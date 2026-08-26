from __future__ import annotations

from datetime import datetime,timezone

from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .case_checks import submit_check_evidence
from .db import (
    Claim,ClaimCheckRoutingCandidate,ClaimCheckRoutingEvent,CheckResult,
    DiligenceCase,Entity,
)

class EvidenceRoutingError(ValueError):pass

def queue_claim_routes(session,claim:Claim,passage_candidate_id:int|None=None)->list[int]:
    if claim.verification_status not in {"SUPPORTED","CORROBORATED","SPECIALIST_VERIFIED"}:return []
    checks=session.scalars(select(CheckResult).join(DiligenceCase,DiligenceCase.id==CheckResult.case_id).where(DiligenceCase.entity_id==claim.entity_id,CheckResult.fact_class==claim.field,CheckResult.status.not_in({"SPECIALIST_VERIFIED","CORROBORATED","EXCEPTED"})).order_by(CheckResult.id)).all()
    result=[]
    for check in checks:
        existing=session.scalar(select(ClaimCheckRoutingCandidate).where(ClaimCheckRoutingCandidate.claim_id==claim.id,ClaimCheckRoutingCandidate.check_id==check.id))
        if existing:result.append(existing.id);continue
        route=ClaimCheckRoutingCandidate(claim_id=claim.id,check_id=check.id,passage_candidate_id=passage_candidate_id,reason=f"claim predicate {claim.field} matches open check fact class");session.add(route);session.flush();result.append(route.id)
        append_ledger_event(session,"EVIDENCE_ROUTE",route.id,"routing-engine","SYSTEM","ROUTE_QUEUED",{"claim_id":claim.id,"check_id":check.id,"case_id":check.case_id,"passage_candidate_id":passage_candidate_id,"predicate":claim.field})
    return result

def route_scope(session,route_id:int):
    route=session.get(ClaimCheckRoutingCandidate,route_id)
    if not route:raise EvidenceRoutingError("unknown routing candidate")
    claim=session.get(Claim,route.claim_id);check=session.get(CheckResult,route.check_id);case=session.get(DiligenceCase,check.case_id) if check else None;entity=session.get(Entity,case.entity_id) if case else None
    if not claim or not check or not case or not entity or claim.entity_id!=entity.id or claim.field!=check.fact_class:raise EvidenceRoutingError("routing candidate scope is invalid")
    return route,claim,check,case,entity

def adjudicate_route(session,route_id:int,action:str,reviewer:str,rationale:str,expected_status:str|None=None):
    route,claim,check,case,entity=route_scope(session,route_id)
    if not reviewer.strip() or len(rationale.strip())<10:raise EvidenceRoutingError("reviewer and substantive rationale are required")
    if expected_status is not None and route.status!=expected_status:raise EvidenceRoutingError("routing candidate changed; reload before deciding")
    action=action.upper();prior=route.status;transitions={"PENDING_REVIEW":{"ATTACH":"ATTACHED","REJECT":"REJECTED","DEFER":"DEFERRED"},"DEFERRED":{"ATTACH":"ATTACHED","REJECT":"REJECTED"}}
    if action not in transitions.get(prior,{}):raise EvidenceRoutingError(f"invalid transition {prior} -> {action}")
    if action=="ATTACH":
        if claim.verification_status not in {"SUPPORTED","CORROBORATED","SPECIALIST_VERIFIED"}:raise EvidenceRoutingError("only supported-or-better claims can be attached")
        submit_check_evidence(session,check.id,[claim.id],reviewer,rationale)
    result=transitions[prior][action];route.status=result;route.updated_at=datetime.now(timezone.utc)
    session.add(ClaimCheckRoutingEvent(routing_candidate_id=route.id,action=action,prior_state=prior,resulting_state=result,reviewer=reviewer,rationale=rationale.strip()))
    append_ledger_event(session,"EVIDENCE_ROUTE",route.id,reviewer,"RESEARCHER",action,{"claim_id":claim.id,"check_id":check.id,"case_id":case.id,"prior_state":prior,"resulting_state":result,"rationale":rationale.strip()})
    session.flush();return {"routing_candidate_id":route.id,"prior_state":prior,"resulting_state":result,"check_id":check.id,"check_status":check.status}
