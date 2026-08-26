from __future__ import annotations

from datetime import datetime,timedelta,timezone
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import IdentityReviewAssignment,IdentityReviewAssignmentEvent,IdentityReviewBatch

ROLES={"RESEARCHER","REVIEWER"};APPROVER_ROLES={"REVIEWER"}
class IdentityReviewAssignmentError(ValueError):pass
def _now():return datetime.now(timezone.utc)
def _aware(value):return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def assign_identity_reviewer(session,batch_id:int,reviewer:str,reviewer_role:str,actor:str,rationale:str,expires_hours:int=24)->IdentityReviewAssignment:
    batch=session.get(IdentityReviewBatch,batch_id);reviewer=reviewer.strip();reviewer_role=reviewer_role.upper()
    if not batch or batch.status!="FROZEN":raise IdentityReviewAssignmentError("identity batch is not open for assignment")
    if not reviewer or reviewer==actor:raise IdentityReviewAssignmentError("identity assignment requires a different named reviewer")
    if reviewer_role not in ROLES or not 1<=expires_hours<=168 or len(rationale.strip())<10:raise IdentityReviewAssignmentError("invalid identity role, expiry, or rationale")
    active=session.scalar(select(IdentityReviewAssignment).where(IdentityReviewAssignment.batch_id==batch_id,IdentityReviewAssignment.reviewer==reviewer,IdentityReviewAssignment.status=="ACTIVE"))
    if active and _aware(active.expires_at)>_now():raise IdentityReviewAssignmentError("reviewer already has an active identity assignment")
    if active:active.status="EXPIRED";session.add(IdentityReviewAssignmentEvent(assignment_id=active.id,action="EXPIRE",prior_state="ACTIVE",resulting_state="EXPIRED",actor=actor,rationale="Prior assignment reached its bounded expiry"))
    assignment=IdentityReviewAssignment(batch_id=batch_id,reviewer=reviewer,reviewer_role=reviewer_role,assigned_by=actor,expires_at=_now()+timedelta(hours=expires_hours));session.add(assignment);session.flush();session.add(IdentityReviewAssignmentEvent(assignment_id=assignment.id,action="ASSIGN",prior_state=None,resulting_state="ACTIVE",actor=actor,rationale=rationale.strip()));append_ledger_event(session,"IDENTITY_REVIEW_ASSIGNMENT",assignment.id,actor,"ADMIN","ASSIGN",{"batch_id":batch_id,"reviewer":reviewer,"reviewer_role":reviewer_role,"expires_at":assignment.expires_at.isoformat()});session.flush();return assignment

def revoke_identity_assignment(session,assignment_id:int,actor:str,rationale:str)->IdentityReviewAssignment:
    assignment=session.get(IdentityReviewAssignment,assignment_id)
    if not assignment or assignment.status!="ACTIVE" or len(rationale.strip())<10:raise IdentityReviewAssignmentError("active identity assignment and substantive rationale are required")
    assignment.status="REVOKED";assignment.revoked_by=actor;assignment.revocation_reason=rationale.strip();session.add(IdentityReviewAssignmentEvent(assignment_id=assignment.id,action="REVOKE",prior_state="ACTIVE",resulting_state="REVOKED",actor=actor,rationale=rationale.strip()));append_ledger_event(session,"IDENTITY_REVIEW_ASSIGNMENT",assignment.id,actor,"ADMIN","REVOKE",{"batch_id":assignment.batch_id,"reason":rationale.strip()});session.flush();return assignment

def close_identity_batch(session,batch_id:int,actor:str,rationale:str)->IdentityReviewBatch:
    batch=session.get(IdentityReviewBatch,batch_id)
    if not batch or batch.status!="FROZEN" or len(rationale.strip())<10:raise IdentityReviewAssignmentError("open identity batch and substantive rationale are required")
    batch.status="CLOSED"
    for assignment in session.scalars(select(IdentityReviewAssignment).where(IdentityReviewAssignment.batch_id==batch.id,IdentityReviewAssignment.status=="ACTIVE")):
        assignment.status="REVOKED";assignment.revoked_by=actor;assignment.revocation_reason="Batch closed: "+rationale.strip();session.add(IdentityReviewAssignmentEvent(assignment_id=assignment.id,action="BATCH_CLOSE",prior_state="ACTIVE",resulting_state="REVOKED",actor=actor,rationale=rationale.strip()))
    append_ledger_event(session,"IDENTITY_REVIEW_BATCH",batch.id,actor,"ADMIN","BATCH_CLOSED",{"rationale":rationale.strip()});session.flush();return batch

def require_identity_assignment(session,batch_id:int,reviewer:str,reviewer_role:str,approval:bool=False)->IdentityReviewAssignment:
    assignment=session.scalar(select(IdentityReviewAssignment).where(IdentityReviewAssignment.batch_id==batch_id,IdentityReviewAssignment.reviewer==reviewer,IdentityReviewAssignment.status=="ACTIVE"))
    if not assignment or _aware(assignment.expires_at)<=_now():
        if assignment:
            assignment.status="EXPIRED";session.add(IdentityReviewAssignmentEvent(assignment_id=assignment.id,action="EXPIRE",prior_state="ACTIVE",resulting_state="EXPIRED",actor="authorization-check",rationale="Assignment reached its bounded expiry"));append_ledger_event(session,"IDENTITY_REVIEW_ASSIGNMENT",assignment.id,"authorization-check","SYSTEM","EXPIRE",{"batch_id":assignment.batch_id});session.flush()
        raise IdentityReviewAssignmentError("active unexpired identity assignment is required")
    if assignment.reviewer_role!=reviewer_role.upper() or (approval and assignment.reviewer_role not in APPROVER_ROLES):raise IdentityReviewAssignmentError("identity assignment role does not authorize this action")
    return assignment

def expire_identity_assignments(session,actor:str="identity-assignment-expiry-worker")->dict:
    rows=session.scalars(select(IdentityReviewAssignment).where(IdentityReviewAssignment.status=="ACTIVE")).all();expired=0
    for assignment in rows:
        if _aware(assignment.expires_at)>_now():continue
        assignment.status="EXPIRED";session.add(IdentityReviewAssignmentEvent(assignment_id=assignment.id,action="EXPIRE",prior_state="ACTIVE",resulting_state="EXPIRED",actor=actor,rationale="Assignment reached its bounded expiry"));append_ledger_event(session,"IDENTITY_REVIEW_ASSIGNMENT",assignment.id,actor,"SYSTEM","EXPIRE",{"batch_id":assignment.batch_id});expired+=1
    session.flush();return {"active_examined":len(rows),"expired":expired}
