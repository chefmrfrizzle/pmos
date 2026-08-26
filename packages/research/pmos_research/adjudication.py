from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse
import hashlib
import secrets
from sqlalchemy import select
from .db import (
    AdjudicationEvent, Claim, Contact, CorroborationJob, Entity, Evidence,
    DiligenceCase, IdentityCluster, IdentityMembership, RawImportRow,
    ResolutionDecision, ReviewQueueItem,IdentityReviewDecisionAuthorization,IdentityReviewDecisionBinding,
)
from .fact_extraction import identity_supported
from .evidence_capture import capture_official_identity_evidence
from .audit_ledger import append_ledger_event
from .source_discovery import persist_source_candidates

PRIORITY_TYPES={"venture capital","private equity","corporate venture capital","family office","asset manager","hedge fund","government","limited partner","pension","sovereign wealth"}

class AdjudicationInputError(ValueError):pass
class StaleReviewError(RuntimeError):pass

def _version(item:ReviewQueueItem)->str:
    value=item.updated_at
    if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
    return value.isoformat()

def _evidence_digest(session,evidence_ids,allowed_entity_ids:set[int]|None=None)->str|None:
    ids=sorted(set(int(x) for x in evidence_ids))
    if not ids:return None
    rows=session.scalars(select(Evidence).where(Evidence.id.in_(ids))).all()
    if len(rows)!=len(ids):raise AdjudicationInputError("all evidence IDs must exist")
    if allowed_entity_ids is not None and any(x.entity_id not in allowed_entity_ids for x in rows):raise AdjudicationInputError("identity evidence must belong to an identity under review")
    return hashlib.sha256("|".join(sorted(x.content_hash for x in rows)).encode()).hexdigest()

def _review_identity_ids(session,item:ReviewQueueItem,decision:ResolutionDecision)->set[int]:
    raw=session.get(RawImportRow,decision.raw_row_id);ids=set()
    if item.queue_type=="ENTITY":ids.update(x for x in (decision.candidate_entity_id,raw.entity_id if raw else None) if x)
    elif item.queue_type=="CONTACT":
        contacts=[session.get(Contact,x) for x in (decision.candidate_contact_id,raw.contact_id if raw else None) if x]
        ids.update(x.entity_id for x in contacts if x and x.entity_id)
    return ids

def _identity_pair(session,item:ReviewQueueItem,decision:ResolutionDecision)->tuple[str,set[int]]:
    raw=session.get(RawImportRow,decision.raw_row_id)
    if item.queue_type=="ENTITY":kind="ENTITY";ids={x for x in (decision.candidate_entity_id,raw.entity_id if raw else None) if x}
    elif item.queue_type=="CONTACT":kind="PERSON";ids={x for x in (decision.candidate_contact_id,raw.contact_id if raw else None) if x}
    else:raise AdjudicationInputError("queue item is not an adjudicable identity pair")
    if len(ids)!=2:raise AdjudicationInputError("identity review requires two distinct candidates")
    return kind,ids

def _member_ids(session,cluster:IdentityCluster)->set[int]:
    rows=session.scalars(select(IdentityMembership).where(IdentityMembership.cluster_id==cluster.id)).all()
    return {x.entity_id if cluster.identity_type=="ENTITY" else x.contact_id for x in rows if (x.entity_id if cluster.identity_type=="ENTITY" else x.contact_id) is not None}

def _exact_pair_cluster(session,item:ReviewQueueItem,decision:ResolutionDecision,status:str)->IdentityCluster|None:
    kind,ids=_identity_pair(session,item,decision);column=IdentityMembership.entity_id if kind=="ENTITY" else IdentityMembership.contact_id
    clusters=session.scalars(select(IdentityCluster).join(IdentityMembership).where(IdentityCluster.identity_type==kind,IdentityCluster.status==status,column.in_(ids)).distinct()).all()
    exact=[x for x in clusters if _member_ids(session,x)==ids]
    if len(exact)>1:raise AdjudicationInputError("multiple proposed clusters exist for the reviewed identity pair")
    return exact[0] if exact else None

