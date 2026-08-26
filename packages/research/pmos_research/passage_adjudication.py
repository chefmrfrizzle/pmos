from __future__ import annotations

import hashlib,re,secrets
from datetime import datetime,timezone

from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .evidence_routing import queue_claim_routes
from .db import (
    Claim,ClaimEvidence,ConflictCase,ConflictMember,EvidencePassage,EvidenceReviewBatch,EvidenceReviewBatchItem,EvidenceReviewDecisionBinding,
    ResearchPassageAdjudicationEvent,ResearchPassageCandidate,
    ResearchDocumentSnapshot,ResearchSourceCandidate,SourceDocument,
)
from .diligence import FRESHNESS_DAYS

MATERIAL_SINGLE_VALUE={"legal_identity","legal_name","legal_status","regulatory_status","ownership_control","authority_to_transact","fund_manager","fund_domicile"}
ACTIVE_CLAIM_STATES={"CANDIDATE","SUPPORTED","CORROBORATED","SPECIALIST_VERIFIED","CONFLICT"}

class PassageAdjudicationError(ValueError):pass

def _normalized(value:str)->str:return " ".join(value.casefold().split())

def _validate_value(passage:str,value:str)->str:
    clean=" ".join((value or "").split())
    if len(clean)<3 or len(clean)>1000 or not re.search(r"[a-z0-9]{3}",clean,re.I):raise PassageAdjudicationError("claim value is too short, too long, or non-substantive")
    if _normalized(clean) not in _normalized(passage):raise PassageAdjudicationError("claim value must be an exact normalized substring of the evidence passage")
    return clean

def _context(session,candidate_id:int):
    candidate=session.get(ResearchPassageCandidate,candidate_id)
    if not candidate:raise PassageAdjudicationError("unknown passage candidate")
    source=session.get(ResearchSourceCandidate,candidate.source_candidate_id);passage=session.get(EvidencePassage,candidate.evidence_passage_id)
    document=session.get(SourceDocument,passage.document_id) if passage else None
    if not source or not passage or not document or document.entity_id!=source.entity_id:raise PassageAdjudicationError("candidate evidence chain is incomplete or out of scope")
    return candidate,source,passage,document

def _batch_item(session,batch_id:int,candidate,passage,document,action:str):
    from .evidence_review_batch import build_batch_packet
    batch=session.get(EvidenceReviewBatch,batch_id);item=session.scalar(select(EvidenceReviewBatchItem).where(EvidenceReviewBatchItem.batch_id==batch_id,EvidenceReviewBatchItem.passage_candidate_id==candidate.id)) if batch else None
    if not batch or not item or batch.status!="FROZEN" or not build_batch_packet(session,batch.id)["manifest_valid"]:raise PassageAdjudicationError("a valid frozen review batch assignment is required")
    if not secrets.compare_digest(item.passage_hash,passage.passage_hash) or not secrets.compare_digest(item.document_hash,document.content_hash):raise PassageAdjudicationError("evidence changed after batch assignment; freeze a new review batch")
    if action!="APPROVE_SUPPORT" and item.candidate_status!=candidate.status:raise PassageAdjudicationError("candidate state changed after batch assignment; freeze a new review batch")
    return item

