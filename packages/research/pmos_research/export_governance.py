from __future__ import annotations

import hashlib,json,os,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path

from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .backup import encrypted_storage_active
from .db import ControlAssuranceRun,DiligenceCase,ExportRequest,ExportRequestEvent
from .dossier import build_dossier

class ExportGovernanceError(ValueError):pass

def _utc(value:datetime)->datetime:return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
def _normalized(value:str)->str:return " ".join(value.casefold().split())
def _inside(path:Path,parent:Path)->bool:
    try:path.relative_to(parent);return True
    except ValueError:return False

def request_dossier_export(session,case_id:int,purpose:str,requester:str,expires_hours:int=24)->ExportRequest:
    case=session.get(DiligenceCase,case_id)
    if not case:raise ExportGovernanceError("unknown diligence case")
    if not requester.strip() or not purpose.strip():raise ExportGovernanceError("requester and purpose are required")
    if _normalized(purpose)!=_normalized(case.permitted_use):raise ExportGovernanceError("export purpose must exactly match the case permitted use")
    hours=max(1,min(int(expires_hours),72));now=datetime.now(timezone.utc)
    request=ExportRequest(case_id=case.id,scope="DILIGENCE_DOSSIER",format="JSON",purpose=purpose.strip(),requester=requester.strip(),expires_at=now+timedelta(hours=hours));session.add(request);session.flush()
    session.add(ExportRequestEvent(export_request_id=request.id,action="REQUEST",prior_state="NONE",resulting_state="REQUESTED",actor=requester.strip(),rationale="Scoped diligence dossier export requested"))
    append_ledger_event(session,"EXPORT_REQUEST",request.id,requester.strip(),"REQUESTER","REQUESTED",{"case_id":case.id,"scope":request.scope,"format":request.format,"purpose":request.purpose,"expires_at":request.expires_at.isoformat()})
    return request

def adjudicate_export_request(session,request_id:int,action:str,reviewer:str,rationale:str,expected_status:str|None=None)->ExportRequest:
    request=session.get(ExportRequest,request_id)
    if not request:raise ExportGovernanceError("unknown export request")
    if not reviewer.strip() or len(rationale.strip())<10:raise ExportGovernanceError("reviewer and substantive rationale are required")
    if expected_status is not None and request.status!=expected_status:raise ExportGovernanceError("export request changed; reload before deciding")
    if request.status!="REQUESTED" or action.upper() not in {"APPROVE","REJECT"}:raise ExportGovernanceError("invalid export decision")
    if reviewer.strip()==request.requester:raise ExportGovernanceError("independent export approval is required")
    now=datetime.now(timezone.utc)
    if _utc(request.expires_at)<=now:raise ExportGovernanceError("export request expired")
    if action.upper()=="APPROVE":
        assurance=session.scalar(select(ControlAssuranceRun).order_by(ControlAssuranceRun.created_at.desc(),ControlAssuranceRun.id.desc()))
        if not assurance or assurance.status!="PASS" or _utc(assurance.created_at)<now-timedelta(hours=24):raise ExportGovernanceError("a passing private assurance run from the last 24 hours is required")
        result="APPROVED";request.approved_by=reviewer.strip();request.approved_at=now
    else:result="REJECTED"
    prior=request.status;request.status=result;session.add(ExportRequestEvent(export_request_id=request.id,action=action.upper(),prior_state=prior,resulting_state=result,actor=reviewer.strip(),rationale=rationale.strip()))
    append_ledger_event(session,"EXPORT_REQUEST",request.id,reviewer.strip(),"EXPORT_APPROVER",action.upper(),{"case_id":request.case_id,"prior_state":prior,"resulting_state":result,"rationale":rationale.strip()});session.flush();return request

def execute_export(session,request_id:int,actor:str,private_root:Path,repo_root:Path,require_encrypted_storage:bool=True)->dict:
    request=session.get(ExportRequest,request_id)
    if not request or request.status!="APPROVED":raise ExportGovernanceError("export request is not approved")
    if not actor.strip() or actor.strip()==request.requester:raise ExportGovernanceError("approved independent executor is required")
    now=datetime.now(timezone.utc)
    if _utc(request.expires_at)<=now:raise ExportGovernanceError("export approval expired")
    if require_encrypted_storage and not encrypted_storage_active():raise ExportGovernanceError("encrypted storage could not be verified")
    root=private_root.expanduser()
    if root.exists() and root.is_symlink():raise ExportGovernanceError("private root cannot be a symlink")
    root=root.resolve();repo=repo_root.resolve()
    if _inside(root,repo):raise ExportGovernanceError("private root cannot be inside the public repository")
    out=root/"exports";out.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(out,0o700)
    if out.is_symlink() or out.parent!=root:raise ExportGovernanceError("export directory is unsafe")
    dossier=build_dossier(session,request.case_id,include_passages=True);payload=json.dumps(dossier,indent=2,sort_keys=True,ensure_ascii=False)+"\n";digest=hashlib.sha256(payload.encode()).hexdigest();token=uuid.uuid4().hex[:12]
    artifact=out/f"dossier-request-{request.id}-{token}.json";manifest=out/f"dossier-request-{request.id}-{token}.manifest.json";temp=out/f".{artifact.name}.tmp"
    try:
        temp.write_text(payload,encoding="utf-8");os.chmod(temp,0o600);temp.replace(artifact);os.chmod(artifact,0o600)
        metadata={"classification":"PMOS PRIVATE — APPROVED DILIGENCE EXPORT","request_id":request.id,"case_id":request.case_id,"scope":request.scope,"format":request.format,"purpose":request.purpose,"approved_by":request.approved_by,"executed_by":actor.strip(),"created_at":now.isoformat(),"approval_expires_at":_utc(request.expires_at).isoformat(),"artifact_file":artifact.name,"bytes":artifact.stat().st_size,"sha256":digest}
        manifest.write_text(json.dumps(metadata,indent=2,sort_keys=True)+"\n",encoding="utf-8");os.chmod(manifest,0o600)
        if hashlib.sha256(artifact.read_bytes()).hexdigest()!=digest:raise ExportGovernanceError("export artifact verification failed")
        prior=request.status;request.status="EXPORTED";request.executed_by=actor.strip();request.executed_at=now;request.artifact_name=artifact.name;request.artifact_sha256=digest
        session.add(ExportRequestEvent(export_request_id=request.id,action="EXECUTE",prior_state=prior,resulting_state="EXPORTED",actor=actor.strip(),rationale="Approved dossier export generated on encrypted private storage"))
        append_ledger_event(session,"EXPORT_REQUEST",request.id,actor.strip(),"EXPORT_EXECUTOR","EXPORTED",{"case_id":request.case_id,"artifact_name":artifact.name,"manifest_name":manifest.name,"sha256":digest,"bytes":artifact.stat().st_size});session.flush();session.commit()
        return {"artifact":artifact,"manifest":manifest,"sha256":digest,"bytes":artifact.stat().st_size}
    except Exception:
        for path in (temp,artifact,manifest):
            if path.exists():path.unlink()
        raise
