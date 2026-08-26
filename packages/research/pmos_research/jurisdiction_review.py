from __future__ import annotations

from datetime import datetime,timezone
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import Claim,Entity,JurisdictionReviewCase,JurisdictionReviewEvent

VALID_CLAIM_STATES={"SUPPORTED","CORROBORATED","SPECIALIST_VERIFIED"}
VALID_PREDICATES={"country","jurisdiction","domicile"}

class JurisdictionReviewError(ValueError):pass

def valid_country(value:str|None)->bool:
    return bool(value and len(value)==2 and value.isalpha() and value.upper()==value)

def enqueue_invalid_jurisdictions(session)->dict:
    existing=set(session.scalars(select(JurisdictionReviewCase.entity_id)).all())
    invalid=session.scalars(select(Entity).where(Entity.country.is_not(None))).all();created=0
    for entity in invalid:
        if valid_country(entity.country) or entity.id in existing:continue
        session.add(JurisdictionReviewCase(entity_id=entity.id,original_country=entity.country));created+=1
    session.flush()
    if created:append_ledger_event(session,"JURISDICTION_REVIEW","QUEUE","jurisdiction-queue-worker","SYSTEM","INVALID_JURISDICTIONS_QUEUED",{"created":created})
    return {"invalid":sum(not valid_country(x.country) for x in invalid),"created":created}

def build_jurisdiction_packet(session,case_id:int)->dict:
    case=session.get(JurisdictionReviewCase,case_id)
    if not case:raise JurisdictionReviewError("unknown jurisdiction review case")
    entity=session.get(Entity,case.entity_id);claim=session.get(Claim,case.source_claim_id) if case.source_claim_id else None
    return {"id":case.id,"entity":{"id":entity.id,"label":entity.name,"universe":entity.universe},"original_country":case.original_country,"proposed_country":case.proposed_country,"status":case.status,"source_claim":{"id":claim.id,"field":claim.field,"value":claim.value,"source_url":claim.source_url,"verification_status":claim.verification_status,"evidence_hash":claim.evidence_hash} if claim else None,"proposed_by":case.proposed_by,"reviewed_by":case.reviewed_by,"updated_at":case.updated_at.isoformat()}

def adjudicate_jurisdiction(session,case_id:int,action:str,actor:str,rationale:str,source_claim_id:int|None,expected_status:str)->JurisdictionReviewCase:
    case=session.get(JurisdictionReviewCase,case_id)
    if not case:raise JurisdictionReviewError("unknown jurisdiction review case")
    action=action.upper();expected_status=expected_status.upper()
    if case.status!=expected_status:raise JurisdictionReviewError("jurisdiction review state changed; refresh before acting")
    if len(rationale.strip())<10:raise JurisdictionReviewError("a substantive rationale is required")
    prior=case.status
    if action=="PROPOSE_CORRECTION":
        if case.status!="HUMAN_REVIEW_REQUIRED" or not source_claim_id:raise JurisdictionReviewError("correction proposal requires an open case and source claim")
        claim=session.get(Claim,source_claim_id)
        if not claim or claim.entity_id!=case.entity_id or claim.field.casefold() not in VALID_PREDICATES or claim.verification_status.upper() not in VALID_CLAIM_STATES or not claim.evidence_hash:raise JurisdictionReviewError("source claim is not qualifying jurisdiction evidence")
        country=claim.value.strip().upper()
        if not valid_country(country):raise JurisdictionReviewError("source claim must contain an ISO alpha-2 country")
        case.proposed_country=country;case.source_claim_id=claim.id;case.proposed_by=actor;case.status="PROPOSED"
    elif action=="APPROVE_CORRECTION":
        if case.status!="PROPOSED" or not case.proposed_country or not case.source_claim_id:raise JurisdictionReviewError("correction is not ready for approval")
        if case.proposed_by==actor:raise JurisdictionReviewError("maker cannot approve their own correction")
        entity=session.get(Entity,case.entity_id);entity.country=case.proposed_country;case.reviewed_by=actor;case.status="APPROVED"
    elif action=="REJECT":
        if case.status not in {"HUMAN_REVIEW_REQUIRED","PROPOSED"}:raise JurisdictionReviewError("case cannot be rejected from its current state")
        case.reviewed_by=actor;case.status="REJECTED"
    else:raise JurisdictionReviewError("unsupported jurisdiction review action")
    case.rationale=rationale.strip();case.updated_at=datetime.now(timezone.utc)
    session.add(JurisdictionReviewEvent(case_id=case.id,action=action,prior_state=prior,resulting_state=case.status,actor=actor,rationale=case.rationale,source_claim_id=case.source_claim_id))
    session.flush();append_ledger_event(session,"JURISDICTION_REVIEW",case.id,actor,"HUMAN",action,{"prior_state":prior,"resulting_state":case.status,"source_claim_id":case.source_claim_id})
    return case
