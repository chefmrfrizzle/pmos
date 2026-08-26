from __future__ import annotations

import hashlib,json,os,secrets
from datetime import datetime,timedelta,timezone
from pathlib import Path
from sqlalchemy import func,select

from .audit_ledger import append_ledger_event
from .db import Contact,LegalHold,LegalHoldEvent,RawImportRow,ResearchDocumentSnapshot,RetentionAssessmentRun,SourceRetrievalAttempt

class RetentionError(ValueError):pass
DISPOSABLE={
    "RAW_IMPORT":{"model":RawImportRow,"timestamp":"imported_at"},
    "CONTACT_DATA":{"model":Contact,"timestamp":"last_verified"},
    "RESEARCH_CACHE":{"model":ResearchDocumentSnapshot,"timestamp":"retrieved_at"},
    "RETRIEVAL_TELEMETRY":{"model":SourceRetrievalAttempt,"timestamp":"occurred_at"},
}
PROTECTED=("AUDIT_LEDGER","ADJUDICATION_HISTORY","IDENTITY_GRAPH","RELATIONSHIP_GRAPH","TRANSACTION_CASES","CLAIMS_AND_EVIDENCE")
def _canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def _scope_hash(scope_type,scope_reference):return hashlib.sha256(f"{scope_type.upper()}|{scope_reference.upper()}".encode()).hexdigest()

def load_retention_policy(path:Path,repo_root:Path)->tuple[dict,str]:
    expanded=path.expanduser()
    if expanded.is_symlink():raise RetentionError("retention policy must not be a symlink")
    resolved=expanded.resolve(strict=True);repo=repo_root.resolve()
    if repo==resolved or repo in resolved.parents or not resolved.is_file():raise RetentionError("retention policy must be a regular file outside the public repository")
    if resolved.stat().st_size>100_000:raise RetentionError("retention policy exceeds size limit")
    try:policy=json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:raise RetentionError("retention policy is not valid UTF-8 JSON") from exc
    if set(policy)!={"version","status","approved_by","approved_at","classes"} or policy["status"]!="APPROVED" or not str(policy["approved_by"]).strip():raise RetentionError("retention policy is not approved or has unexpected fields")
    try:approved=datetime.fromisoformat(str(policy["approved_at"]).replace("Z","+00:00"))
    except ValueError as exc:raise RetentionError("retention policy approval timestamp is invalid") from exc
    if not approved.tzinfo or approved>datetime.now(timezone.utc)+timedelta(minutes=5):raise RetentionError("retention policy approval timestamp must be timezone-aware and not future-dated")
    classes=policy["classes"]
    if set(classes)!=set(DISPOSABLE):raise RetentionError("retention policy must configure every disposable data class exactly once")
    for name,entry in classes.items():
        if set(entry)!={"retention_days","disposition"} or entry["disposition"]!="REVIEW_DELETE" or not isinstance(entry["retention_days"],int) or not 30<=entry["retention_days"]<=3650:raise RetentionError(f"invalid retention rule for {name}")
    canonical=_canonical(policy);return policy,hashlib.sha256(canonical.encode()).hexdigest()

def build_retention_assessment(session,repo_root:Path,policy_path:Path|None=None)->dict:
    now=datetime.now(timezone.utc);policy=None;policy_hash=None;configuration_error=None
    requested=policy_path or (Path(os.environ["PMOS_RETENTION_POLICY_PATH"]) if os.getenv("PMOS_RETENTION_POLICY_PATH") else None)
    if requested:
        try:policy,policy_hash=load_retention_policy(requested,repo_root)
        except RetentionError as exc:configuration_error=str(exc)
        except OSError:configuration_error="retention policy file is unavailable"
    else:configuration_error="PMOS_RETENTION_POLICY_PATH is not configured"
    classes=[];total_due=0
    for name,spec in DISPOSABLE.items():
        model=spec["model"];column=getattr(model,spec["timestamp"]);population=session.scalar(select(func.count()).select_from(model)) or 0;rule=policy["classes"][name] if policy else None;age_eligible=0
        if rule:age_eligible=session.scalar(select(func.count()).select_from(model).where(column.is_not(None),column<=now-timedelta(days=rule["retention_days"]))) or 0
        hold=session.scalar(select(LegalHold).where(LegalHold.scope_type=="DATA_CLASS",LegalHold.scope_reference_hash==_scope_hash("DATA_CLASS",name),LegalHold.status=="ACTIVE"));due=0 if hold else age_eligible;total_due+=due
        classes.append({"data_class":name,"population":population,"timestamp_field":spec["timestamp"],"retention_days":rule["retention_days"] if rule else None,"disposition":rule["disposition"] if rule else "NOT_CONFIGURED","age_eligible_count":age_eligible,"active_class_hold":bool(hold),"disposition_review_count":due})
    status="NOT_CONFIGURED" if not policy else "REVIEW_REQUIRED" if total_due else "NO_RECORDS_DUE"
    return {"classification":"PMOS PRIVATE AGGREGATE RETENTION ASSESSMENT — NO RECORD VALUES","generated_at":now.isoformat(),"status":status,"method":"retention_dry_run_v1","policy_hash":policy_hash,"configuration_error":configuration_error,"protected_classes":list(PROTECTED),"classes":classes,"summary":{"disposable_population":sum(x["population"] for x in classes),"disposition_review_count":total_due,"active_class_holds":sum(x["active_class_hold"] for x in classes)},"limitations":["Dry-run only; this module contains no deletion operation.","Record-specific holds and downstream replicas require separate disposition review.","Policy approval metadata is not a cryptographic signature."]}

