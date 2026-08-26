from __future__ import annotations

import hashlib,json,secrets
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import Entity,EvidencePassage,EvidenceReviewBatch,EvidenceReviewBatchItem,ResearchPassageCandidate,ResearchSourceCandidate,SourceDocument
from .passage_adjudication import evidence_controls

class EvidenceReviewBatchError(ValueError):pass

def _canonical(value)->str:return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def freeze_review_batch(session,actor:str,universe:str,status:str="HUMAN_REVIEW_REQUIRED",predicate:str|None=None,min_confidence:float=0,limit:int=50)->EvidenceReviewBatch:
    status=status.upper();predicate=predicate.casefold() if predicate else None
    if status not in {"HUMAN_REVIEW_REQUIRED","DEFERRED","SUPPORT_PROPOSED","CONFLICT"} or not 0<=min_confidence<=1 or not 1<=limit<=100:raise EvidenceReviewBatchError("invalid review batch criteria")
    if not universe.strip():raise EvidenceReviewBatchError("universe is required")
    query=select(ResearchPassageCandidate).join(ResearchSourceCandidate,ResearchSourceCandidate.id==ResearchPassageCandidate.source_candidate_id).join(Entity,Entity.id==ResearchSourceCandidate.entity_id).where(Entity.universe==universe,ResearchPassageCandidate.status==status,ResearchPassageCandidate.confidence>=min_confidence)
    if predicate:query=query.where(ResearchPassageCandidate.predicate==predicate)
    candidates=session.scalars(query.order_by(ResearchPassageCandidate.confidence.desc(),ResearchPassageCandidate.id).limit(limit)).all();items=[]
    for candidate in candidates:
        source=session.get(ResearchSourceCandidate,candidate.source_candidate_id);passage=session.get(EvidencePassage,candidate.evidence_passage_id);document=session.get(SourceDocument,passage.document_id) if passage else None
        if not source or not passage or not document or document.entity_id!=source.entity_id:raise EvidenceReviewBatchError("candidate evidence chain is incomplete")
        controls=evidence_controls(session,candidate,source,passage,document);state="ELIGIBLE" if controls["support_eligible"] else "CONFLICT" if controls["material_open_conflict"] else "STALE" if controls["freshness"]["state"]=="STALE" else "BLOCKED"
        items.append({"passage_candidate_id":candidate.id,"candidate_status":candidate.status,"predicate":candidate.predicate,"passage_hash":passage.passage_hash,"document_hash":document.content_hash,"evidence_state":state})
    criteria={"universe":universe,"status":status,"predicate":predicate,"min_confidence":min_confidence,"limit":limit};manifest={"criteria":criteria,"items":items};digest=hashlib.sha256(_canonical(manifest).encode()).hexdigest()
    existing=session.scalar(select(EvidenceReviewBatch).where(EvidenceReviewBatch.manifest_hash==digest))
    if existing:return existing
    batch=EvidenceReviewBatch(criteria_json=_canonical(criteria),manifest_hash=digest,item_count=len(items),created_by=actor);session.add(batch);session.flush()
    for item in items:session.add(EvidenceReviewBatchItem(batch_id=batch.id,**item))
    session.flush();append_ledger_event(session,"EVIDENCE_REVIEW_BATCH",batch.id,actor,"REVIEWER","BATCH_FROZEN",{"manifest_hash":digest,"item_count":len(items),"criteria":criteria});return batch

def build_batch_packet(session,batch_id:int)->dict:
    batch=session.get(EvidenceReviewBatch,batch_id)
    if not batch:raise EvidenceReviewBatchError("unknown evidence review batch")
    rows=session.scalars(select(EvidenceReviewBatchItem).where(EvidenceReviewBatchItem.batch_id==batch.id).order_by(EvidenceReviewBatchItem.id)).all();items=[{"passage_candidate_id":x.passage_candidate_id,"candidate_status":x.candidate_status,"predicate":x.predicate,"passage_hash":x.passage_hash,"document_hash":x.document_hash,"evidence_state":x.evidence_state} for x in rows];manifest={"criteria":json.loads(batch.criteria_json),"items":items};valid=secrets.compare_digest(hashlib.sha256(_canonical(manifest).encode()).hexdigest(),batch.manifest_hash) and len(items)==batch.item_count
    return {"classification":"PRIVATE—AUTHORIZED EVIDENCE REVIEW BATCH","id":batch.id,"status":batch.status,"criteria":manifest["criteria"],"manifest_hash":batch.manifest_hash,"item_count":batch.item_count,"manifest_valid":valid,"created_by":batch.created_by,"created_at":batch.created_at.isoformat(),"items":items}
