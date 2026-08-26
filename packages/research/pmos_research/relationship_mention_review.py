from __future__ import annotations

import hashlib,json,secrets
from datetime import datetime,timedelta,timezone
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import Entity,EvidencePassage,RelationshipMentionCandidate,RelationshipMentionResolution,RelationshipMentionReviewAssignment,RelationshipMentionReviewAssignmentEvent,RelationshipMentionReviewBatch,RelationshipMentionReviewBatchItem,RelationshipMentionReviewDecisionBinding,SourceDocument

class RelationshipMentionReviewError(ValueError):pass
def _canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def _now():return datetime.now(timezone.utc)
def _aware(value):return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def mention_review_fingerprint(session,mention:RelationshipMentionCandidate)->str:
    source=session.get(Entity,mention.from_entity_id);passage=session.get(EvidencePassage,mention.evidence_passage_id);document=session.get(SourceDocument,passage.document_id) if passage else None;resolution=session.scalar(select(RelationshipMentionResolution).where(RelationshipMentionResolution.mention_candidate_id==mention.id).order_by(RelationshipMentionResolution.version.desc()));target=session.get(Entity,resolution.target_entity_id) if resolution else None
    if not source or not passage or not document:raise RelationshipMentionReviewError("mention review chain is incomplete")
    material={"mention_id":mention.id,"status":mention.status,"mention_hash":mention.mention_hash,"relation_type":mention.suggested_relation_type,"source":{"id":source.id,"canonical_name":source.canonical_name,"universe":source.universe,"country":source.country,"official_url":source.official_url},"document_hash":document.content_hash,"passage_hash":passage.passage_hash,"resolution_id":resolution.id if resolution else None,"resolution_status":resolution.status if resolution else None,"target":{"id":target.id,"canonical_name":target.canonical_name,"universe":target.universe,"country":target.country,"official_url":target.official_url} if target else None,"identity_package_hash":resolution.identity_package_hash if resolution else None}
    return hashlib.sha256(_canonical(material).encode()).hexdigest()

def freeze_mention_review_batch(session,actor:str,universe:str,status:str="ENTITY_RESOLUTION_REQUIRED",limit:int=100)->RelationshipMentionReviewBatch:
    status=status.upper()
    if not actor.strip() or not universe.strip() or status not in {"ENTITY_RESOLUTION_REQUIRED","TARGET_PROPOSED"} or not 1<=limit<=100:raise RelationshipMentionReviewError("invalid mention batch criteria")
    rows=[]
    for mention in session.scalars(select(RelationshipMentionCandidate).where(RelationshipMentionCandidate.status==status).order_by(RelationshipMentionCandidate.id)):
        source=session.get(Entity,mention.from_entity_id)
        if not source or source.universe!=universe:continue
        rows.append({"mention_candidate_id":mention.id,"item_status":mention.status,"identity_fingerprint":mention_review_fingerprint(session,mention)})
        if len(rows)>=limit:break
    criteria={"universe":universe,"status":status,"limit":limit};manifest={"criteria":criteria,"items":rows};digest=hashlib.sha256(_canonical(manifest).encode()).hexdigest();existing=session.scalar(select(RelationshipMentionReviewBatch).where(RelationshipMentionReviewBatch.manifest_hash==digest))
    if existing:return existing
    batch=RelationshipMentionReviewBatch(criteria_json=_canonical(criteria),manifest_hash=digest,item_count=len(rows),created_by=actor.strip());session.add(batch);session.flush()
    for row in rows:session.add(RelationshipMentionReviewBatchItem(batch_id=batch.id,**row))
    session.flush();append_ledger_event(session,"RELATIONSHIP_MENTION_REVIEW_BATCH",batch.id,actor.strip(),"ADMIN","BATCH_FROZEN",{"manifest_hash":digest,"item_count":len(rows),"criteria":criteria});return batch

def freeze_pending_mention_batches(session,actor:str="mention-batch-worker",status:str="ENTITY_RESOLUTION_REQUIRED",limit_per_universe:int=100)->dict:
    status=status.upper()
    if status not in {"ENTITY_RESOLUTION_REQUIRED","TARGET_PROPOSED"} or not 1<=limit_per_universe<=100:raise RelationshipMentionReviewError("invalid pending mention batch criteria")
    universes=sorted({source.universe for mention,source in session.execute(select(RelationshipMentionCandidate,Entity).join(Entity,Entity.id==RelationshipMentionCandidate.from_entity_id).where(RelationshipMentionCandidate.status==status)).all()})
    batches=[]
    for universe in universes:
        batch=freeze_mention_review_batch(session,actor,universe,status,limit_per_universe)
        if batch.item_count:batches.append({"batch_id":batch.id,"item_count":batch.item_count})
    return {"classification":"PMOS PRIVATE AGGREGATE MENTION BATCH PREPARATION — NO RECORD VALUES","status":status,"universe_count":len(universes),"batch_count":len(batches),"item_count":sum(x["item_count"] for x in batches),"batches":batches}