def _assert_pair_available(session,item:ReviewQueueItem,decision:ResolutionDecision)->None:
    kind,ids=_identity_pair(session,item,decision);column=IdentityMembership.entity_id if kind=="ENTITY" else IdentityMembership.contact_id
    conflict=session.scalar(select(IdentityCluster).join(IdentityMembership).where(IdentityCluster.identity_type==kind,IdentityCluster.status.in_(("PROPOSED","ACCEPTED")),column.in_(ids)).limit(1))
    if conflict:raise AdjudicationInputError("an identity candidate already belongs to an active or accepted cluster")

def _create_proposed_cluster(session,item:ReviewQueueItem,decision:ResolutionDecision,reviewer:str):
    _assert_pair_available(session,item,decision)
    raw=session.get(RawImportRow,decision.raw_row_id)
    if item.queue_type=="ENTITY" and raw and raw.entity_id and decision.candidate_entity_id:
        candidate=session.get(Entity,decision.candidate_entity_id);source=session.get(Entity,raw.entity_id)
        cluster=IdentityCluster(identity_type="ENTITY",canonical_label=candidate.name,status="PROPOSED",created_by=reviewer)
        session.add(cluster);session.flush()
        for entity,confidence,basis in ((candidate,1.0,["existing candidate"]),(source,decision.confidence,json.loads(decision.reasons_json))):
            session.add(IdentityMembership(cluster_id=cluster.id,entity_id=entity.id,status="PROPOSED",match_basis_json=json.dumps(basis),confidence=confidence))
        return cluster
    if item.queue_type=="CONTACT" and raw and raw.contact_id and decision.candidate_contact_id:
        candidate=session.get(Contact,decision.candidate_contact_id);source=session.get(Contact,raw.contact_id)
        cluster=IdentityCluster(identity_type="PERSON",canonical_label=candidate.name,status="PROPOSED",created_by=reviewer)
        session.add(cluster);session.flush()
        for contact,confidence,basis in ((candidate,1.0,["existing candidate"]),(source,decision.confidence,json.loads(decision.reasons_json))):
            session.add(IdentityMembership(cluster_id=cluster.id,contact_id=contact.id,status="PROPOSED",match_basis_json=json.dumps(basis),confidence=confidence))
        return cluster
    raise AdjudicationInputError("queue item does not contain two identity candidates")

