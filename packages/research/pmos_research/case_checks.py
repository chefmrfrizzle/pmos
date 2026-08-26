from __future__ import annotations

from datetime import datetime,timezone
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import Claim,ClaimEvidence,CheckResult,ConflictCase,DiligenceCase,DiligenceCheckAdjudicationEvent,DiligenceCheckEvidence,EvidencePassage,SourceDocument

class CheckAdjudicationError(ValueError):pass
QUALIFYING_STATUSES={"SUPPORTED","CORROBORATED","SPECIALIST_VERIFIED"}

def _check_case(session,check_id:int):
    check=session.get(CheckResult,check_id)
    if not check:raise CheckAdjudicationError("unknown diligence check")
    case=session.get(DiligenceCase,check.case_id)
    if not case:raise CheckAdjudicationError("unknown diligence case")
    return check,case

def submit_check_evidence(session,check_id:int,claim_ids,actor:str,rationale:str):
    check,case=_check_case(session,check_id);ids=sorted(set(int(x) for x in claim_ids))
    if not ids or not actor.strip() or not rationale.strip():raise CheckAdjudicationError("claims, actor, and rationale are required")
    claims=session.scalars(select(Claim).where(Claim.id.in_(ids))).all()
    if len(claims)!=len(ids) or any(x.entity_id!=case.entity_id for x in claims):raise CheckAdjudicationError("all claims must belong to the case entity")
    existing=set(session.scalars(select(DiligenceCheckEvidence.claim_id).where(DiligenceCheckEvidence.check_id==check.id)).all())
    for claim in claims:
        if claim.id not in existing:session.add(DiligenceCheckEvidence(check_id=check.id,claim_id=claim.id,added_by=actor))
    prior=check.status
    if prior=="NOT_STARTED":check.status="EVIDENCE_COLLECTED"
    append_ledger_event(session,"DILIGENCE_CHECK",check.id,actor,"RESEARCHER","EVIDENCE_ATTACHED",{"claim_ids":ids,"prior_state":prior,"resulting_state":check.status,"rationale":rationale})
    session.flush();return check

def evidence_sufficiency(session,check_id:int)->dict:
    check,case=_check_case(session,check_id)
    claims=session.scalars(select(Claim).join(DiligenceCheckEvidence,DiligenceCheckEvidence.claim_id==Claim.id).where(DiligenceCheckEvidence.check_id==check.id)).all()
    claim_ids=[x.id for x in claims if x.verification_status in QUALIFYING_STATUSES]
    documents=session.scalars(select(SourceDocument).join(EvidencePassage,EvidencePassage.document_id==SourceDocument.id).join(ClaimEvidence,ClaimEvidence.passage_id==EvidencePassage.id).where(ClaimEvidence.claim_id.in_(claim_ids))).unique().all() if claim_ids else []
    ranks={x.source_rank for x in documents};independence={x.publisher_independence_group for x in documents if x.source_rank in {"S0","S1","S2","S3"}}
    dispositive="S0" in ranks;corroborated=len(independence)>=2 and bool(ranks & {"S1","S2"})
    status_ok=bool(claim_ids);sufficient=status_ok and (dispositive or corroborated)
    conflicts=session.scalars(select(ConflictCase).where(ConflictCase.entity_id==case.entity_id,ConflictCase.predicate==check.fact_class,ConflictCase.status!="RESOLVED")).all()
    return {"sufficient":sufficient and not conflicts,"qualifying_claim_ids":sorted(claim_ids),"source_ranks":sorted(ranks),"independence_groups":sorted(independence),"unresolved_conflict_ids":sorted(x.id for x in conflicts)}

def adjudicate_check(session,check_id:int,action:str,reviewer:str,rationale:str,expected_status:str|None=None):
    check,case=_check_case(session,check_id)
    if not reviewer.strip() or not rationale.strip():raise CheckAdjudicationError("reviewer and rationale are required")
    if expected_status is not None and check.status!=expected_status:raise CheckAdjudicationError("check changed; reload before deciding")
    action=action.upper();prior=check.status
    transitions={
        "EVIDENCE_COLLECTED":{"PROPOSE_COMPLETE":"REVIEW_PROPOSED","PROPOSE_EXCEPTION":"EXCEPTION_PROPOSED","REJECT":"REJECTED"},
        "REVIEW_PROPOSED":{"APPROVE":"SPECIALIST_VERIFIED","REJECT":"EVIDENCE_COLLECTED"},
        "EXCEPTION_PROPOSED":{"APPROVE_EXCEPTION":"EXCEPTED","REJECT":"EVIDENCE_COLLECTED"},
    }
    if action not in transitions.get(prior,{}):raise CheckAdjudicationError(f"invalid transition {prior} -> {action}")
    if action in {"PROPOSE_COMPLETE","APPROVE"}:
        result=evidence_sufficiency(session,check.id)
        if not result["sufficient"]:raise CheckAdjudicationError("evidence does not meet independent-source or conflict policy")
    events=session.scalars(select(DiligenceCheckAdjudicationEvent).where(DiligenceCheckAdjudicationEvent.check_id==check.id).order_by(DiligenceCheckAdjudicationEvent.id)).all()
    if action in {"APPROVE","APPROVE_EXCEPTION"}:
        proposal_action="PROPOSE_COMPLETE" if action=="APPROVE" else "PROPOSE_EXCEPTION"
        proposer=next((x.reviewer for x in reversed(events) if x.action==proposal_action),None)
        if not proposer or proposer==reviewer:raise CheckAdjudicationError("independent approval is required")
    if action=="PROPOSE_EXCEPTION":check.exception_reason=rationale
    result=transitions[prior][action];check.status=result
    if result in {"SPECIALIST_VERIFIED","EXCEPTED"}:check.completed_at=datetime.now(timezone.utc)
    session.add(DiligenceCheckAdjudicationEvent(check_id=check.id,action=action,prior_state=prior,resulting_state=result,reviewer=reviewer,rationale=rationale))
    append_ledger_event(session,"DILIGENCE_CHECK",check.id,reviewer,"REVIEWER",action,{"case_id":case.id,"check_code":check.check_code,"prior_state":prior,"resulting_state":result,"rationale":rationale})
    session.flush();return check