def build_mention_review_batch_packet(session,batch_id:int)->dict:
    batch=session.get(RelationshipMentionReviewBatch,batch_id)
    if not batch:raise RelationshipMentionReviewError("unknown mention review batch")
    rows=session.scalars(select(RelationshipMentionReviewBatchItem).where(RelationshipMentionReviewBatchItem.batch_id==batch.id).order_by(RelationshipMentionReviewBatchItem.id)).all();items=[{"mention_candidate_id":x.mention_candidate_id,"item_status":x.item_status,"identity_fingerprint":x.identity_fingerprint} for x in rows];manifest={"criteria":json.loads(batch.criteria_json),"items":items};valid=secrets.compare_digest(hashlib.sha256(_canonical(manifest).encode()).hexdigest(),batch.manifest_hash) and len(items)==batch.item_count
    return {"classification":"PRIVATE—AUTHORIZED RELATIONSHIP MENTION REVIEW BATCH","id":batch.id,"status":batch.status,"criteria":manifest["criteria"],"manifest_hash":batch.manifest_hash,"item_count":batch.item_count,"manifest_valid":valid,"created_by":batch.created_by,"created_at":batch.created_at.isoformat(),"items":items}

def assign_mention_reviewer(session,batch_id:int,reviewer:str,reviewer_role:str,actor:str,rationale:str,expires_hours:int=24):
    batch=session.get(RelationshipMentionReviewBatch,batch_id);reviewer=reviewer.strip();role=reviewer_role.upper()
    if not batch or batch.status!="FROZEN" or not reviewer or reviewer==actor or role not in {"RESEARCHER","REVIEWER"} or len(rationale.strip())<10 or not 1<=expires_hours<=168:raise RelationshipMentionReviewError("invalid mention review assignment")
    active=session.scalar(select(RelationshipMentionReviewAssignment).where(RelationshipMentionReviewAssignment.batch_id==batch.id,RelationshipMentionReviewAssignment.reviewer==reviewer,RelationshipMentionReviewAssignment.status=="ACTIVE"))
    if active and _aware(active.expires_at)>_now():raise RelationshipMentionReviewError("reviewer already has an active mention assignment")
    if active:active.status="EXPIRED";session.add(RelationshipMentionReviewAssignmentEvent(assignment_id=active.id,action="EXPIRE",prior_state="ACTIVE",resulting_state="EXPIRED",actor=actor,rationale="Prior assignment reached its bounded expiry"))
    assignment=RelationshipMentionReviewAssignment(batch_id=batch.id,reviewer=reviewer,reviewer_role=role,assigned_by=actor,expires_at=_now()+timedelta(hours=expires_hours));session.add(assignment);session.flush();session.add(RelationshipMentionReviewAssignmentEvent(assignment_id=assignment.id,action="ASSIGN",prior_state=None,resulting_state="ACTIVE",actor=actor,rationale=rationale.strip()));append_ledger_event(session,"RELATIONSHIP_MENTION_REVIEW_ASSIGNMENT",assignment.id,actor,"ADMIN","ASSIGN",{"batch_id":batch.id,"reviewer":reviewer,"reviewer_role":role,"expires_at":assignment.expires_at.isoformat()});session.flush();return assignment

def validate_mention_review_decision(session,batch_id:int,mention:RelationshipMentionCandidate,reviewer:str,reviewer_role:str,approval:bool):
    batch=session.get(RelationshipMentionReviewBatch,batch_id);item=session.scalar(select(RelationshipMentionReviewBatchItem).where(RelationshipMentionReviewBatchItem.batch_id==batch_id,RelationshipMentionReviewBatchItem.mention_candidate_id==mention.id)) if batch else None
    if not batch or batch.status!="FROZEN" or not item or not build_mention_review_batch_packet(session,batch.id)["manifest_valid"]:raise RelationshipMentionReviewError("a valid frozen mention review batch is required")
    if item.item_status!=mention.status or not secrets.compare_digest(item.identity_fingerprint,mention_review_fingerprint(session,mention)):raise RelationshipMentionReviewError("mention identity package changed after batch assignment")
    assignment=session.scalar(select(RelationshipMentionReviewAssignment).where(RelationshipMentionReviewAssignment.batch_id==batch.id,RelationshipMentionReviewAssignment.reviewer==reviewer,RelationshipMentionReviewAssignment.status=="ACTIVE"))
    if not assignment or _aware(assignment.expires_at)<=_now():
        if assignment:assignment.status="EXPIRED";session.add(RelationshipMentionReviewAssignmentEvent(assignment_id=assignment.id,action="EXPIRE",prior_state="ACTIVE",resulting_state="EXPIRED",actor="authorization-check",rationale="Assignment reached its bounded expiry"));append_ledger_event(session,"RELATIONSHIP_MENTION_REVIEW_ASSIGNMENT",assignment.id,"authorization-check","SYSTEM","EXPIRE",{"batch_id":assignment.batch_id});session.flush()
        raise RelationshipMentionReviewError("active unexpired mention review assignment is required")
    if assignment.reviewer_role!=reviewer_role.upper() or (approval and assignment.reviewer_role!="REVIEWER"):raise RelationshipMentionReviewError("mention assignment role does not authorize this action")
    return item,assignment