def evidence_controls(session,candidate,source,passage,document)->dict:
    snapshot=session.scalar(select(ResearchDocumentSnapshot).where(ResearchDocumentSnapshot.source_candidate_id==source.id,ResearchDocumentSnapshot.source_document_id==document.id,ResearchDocumentSnapshot.text_hash==document.content_hash).order_by(ResearchDocumentSnapshot.id.desc()))
    passage_hash_valid=secrets.compare_digest(hashlib.sha256(passage.passage.encode()).hexdigest(),passage.passage_hash)
    snapshot_hash_valid=bool(snapshot) and secrets.compare_digest(hashlib.sha256(snapshot.normalized_text.encode()).hexdigest(),snapshot.text_hash)
    passage_in_snapshot=bool(snapshot) and _normalized(passage.passage) in _normalized(snapshot.normalized_text)
    observed=document.retrieved_at if document.retrieved_at.tzinfo else document.retrieved_at.replace(tzinfo=timezone.utc)
    age=max(0,(datetime.now(timezone.utc)-observed).days);freshness_key="identity" if candidate.predicate in {"legal_identity","legal_name"} else candidate.predicate;threshold=FRESHNESS_DAYS.get(freshness_key,180)
    conflicts=session.scalars(select(ConflictCase).where(ConflictCase.entity_id==source.entity_id,ConflictCase.predicate==candidate.predicate,ConflictCase.status!="RESOLVED")).all()
    integrity=passage_hash_valid and snapshot_hash_valid and passage_in_snapshot and document.source_rank=="S1"
    return {"passage_hash_valid":passage_hash_valid,"snapshot_hash_valid":snapshot_hash_valid,"passage_in_snapshot":passage_in_snapshot,"source_rank_eligible":document.source_rank=="S1","freshness":{"state":"CURRENT" if age<=threshold else "STALE","age_days":age,"threshold_days":threshold,"observed_at":observed.isoformat()},"open_conflict_count":len(conflicts),"material_open_conflict":any(x.materiality=="MATERIAL" for x in conflicts),"evidence_eligible":integrity and age<=threshold,"support_eligible":integrity and age<=threshold and not any(x.materiality=="MATERIAL" for x in conflicts)}

def _material_conflicts(session,entity_id:int,predicate:str,value:str)->list[Claim]:
    if predicate not in MATERIAL_SINGLE_VALUE:return []
    claims=session.scalars(select(Claim).where(Claim.entity_id==entity_id,Claim.field==predicate,Claim.verification_status.in_(ACTIVE_CLAIM_STATES))).all()
    return [x for x in claims if not secrets.compare_digest(_normalized(x.value),_normalized(value))]

def _create_claim(session,candidate,source,passage,document,value,status)->Claim:
    claim=Claim(entity_id=source.entity_id,field=candidate.predicate,value=value,source_url=document.source_url,source_type=document.source_type,confidence=candidate.confidence,verification_status=status,extractor="specialist_passage_adjudication_v1",evidence_hash=document.content_hash)
    session.add(claim);session.flush();session.add(ClaimEvidence(claim_id=claim.id,passage_id=passage.id,directness=candidate.confidence,supports=True));session.flush();return claim