def adjudicate(session,queue_item_id:int,action:str,reviewer:str,reviewer_role:str,rationale:str,evidence_ids=(),expected_version:str|None=None,review_batch_id:int|None=None):
    """Append a reviewer decision; never overwrite source entities or prior events."""
    if not reviewer.strip() or not rationale.strip():raise AdjudicationInputError("reviewer and rationale are required")
    item=session.get(ReviewQueueItem,queue_item_id)
    if not item:raise AdjudicationInputError("unknown queue item")
    current_version=_version(item)
    if expected_version is not None and expected_version!=current_version:raise StaleReviewError("review item changed; reload before deciding")
    action=action.upper();prior=item.status
    if not review_batch_id:raise AdjudicationInputError("review_batch_id is required")
    decision=session.get(ResolutionDecision,item.resolution_decision_id)
    from .identity_review_batch import IdentityReviewBatchError,validate_identity_assignment
    try:batch_item=validate_identity_assignment(session,review_batch_id,item,decision,action)
    except IdentityReviewBatchError as exc:raise AdjudicationInputError(str(exc)) from exc
    from .identity_review_assignment import IdentityReviewAssignmentError,require_identity_assignment
    try:assignment=require_identity_assignment(session,review_batch_id,reviewer,reviewer_role,action=="APPROVE_MATCH")
    except IdentityReviewAssignmentError as exc:raise AdjudicationInputError(str(exc)) from exc
    allowed={
        "PENDING":{"PROPOSE_MATCH":"PROPOSED","REJECT_MATCH":"REJECTED","MARK_CONFLICT":"CONFLICT","DEFER":"DEFERRED"},
        "DEFERRED":{"PROPOSE_MATCH":"PROPOSED","REJECT_MATCH":"REJECTED","MARK_CONFLICT":"CONFLICT"},
        "PROPOSED":{"APPROVE_MATCH":"ACCEPTED","REJECT_MATCH":"REJECTED","MARK_CONFLICT":"CONFLICT"},
    }
    if action not in allowed.get(prior,{}):raise AdjudicationInputError(f"invalid transition {prior} -> {action}")
    prior_events=session.scalars(select(AdjudicationEvent).where(AdjudicationEvent.queue_item_id==item.id).order_by(AdjudicationEvent.id)).all()
    if action=="APPROVE_MATCH":
        proposal_event=next((x for x in reversed(prior_events) if x.action=="PROPOSE_MATCH"),None);proposer=proposal_event.reviewer if proposal_event else None
        if not proposer or proposer==reviewer:raise AdjudicationInputError("approval requires a different reviewer from the proposer")
        proposal_binding=session.scalar(select(IdentityReviewDecisionBinding).where(IdentityReviewDecisionBinding.adjudication_event_id==proposal_event.id,IdentityReviewDecisionBinding.batch_item_id==batch_item.id))
        if not proposal_binding:raise AdjudicationInputError("approval must use the proposal's frozen identity batch")
    digest=_evidence_digest(session,evidence_ids,_review_identity_ids(session,item,decision))
    if action in {"PROPOSE_MATCH","APPROVE_MATCH"} and not digest:raise AdjudicationInputError("match decisions require scoped evidence snapshots")
    if action=="APPROVE_MATCH":
        proposal=next((x for x in reversed(prior_events) if x.action=="PROPOSE_MATCH"),None)
        if not proposal or not secrets.compare_digest(proposal.evidence_hash or "",digest or ""):raise AdjudicationInputError("approval must review the proposal evidence package")
    if action=="PROPOSE_MATCH":_create_proposed_cluster(session,item,decision,reviewer)
    if prior=="PROPOSED" and action in {"APPROVE_MATCH","REJECT_MATCH","MARK_CONFLICT"}:
        cluster=_exact_pair_cluster(session,item,decision,"PROPOSED")
        if action=="APPROVE_MATCH" and not cluster:raise AdjudicationInputError("no proposed identity cluster exists")
        if cluster:
            cluster.status="ACCEPTED" if action=="APPROVE_MATCH" else "REJECTED"
            for membership in session.scalars(select(IdentityMembership).where(IdentityMembership.cluster_id==cluster.id)):
                membership.status=cluster.status;membership.decided_by=reviewer;membership.decided_at=datetime.now(timezone.utc)
    result=allowed[prior][action];now=datetime.now(timezone.utc)
    event=AdjudicationEvent(queue_item_id=item.id,action=action,prior_state=prior,resulting_state=result,reviewer=reviewer,rationale=rationale,evidence_hash=digest);session.add(event);session.flush();session.add(IdentityReviewDecisionBinding(batch_item_id=batch_item.id,adjudication_event_id=event.id));session.add(IdentityReviewDecisionAuthorization(adjudication_event_id=event.id,assignment_id=assignment.id))
    from .db import IdentityReviewBatch
    append_ledger_event(session,"IDENTITY_REVIEW",item.id,reviewer,reviewer_role.upper(),action,{"prior_state":prior,"resulting_state":result,"review_batch_id":review_batch_id,"assignment_id":assignment.id,"review_batch_manifest_hash":session.get(IdentityReviewBatch,review_batch_id).manifest_hash,"evidence_hash":digest,"rationale":rationale})
    item.status=result;item.updated_at=now
    session.flush()
    return {"queue_item_id":item.id,"prior_state":prior,"resulting_state":result,"version":_version(item)}