def assigned_mention_batch_items(session,batch_id:int,reviewer:str,reviewer_role:str)->list[RelationshipMentionReviewBatchItem]:
    batch=session.get(RelationshipMentionReviewBatch,batch_id)
    if not batch or batch.status!="FROZEN" or not build_mention_review_batch_packet(session,batch_id)["manifest_valid"]:raise RelationshipMentionReviewError("a valid frozen mention review batch is required")
    assignment=session.scalar(select(RelationshipMentionReviewAssignment).where(RelationshipMentionReviewAssignment.batch_id==batch.id,RelationshipMentionReviewAssignment.reviewer==reviewer,RelationshipMentionReviewAssignment.status=="ACTIVE"))
    if not assignment or _aware(assignment.expires_at)<=_now():
        if assignment:assignment.status="EXPIRED";session.add(RelationshipMentionReviewAssignmentEvent(assignment_id=assignment.id,action="EXPIRE",prior_state="ACTIVE",resulting_state="EXPIRED",actor="authorization-check",rationale="Assignment reached its bounded expiry"));append_ledger_event(session,"RELATIONSHIP_MENTION_REVIEW_ASSIGNMENT",assignment.id,"authorization-check","SYSTEM","EXPIRE",{"batch_id":assignment.batch_id});session.flush()
        raise RelationshipMentionReviewError("active unexpired mention review assignment is required")
    if assignment.reviewer_role!=reviewer_role.upper():raise RelationshipMentionReviewError("mention assignment role does not authorize this access")
    return session.scalars(select(RelationshipMentionReviewBatchItem).where(RelationshipMentionReviewBatchItem.batch_id==batch.id).order_by(RelationshipMentionReviewBatchItem.id)).all()

def bind_mention_review_decision(session,batch_item_id:int,assignment_id:int,mention_event_id:int|None=None,resolution_event_id:int|None=None):
    if bool(mention_event_id)==bool(resolution_event_id):raise RelationshipMentionReviewError("exactly one mention decision event must be bound")
    binding=RelationshipMentionReviewDecisionBinding(batch_item_id=batch_item_id,assignment_id=assignment_id,mention_event_id=mention_event_id,resolution_event_id=resolution_event_id);session.add(binding);session.flush();return binding

def revoke_mention_assignment(session,assignment_id:int,actor:str,rationale:str):
    assignment=session.get(RelationshipMentionReviewAssignment,assignment_id)
    if not assignment or assignment.status!="ACTIVE" or len(rationale.strip())<10:raise RelationshipMentionReviewError("active assignment and substantive rationale are required")
    assignment.status="REVOKED";assignment.revoked_by=actor;assignment.revocation_reason=rationale.strip();session.add(RelationshipMentionReviewAssignmentEvent(assignment_id=assignment.id,action="REVOKE",prior_state="ACTIVE",resulting_state="REVOKED",actor=actor,rationale=rationale.strip()));append_ledger_event(session,"RELATIONSHIP_MENTION_REVIEW_ASSIGNMENT",assignment.id,actor,"ADMIN","REVOKE",{"batch_id":assignment.batch_id,"reason":rationale.strip()});session.flush();return assignment

def close_mention_review_batch(session,batch_id:int,actor:str,rationale:str):
    batch=session.get(RelationshipMentionReviewBatch,batch_id)
    if not batch or batch.status!="FROZEN" or len(rationale.strip())<10:raise RelationshipMentionReviewError("open mention batch and substantive rationale are required")
    batch.status="CLOSED"
    for assignment in session.scalars(select(RelationshipMentionReviewAssignment).where(RelationshipMentionReviewAssignment.batch_id==batch.id,RelationshipMentionReviewAssignment.status=="ACTIVE")):
        assignment.status="REVOKED";assignment.revoked_by=actor;assignment.revocation_reason="Batch closed: "+rationale.strip();session.add(RelationshipMentionReviewAssignmentEvent(assignment_id=assignment.id,action="BATCH_CLOSE",prior_state="ACTIVE",resulting_state="REVOKED",actor=actor,rationale=rationale.strip()))
    append_ledger_event(session,"RELATIONSHIP_MENTION_REVIEW_BATCH",batch.id,actor,"ADMIN","BATCH_CLOSED",{"rationale":rationale.strip()});session.flush();return batch
