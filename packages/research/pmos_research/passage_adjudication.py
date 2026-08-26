from __future__ import annotations

import re,secrets

from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import (
    Claim,ClaimEvidence,ConflictCase,ConflictMember,EvidencePassage,
    ResearchPassageAdjudicationEvent,ResearchPassageCandidate,
    ResearchSourceCandidate,SourceDocument,
)

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

def _material_conflicts(session,entity_id:int,predicate:str,value:str)->list[Claim]:
    if predicate not in MATERIAL_SINGLE_VALUE:return []
    claims=session.scalars(select(Claim).where(Claim.entity_id==entity_id,Claim.field==predicate,Claim.verification_status.in_(ACTIVE_CLAIM_STATES))).all()
    return [x for x in claims if not secrets.compare_digest(_normalized(x.value),_normalized(value))]

def _create_claim(session,candidate,source,passage,document,value,status)->Claim:
    claim=Claim(entity_id=source.entity_id,field=candidate.predicate,value=value,source_url=document.source_url,source_type=document.source_type,confidence=candidate.confidence,verification_status=status,extractor="specialist_passage_adjudication_v1",evidence_hash=document.content_hash)
    session.add(claim);session.flush();session.add(ClaimEvidence(claim_id=claim.id,passage_id=passage.id,directness=candidate.confidence,supports=True));session.flush();return claim

def adjudicate_passage(session,candidate_id:int,action:str,reviewer:str,rationale:str,claim_value:str|None=None,expected_status:str|None=None):
    candidate,source,passage,document=_context(session,candidate_id)
    if not reviewer.strip() or len(rationale.strip())<10:raise PassageAdjudicationError("reviewer and substantive rationale are required")
    if expected_status is not None and candidate.status!=expected_status:raise PassageAdjudicationError("passage candidate changed; reload before deciding")
    action=action.upper();prior=candidate.status
    transitions={
        "HUMAN_REVIEW_REQUIRED":{"PROPOSE_SUPPORT":"SUPPORT_PROPOSED","REJECT":"REJECTED","DEFER":"DEFERRED","MARK_CONFLICT":"CONFLICT"},
        "DEFERRED":{"PROPOSE_SUPPORT":"SUPPORT_PROPOSED","REJECT":"REJECTED","MARK_CONFLICT":"CONFLICT"},
        "SUPPORT_PROPOSED":{"APPROVE_SUPPORT":"SUPPORTED","REJECT":"REJECTED","MARK_CONFLICT":"CONFLICT"},
    }
    if action not in transitions.get(prior,{}):raise PassageAdjudicationError(f"invalid transition {prior} -> {action}")
    value=_validate_value(passage.passage,claim_value or "") if action in {"PROPOSE_SUPPORT","APPROVE_SUPPORT","MARK_CONFLICT"} else None
    events=session.scalars(select(ResearchPassageAdjudicationEvent).where(ResearchPassageAdjudicationEvent.passage_candidate_id==candidate.id).order_by(ResearchPassageAdjudicationEvent.id)).all()
    result=transitions[prior][action];claim=None
    conflicts=_material_conflicts(session,source.entity_id,candidate.predicate,value) if value else []
    if action=="PROPOSE_SUPPORT" and conflicts:raise PassageAdjudicationError("material contradiction detected; mark conflict instead of proposing support")
    if action=="APPROVE_SUPPORT":
        proposal=next((x for x in reversed(events) if x.action=="PROPOSE_SUPPORT"),None)
        if not proposal or proposal.reviewer==reviewer:raise PassageAdjudicationError("independent approval is required")
        if not secrets.compare_digest(_normalized(proposal.claim_value or ""),_normalized(value)):raise PassageAdjudicationError("approval must use the exact proposed claim value")
        if conflicts:raise PassageAdjudicationError("material contradiction appeared after proposal; mark conflict")
        claim=_create_claim(session,candidate,source,passage,document,value,"SUPPORTED")
    elif action=="MARK_CONFLICT":
        claim=_create_claim(session,candidate,source,passage,document,value,"CONFLICT")
        conflict=session.scalar(select(ConflictCase).where(ConflictCase.entity_id==source.entity_id,ConflictCase.predicate==candidate.predicate,ConflictCase.status!="RESOLVED").order_by(ConflictCase.id.desc()))
        if not conflict:
            conflict=ConflictCase(entity_id=source.entity_id,predicate=candidate.predicate,materiality="MATERIAL" if candidate.predicate in MATERIAL_SINGLE_VALUE else "NON_MATERIAL",status="HUMAN_REVIEW_REQUIRED");session.add(conflict);session.flush()
        member_ids={x.id for x in conflicts} | {claim.id}
        existing=set(session.scalars(select(ConflictMember.claim_id).where(ConflictMember.conflict_id==conflict.id)).all())
        for claim_id in sorted(member_ids-existing):session.add(ConflictMember(conflict_id=conflict.id,claim_id=claim_id))
    candidate.status=result
    event=ResearchPassageAdjudicationEvent(passage_candidate_id=candidate.id,action=action,prior_state=prior,resulting_state=result,reviewer=reviewer,rationale=rationale.strip(),claim_value=value,resulting_claim_id=claim.id if claim else None);session.add(event)
    append_ledger_event(session,"PASSAGE_REVIEW",candidate.id,reviewer,"REVIEWER",action,{"entity_id":source.entity_id,"predicate":candidate.predicate,"prior_state":prior,"resulting_state":result,"passage_hash":passage.passage_hash,"document_hash":document.content_hash,"claim_value_hash":__import__("hashlib").sha256(value.encode()).hexdigest() if value else None,"resulting_claim_id":claim.id if claim else None,"rationale":rationale.strip()})
    session.flush();return {"candidate_id":candidate.id,"prior_state":prior,"resulting_state":result,"claim_id":claim.id if claim else None}