def adjudicate_passage(session,candidate_id:int,action:str,reviewer:str,rationale:str,claim_value:str|None=None,expected_status:str|None=None,review_batch_id:int|None=None):
    candidate,source,passage,document=_context(session,candidate_id)
    if not reviewer.strip() or len(rationale.strip())<10:raise PassageAdjudicationError("reviewer and substantive rationale are required")
    if expected_status is not None and candidate.status!=expected_status:raise PassageAdjudicationError("passage candidate changed; reload before deciding")
    action=action.upper();prior=candidate.status
    if not review_batch_id:raise PassageAdjudicationError("review_batch_id is required")
    batch_item=_batch_item(session,review_batch_id,candidate,passage,document,action)
    transitions={
        "HUMAN_REVIEW_REQUIRED":{"PROPOSE_SUPPORT":"SUPPORT_PROPOSED","REJECT":"REJECTED","DEFER":"DEFERRED","MARK_CONFLICT":"CONFLICT"},
        "DEFERRED":{"PROPOSE_SUPPORT":"SUPPORT_PROPOSED","REJECT":"REJECTED","MARK_CONFLICT":"CONFLICT"},
        "SUPPORT_PROPOSED":{"APPROVE_SUPPORT":"SUPPORTED","REJECT":"REJECTED","MARK_CONFLICT":"CONFLICT"},
    }
    if action not in transitions.get(prior,{}):raise PassageAdjudicationError(f"invalid transition {prior} -> {action}")
    controls=evidence_controls(session,candidate,source,passage,document)
    if action in {"PROPOSE_SUPPORT","APPROVE_SUPPORT","MARK_CONFLICT"} and not controls["evidence_eligible"]:raise PassageAdjudicationError("evidence integrity, first-party rank, or freshness control failed")
    if action in {"PROPOSE_SUPPORT","APPROVE_SUPPORT"} and controls["material_open_conflict"]:raise PassageAdjudicationError("an open material conflict blocks support; use the conflict workflow")
    value=_validate_value(passage.passage,claim_value or "") if action in {"PROPOSE_SUPPORT","APPROVE_SUPPORT","MARK_CONFLICT"} else None
    events=session.scalars(select(ResearchPassageAdjudicationEvent).where(ResearchPassageAdjudicationEvent.passage_candidate_id==candidate.id).order_by(ResearchPassageAdjudicationEvent.id)).all()
    result=transitions[prior][action];claim=None;route_ids=[]
    conflicts=_material_conflicts(session,source.entity_id,candidate.predicate,value) if value else []
    if action=="PROPOSE_SUPPORT" and conflicts:raise PassageAdjudicationError("material contradiction detected; mark conflict instead of proposing support")
    if action=="APPROVE_SUPPORT":
        proposal=next((x for x in reversed(events) if x.action=="PROPOSE_SUPPORT"),None)
        if not proposal or proposal.reviewer==reviewer:raise PassageAdjudicationError("independent approval is required")
        proposal_binding=session.scalar(select(EvidenceReviewDecisionBinding).where(EvidenceReviewDecisionBinding.adjudication_event_id==proposal.id,EvidenceReviewDecisionBinding.batch_item_id==batch_item.id))
        if not proposal_binding:raise PassageAdjudicationError("approval must use the proposal's frozen review batch")
        if not secrets.compare_digest(_normalized(proposal.claim_value or ""),_normalized(value)):raise PassageAdjudicationError("approval must use the exact proposed claim value")
        if conflicts:raise PassageAdjudicationError("material contradiction appeared after proposal; mark conflict")
        claim=_create_claim(session,candidate,source,passage,document,value,"SUPPORTED")
        route_ids=queue_claim_routes(session,claim,candidate.id)
    elif action=="MARK_CONFLICT":
        claim=_create_claim(session,candidate,source,passage,document,value,"CONFLICT")
        conflict=session.scalar(select(ConflictCase).where(ConflictCase.entity_id==source.entity_id,ConflictCase.predicate==candidate.predicate,ConflictCase.status!="RESOLVED").order_by(ConflictCase.id.desc()))
        if not conflict:
            conflict=ConflictCase(entity_id=source.entity_id,predicate=candidate.predicate,materiality="MATERIAL" if candidate.predicate in MATERIAL_SINGLE_VALUE else "NON_MATERIAL",status="HUMAN_REVIEW_REQUIRED");session.add(conflict);session.flush()
        member_ids={x.id for x in conflicts} | {claim.id}
        existing=set(session.scalars(select(ConflictMember.claim_id).where(ConflictMember.conflict_id==conflict.id)).all())
        for claim_id in sorted(member_ids-existing):session.add(ConflictMember(conflict_id=conflict.id,claim_id=claim_id))
    candidate.status=result
    event=ResearchPassageAdjudicationEvent(passage_candidate_id=candidate.id,action=action,prior_state=prior,resulting_state=result,reviewer=reviewer,rationale=rationale.strip(),claim_value=value,resulting_claim_id=claim.id if claim else None);session.add(event);session.flush();session.add(EvidenceReviewDecisionBinding(batch_item_id=batch_item.id,adjudication_event_id=event.id))
    append_ledger_event(session,"PASSAGE_REVIEW",candidate.id,reviewer,"REVIEWER",action,{"entity_id":source.entity_id,"predicate":candidate.predicate,"prior_state":prior,"resulting_state":result,"review_batch_id":review_batch_id,"review_batch_manifest_hash":session.get(EvidenceReviewBatch,review_batch_id).manifest_hash,"passage_hash":passage.passage_hash,"document_hash":document.content_hash,"claim_value_hash":hashlib.sha256(value.encode()).hexdigest() if value else None,"resulting_claim_id":claim.id if claim else None,"evidence_controls":controls,"rationale":rationale.strip()})
    session.flush();return {"candidate_id":candidate.id,"prior_state":prior,"resulting_state":result,"claim_id":claim.id if claim else None,"routing_candidate_ids":route_ids}
