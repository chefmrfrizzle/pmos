from __future__ import annotations

import hashlib,json
from urllib.parse import urlparse,parse_qsl
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import CorroborationJob,PrivateEgressReviewCase,PrivateEgressReviewEvent

class PrivateEgressReviewError(ValueError):pass
PROPOSE={"PROPOSE_NO_MATERIAL_DISCLOSURE":"NO_MATERIAL_DISCLOSURE_PROPOSED","PROPOSE_ESCALATION":"ESCALATION_PROPOSED"};APPROVE={"APPROVE_NO_MATERIAL_DISCLOSURE":("NO_MATERIAL_DISCLOSURE_PROPOSED","RESOLVED_NO_MATERIAL_DISCLOSURE"),"APPROVE_ESCALATION":("ESCALATION_PROPOSED","ESCALATED")}
def _canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def _error_type(value):return value.split(":",1)[0][:80] if value else None

def evidence_package(session,case_id:int)->dict:
    case=session.get(PrivateEgressReviewCase,case_id);job=session.get(CorroborationJob,case.corroboration_job_id) if case else None
    if not case or not job:raise PrivateEgressReviewError("private egress case evidence is incomplete")
    parsed=urlparse(job.source_url);path_segments=len([x for x in parsed.path.split("/") if x]);query_count=len(parse_qsl(parsed.query,keep_blank_values=True));package={"case_id":case.id,"job_id":job.id,"prior_status":case.prior_status,"attempts_observed":case.attempts_observed,"request_method":"GET","generic_user_agent":True,"credentials_in_url":bool(parsed.username or parsed.password),"source_domain_hash":hashlib.sha256(job.source_domain.casefold().encode()).hexdigest(),"query_parameter_count":query_count,"path_segment_count":path_segments,"error_type":_error_type(job.last_error),"job_updated_at":job.updated_at.isoformat()}
    digest=hashlib.sha256(_canonical(package).encode()).hexdigest();return {**package,"evidence_package_hash":digest}

def build_private_egress_packet(session,case_id:int)->dict:
    case=session.get(PrivateEgressReviewCase,case_id)
    if not case:raise PrivateEgressReviewError("unknown private egress review case")
    package=evidence_package(session,case.id);events=session.scalars(select(PrivateEgressReviewEvent).where(PrivateEgressReviewEvent.case_id==case.id).order_by(PrivateEgressReviewEvent.id)).all()
    return {"classification":"PRIVATE—AUTHORIZED SECURITY REVIEW; NO ENTITY NAME OR URL","id":case.id,"status":case.status,"reason":case.reason,"evidence":package,"history":[{"action":x.action,"actor":x.actor,"actor_role":x.actor_role,"rationale":x.rationale,"prior_state":x.prior_state,"resulting_state":x.resulting_state,"evidence_package_hash":x.evidence_package_hash,"occurred_at":x.occurred_at.isoformat()} for x in events]}

def adjudicate_private_egress(session,case_id:int,action:str,actor:str,actor_role:str,rationale:str,expected_status:str):
    case=session.get(PrivateEgressReviewCase,case_id);action=action.upper();actor=actor.strip();role=actor_role.upper();rationale=rationale.strip()
    if not case or case.status!=expected_status or not actor or role not in {"ADMIN","COUNSEL"} or len(rationale)<20:raise PrivateEgressReviewError("case changed or actor, role, or substantive rationale is invalid")
    package=evidence_package(session,case.id);prior=case.status
    if action in PROPOSE and prior=="OPEN":result=PROPOSE[action]
    elif action in APPROVE and prior==APPROVE[action][0]:
        proposal=session.scalar(select(PrivateEgressReviewEvent).where(PrivateEgressReviewEvent.case_id==case.id,PrivateEgressReviewEvent.resulting_state==prior).order_by(PrivateEgressReviewEvent.id.desc()))
        if not proposal or proposal.actor==actor or proposal.evidence_package_hash!=package["evidence_package_hash"]:raise PrivateEgressReviewError("independent approval of the unchanged evidence package is required")
        if action=="APPROVE_NO_MATERIAL_DISCLOSURE" and (package["credentials_in_url"] or package["query_parameter_count"]):raise PrivateEgressReviewError("URL metadata requires escalation rather than no-material-disclosure closure")
        result=APPROVE[action][1]
    else:raise PrivateEgressReviewError("unsupported private egress review transition")
    case.status=result;session.add(PrivateEgressReviewEvent(case_id=case.id,action=action,actor=actor,actor_role=role,rationale=rationale,prior_state=prior,resulting_state=result,evidence_package_hash=package["evidence_package_hash"]));append_ledger_event(session,"PRIVATE_EGRESS_REVIEW",case.id,actor,role,action,{"prior_state":prior,"resulting_state":result,"evidence_package_hash":package["evidence_package_hash"]});return case