def persist_retention_assessment(session,report:dict,actor:str="retention-assessment-worker"):
    canonical=_canonical(report);digest=hashlib.sha256(canonical.encode()).hexdigest();existing=session.scalar(select(RetentionAssessmentRun).where(RetentionAssessmentRun.report_hash==digest))
    if existing:return existing
    run=RetentionAssessmentRun(status=report["status"],policy_hash=report["policy_hash"],report_hash=digest,report_json=canonical,actor=actor);session.add(run);session.flush();append_ledger_event(session,"RETENTION_ASSESSMENT",run.id,actor,"SYSTEM","ASSESSMENT_RECORDED",{"status":run.status,"policy_hash":run.policy_hash,"report_hash":digest,"summary":report["summary"]});return run

def propose_class_legal_hold(session,data_class:str,creator:str,reason:str):
    name=data_class.upper()
    if name not in DISPOSABLE or not creator.strip() or len(reason.strip())<10:raise RetentionError("valid class, creator, and substantive reason are required")
    digest=_scope_hash("DATA_CLASS",name);active=session.scalar(select(LegalHold).where(LegalHold.scope_type=="DATA_CLASS",LegalHold.scope_reference_hash==digest,LegalHold.status.in_({"PROPOSED","ACTIVE"})))
    if active:raise RetentionError("a proposed or active legal hold already covers this data class")
    hold=LegalHold(scope_type="DATA_CLASS",scope_reference_hash=digest,reason=reason.strip(),created_by=creator.strip(),status="PROPOSED");session.add(hold);session.flush();session.add(LegalHoldEvent(legal_hold_id=hold.id,action="PROPOSE",actor=creator.strip(),rationale=reason.strip(),prior_state=None,resulting_state="PROPOSED"));append_ledger_event(session,"LEGAL_HOLD",hold.id,creator.strip(),"COUNSEL","PROPOSE",{"scope_type":"DATA_CLASS","scope_reference_hash":digest});return hold

def adjudicate_legal_hold(session,hold_id:int,action:str,actor:str,rationale:str,expected_status:str):
    hold=session.get(LegalHold,hold_id)
    actor=actor.strip()
    if not hold or hold.status!=expected_status or not actor or len(rationale.strip())<10:raise RetentionError("hold changed or actor or substantive rationale is missing")
    action=action.upper();prior=hold.status
    if prior=="PROPOSED" and action in {"APPROVE","REJECT"}:
        if actor==hold.created_by:raise RetentionError("independent hold approver required")
        result="ACTIVE" if action=="APPROVE" else "REJECTED"
        if action=="APPROVE":hold.approved_by=actor.strip()
    elif prior=="ACTIVE" and action=="RELEASE":
        if actor in {hold.created_by,hold.approved_by}:raise RetentionError("independent hold releaser required")
        result="RELEASED";hold.released_by=actor.strip();hold.released_at=datetime.now(timezone.utc)
    else:raise RetentionError("unsupported legal hold transition")
    hold.status=result;session.add(LegalHoldEvent(legal_hold_id=hold.id,action=action,actor=actor.strip(),rationale=rationale.strip(),prior_state=prior,resulting_state=result));append_ledger_event(session,"LEGAL_HOLD",hold.id,actor.strip(),"COUNSEL",action,{"scope_type":hold.scope_type,"scope_reference_hash":hold.scope_reference_hash,"prior_state":prior,"resulting_state":result});return hold

def build_legal_hold_packet(session,hold_id:int)->dict:
    hold=session.get(LegalHold,hold_id)
    if not hold:raise RetentionError("unknown legal hold")
    data_class=next((name for name in DISPOSABLE if secrets.compare_digest(_scope_hash("DATA_CLASS",name),hold.scope_reference_hash)),None);events=session.scalars(select(LegalHoldEvent).where(LegalHoldEvent.legal_hold_id==hold.id).order_by(LegalHoldEvent.id)).all()
    return {"classification":"PRIVATE—AUTHORIZED RETENTION GOVERNANCE","id":hold.id,"scope_type":hold.scope_type,"data_class":data_class,"scope_reference_hash":hold.scope_reference_hash,"status":hold.status,"reason":hold.reason,"created_by":hold.created_by,"approved_by":hold.approved_by,"released_by":hold.released_by,"created_at":hold.created_at.isoformat(),"released_at":hold.released_at.isoformat() if hold.released_at else None,"history":[{"action":x.action,"actor":x.actor,"rationale":x.rationale,"prior_state":x.prior_state,"resulting_state":x.resulting_state,"occurred_at":x.occurred_at.isoformat()} for x in events]}
