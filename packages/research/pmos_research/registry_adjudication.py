from __future__ import annotations

from datetime import datetime,timezone
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import Claim,ClaimEvidence,IdentifierAdjudicationEvent,LegalIdentifier,RegistryIdentifierCandidate

class IdentifierAdjudicationError(ValueError):pass

def _identity_is_supported(session,entity_id:int)->bool:
    return bool(session.scalar(select(Claim.id).join(ClaimEvidence,ClaimEvidence.claim_id==Claim.id).where(Claim.entity_id==entity_id,Claim.field=="official_identity",Claim.verification_status=="SUPPORTED").limit(1)))

def adjudicate_identifier(session,candidate_id:int,action:str,reviewer:str,rationale:str,expected_status:str|None=None):
    if not reviewer.strip() or not rationale.strip():raise IdentifierAdjudicationError("reviewer and rationale are required")
    candidate=session.get(RegistryIdentifierCandidate,candidate_id)
    if not candidate:raise IdentifierAdjudicationError("unknown identifier candidate")
    if expected_status is not None and candidate.status!=expected_status:raise IdentifierAdjudicationError("candidate changed; reload before deciding")
    action=action.upper();prior=candidate.status
    transitions={
        "PENDING_REVIEW":{"PROPOSE_ACCEPTANCE":"PROPOSED_ACCEPTANCE","REJECT":"REJECTED","MARK_CONFLICT":"CONFLICT"},
        "PROPOSED_ACCEPTANCE":{"APPROVE":"ACCEPTED","REJECT":"REJECTED","MARK_CONFLICT":"CONFLICT"},
    }
    if action not in transitions.get(prior,{}):raise IdentifierAdjudicationError(f"invalid transition {prior} -> {action}")
    events=session.scalars(select(IdentifierAdjudicationEvent).where(IdentifierAdjudicationEvent.candidate_id==candidate.id).order_by(IdentifierAdjudicationEvent.id)).all()
    if action=="PROPOSE_ACCEPTANCE":
        if candidate.match_state!="PROBABLE_MATCH":raise IdentifierAdjudicationError("only probable registry matches can be proposed")
        if not _identity_is_supported(session,candidate.entity_id):raise IdentifierAdjudicationError("supported official identity evidence is required")
    if action=="APPROVE":
        proposer=next((x.reviewer for x in reversed(events) if x.action=="PROPOSE_ACCEPTANCE"),None)
        if not proposer or proposer==reviewer:raise IdentifierAdjudicationError("independent approval is required")
        source_claim=session.get(Claim,candidate.claim_id)
        accepted_claim=Claim(entity_id=candidate.entity_id,field=candidate.identifier_type.casefold(),value=candidate.identifier_value,source_url=source_claim.source_url,source_type=source_claim.source_type,confidence=1.0,verification_status="SPECIALIST_VERIFIED",extractor="registry_adjudication_v1",evidence_hash=source_claim.evidence_hash)
        session.add(accepted_claim);session.flush()
        for link in session.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id==source_claim.id)):
            session.add(ClaimEvidence(claim_id=accepted_claim.id,passage_id=link.passage_id,directness=link.directness,supports=link.supports))
        session.add(LegalIdentifier(entity_id=candidate.entity_id,identifier_type=candidate.identifier_type,identifier_value=candidate.identifier_value,jurisdiction=candidate.jurisdiction,status="SPECIALIST_VERIFIED",claim_id=accepted_claim.id))
    result=transitions[prior][action];candidate.status=result
    event=IdentifierAdjudicationEvent(candidate_id=candidate.id,action=action,prior_state=prior,resulting_state=result,reviewer=reviewer,rationale=rationale);session.add(event)
    append_ledger_event(session,"IDENTIFIER_REVIEW",candidate.id,reviewer,"REVIEWER",action,{"prior_state":prior,"resulting_state":result,"identifier_type":candidate.identifier_type,"rationale":rationale})
    session.flush();return candidate