def _domain(url:str|None)->str:
    return urlparse(url or "").netloc.lower().split(":")[0].removeprefix("www.")

def normalize_public_url(url:str|None)->str:
    value=(url or "").strip()
    if value and "://" not in value:value="https://"+value
    parsed=urlparse(value)
    return value if parsed.scheme in {"http","https"} and parsed.netloc else ""

def queue_priority(decision:ResolutionDecision,raw:RawImportRow|None,entity:Entity|None)->tuple[int,str,list[str]]:
    reasons=[]
    if decision.state=="CONFLICT":priority=100;reasons.append("deterministic conflict")
    elif decision.state=="PROBABLE_MATCH":priority=75;reasons.append("probable match requires human adjudication")
    else:priority=45;reasons.append("insufficient deterministic identity evidence")
    if decision.candidate_entity_id:
        kind="ENTITY"
        if entity and entity.official_url:priority+=10;reasons.append("candidate official URL available")
        if entity and (entity.entity_type or "").casefold() in PRIORITY_TYPES:priority+=10;reasons.append("priority institutional type")
    elif decision.candidate_contact_id:kind="CONTACT";priority+=5
    else:kind="UNRESOLVED"
    return min(priority,100),kind,reasons

def build_review_queue(session)->Counter:
    counts=Counter()
    decisions=session.scalars(select(ResolutionDecision).where(ResolutionDecision.state!="EXACT_MATCH").order_by(ResolutionDecision.id)).all()
    existing=set(session.scalars(select(ReviewQueueItem.resolution_decision_id)).all())
    for decision in decisions:
        if decision.id in existing:counts["existing"]+=1;continue
        raw=session.get(RawImportRow,decision.raw_row_id);entity=session.get(Entity,raw.entity_id) if raw and raw.entity_id else None
        priority,kind,reasons=queue_priority(decision,raw,entity)
        session.add(ReviewQueueItem(resolution_decision_id=decision.id,queue_type=kind,priority=priority,reasons_json=json.dumps(reasons)))
        counts[kind]+=1
    session.flush();return counts

def enqueue_corroboration(session,limit:int=0)->Counter:
    counts=Counter();seen=set()
    existing={(x.entity_id,x.source_url) for x in session.scalars(select(CorroborationJob)).all()}
    entities=session.scalars(select(Entity).where(Entity.official_url.is_not(None),Entity.official_url!="",Entity.mandate.is_not(None),Entity.mandate!="").order_by(Entity.entity_type,Entity.canonical_name,Entity.id)).all()
    for entity in entities:
        if entity.canonical_name in seen:counts["canonical_duplicate_skipped"]+=1;continue
        seen.add(entity.canonical_name);source_url=normalize_public_url(entity.official_url);domain=_domain(source_url)
        if not domain:counts["invalid_url"]+=1;continue
        if (entity.id,source_url) in existing:counts["existing"]+=1;continue
        session.add(CorroborationJob(entity_id=entity.id,source_url=source_url,source_domain=domain,status="PENDING",checkpoint_json="{}"))
        counts["queued"]+=1
        if limit and counts["queued"]>=limit:break
    session.flush();return counts

def enqueue_case_corroboration(session)->Counter:
    """Queue only public-registry entities already selected into diligence cases."""
    counts=Counter();existing={(x.entity_id,x.source_url) for x in session.scalars(select(CorroborationJob)).all()}
    entities=session.scalars(select(Entity).join(DiligenceCase,DiligenceCase.entity_id==Entity.id).where(Entity.universe!="imported_private").order_by(Entity.universe,Entity.canonical_name,Entity.id)).all()
    for entity in entities:
        source_url=normalize_public_url(entity.official_url);domain=_domain(source_url)
        if not domain:counts["invalid_url"]+=1;continue
        if (entity.id,source_url) in existing:counts["existing"]+=1;continue
        session.add(CorroborationJob(entity_id=entity.id,source_url=source_url,source_domain=domain,status="PENDING",checkpoint_json="{}"))
        existing.add((entity.id,source_url));counts["queued"]+=1
    session.flush();return counts

def queue_summary(session)->dict:
    review=Counter(x.status for x in session.scalars(select(ReviewQueueItem)).all())
    jobs=Counter(x.status for x in session.scalars(select(CorroborationJob)).all())
    return {"review_queue":dict(sorted(review.items())),"corroboration_jobs":dict(sorted(jobs.items())),"generated_at":datetime.now(timezone.utc).isoformat()}

def run_corroboration_job(session,job:CorroborationJob,adapter)->str:
    job.attempts+=1;job.updated_at=datetime.now(timezone.utc);entity=session.get(Entity,job.entity_id)
    try:
        snapshot=adapter.fetch(job.source_url)
        status=snapshot.get("status","failed")
        if status!="ok":
            job.status="BLOCKED" if status.startswith("robots_") else "NEEDS_REVIEW"
            job.last_error=status;append_ledger_event(session,"RESEARCH_JOB",job.id,"research-worker","SYSTEM","JOB_COMPLETED",{"entity_id":job.entity_id,"status":job.status,"reason":status});return job.status
        source_url=snapshot["url"];content_hash=snapshot["hash"]
        duplicate=session.scalar(select(Evidence).where(Evidence.entity_id==entity.id,Evidence.source_url==source_url,Evidence.content_hash==content_hash))
        if not duplicate:session.add(Evidence(entity_id=entity.id,source_url=source_url,source_type="official",content_hash=content_hash,title=snapshot["title"],text_excerpt=snapshot["text"][:5000],confidence=.9))
        supported=identity_supported(entity.name,snapshot["title"]+" "+snapshot["text"][:10000])
        if supported:
            existing=session.scalar(select(Claim).where(Claim.entity_id==entity.id,Claim.field=="official_identity",Claim.value==entity.name,Claim.source_url==source_url,Claim.evidence_hash==content_hash))
            if not existing:
                existing=Claim(entity_id=entity.id,field="official_identity",value=entity.name,source_url=source_url,source_type="official",confidence=.9,verification_status="SUPPORTED",extractor="deterministic_identity_v2",evidence_hash=content_hash);session.add(existing);session.flush()
            captured=capture_official_identity_evidence(session,entity,existing,source_url,content_hash,snapshot["title"],snapshot["text"][:10000])
            # This supports only the official-identity claim. Entity-level status is
            # a field-coverage roll-up and must never be promoted by one homepage hit.
            job.status="SUPPORTED";entity.verification_status="EVIDENCE_COLLECTED";entity.evidence_confidence=max(entity.evidence_confidence,35)
        else:
            job.status="HUMAN_REVIEW_REQUIRED";entity.verification_status="EVIDENCE_COLLECTED";entity.evidence_confidence=max(entity.evidence_confidence,35)
        discovery=persist_source_candidates(session,entity,source_url,snapshot.get("html","")) if snapshot.get("html") else Counter()
        checkpoint={"source_url":source_url,"evidence_hash":content_hash,"identity_supported":supported,"source_candidates_queued":discovery.get("queued",0)}
        if supported:checkpoint.update(captured)
        job.checkpoint_json=json.dumps(checkpoint,sort_keys=True)
        job.last_error=None;append_ledger_event(session,"RESEARCH_JOB",job.id,"research-worker","SYSTEM","JOB_COMPLETED",{"entity_id":job.entity_id,"status":job.status,"evidence_hash":content_hash,"identity_supported":supported});return job.status
    except Exception as exc:
        job.status="FAILED";job.last_error=f"{type(exc).__name__}: {exc}"[:1000];append_ledger_event(session,"RESEARCH_JOB",job.id,"research-worker","SYSTEM","JOB_FAILED",{"entity_id":job.entity_id,"status":job.status,"error_type":type(exc).__name__});return job.status
