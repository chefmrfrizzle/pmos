from __future__ import annotations

import hashlib,json,os
from datetime import datetime,timedelta,timezone
from pathlib import Path
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import EvidenceReviewBatch,IdentityReviewBatch,RelationshipMentionReviewBatch,ReviewerRosterAssessmentRun

class ReviewerRosterError(ValueError):pass
ROLES={"RESEARCHER","REVIEWER","COUNSEL","ADMIN"};WRITE={"evidence:write","identity:write","relationships:write"};APPROVE={"evidence:approve","identity:approve","relationships:approve"};ASSIGN={"evidence:assign","identity:assign"}
def _canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def load_reviewer_roster(path:Path,repo_root:Path)->tuple[dict,str]:
    expanded=path.expanduser()
    if expanded.is_symlink():raise ReviewerRosterError("reviewer roster must not be a symlink")
    resolved=expanded.resolve(strict=True);repo=repo_root.resolve()
    if repo==resolved or repo in resolved.parents or not resolved.is_file():raise ReviewerRosterError("reviewer roster must be a regular file outside the public repository")
    if resolved.stat().st_size>100_000:raise ReviewerRosterError("reviewer roster exceeds size limit")
    try:value=json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:raise ReviewerRosterError("reviewer roster is not valid UTF-8 JSON") from exc
    if set(value)!={"version","status","approved_by","approved_at","tenant_id","reviewers"} or value["status"]!="APPROVED" or not str(value["approved_by"]).strip() or not str(value["tenant_id"]).strip():raise ReviewerRosterError("reviewer roster is not approved or has unexpected fields")
    try:approved=datetime.fromisoformat(str(value["approved_at"]).replace("Z","+00:00"))
    except ValueError as exc:raise ReviewerRosterError("reviewer roster approval timestamp is invalid") from exc
    if not approved.tzinfo or approved>datetime.now(timezone.utc)+timedelta(minutes=5) or approved<datetime.now(timezone.utc)-timedelta(days=365):raise ReviewerRosterError("reviewer roster approval must be timezone-aware and current")
    if not isinstance(value["reviewers"],list) or not 3<=len(value["reviewers"])<=100:raise ReviewerRosterError("reviewer roster must contain 3 to 100 entries")
    subjects=set()
    for item in value["reviewers"]:
        if set(item)!={"subject","roles","permissions","universes","purposes","status"}:raise ReviewerRosterError("reviewer entry has unexpected fields")
        subject=str(item["subject"]).strip();roles=set(item["roles"]);permissions=set(item["permissions"]);universes=set(item["universes"]);purposes=set(item["purposes"])
        if not subject or subject in subjects or item["status"]!="ACTIVE" or not roles or not roles<=ROLES or not permissions or not universes or not purposes or "*" in permissions|universes|purposes:raise ReviewerRosterError("reviewer entry violates identity, role, scope, or wildcard policy")
        if "RESEARCHER" in roles and permissions&APPROVE:raise ReviewerRosterError("researcher entries cannot carry approval permissions")
        if roles&{"REVIEWER","COUNSEL"} and permissions&WRITE:raise ReviewerRosterError("checker entries cannot carry maker permissions")
        if "ADMIN" in roles and permissions&(WRITE|APPROVE):raise ReviewerRosterError("assignment administrators cannot make or approve decisions")
        subjects.add(subject)
    canonical=_canonical(value);return value,hashlib.sha256(canonical.encode()).hexdigest()

def _required_batches(session):
    mapping=[]
    for model,kind,maker,checker,assigner in ((EvidenceReviewBatch,"EVIDENCE","evidence:write","evidence:approve","evidence:assign"),(IdentityReviewBatch,"IDENTITY","identity:write","identity:approve","identity:assign"),(RelationshipMentionReviewBatch,"MENTION_IDENTITY","identity:write","identity:approve","identity:assign")):
        for batch in session.scalars(select(model).where(model.status=="FROZEN")):
            criteria=json.loads(batch.criteria_json);mapping.append((kind,str(criteria["universe"]),batch.item_count,maker,checker,assigner))
    return mapping

def build_reviewer_roster_assessment(session,repo_root:Path,roster_path:Path|None=None)->dict:
    requested=roster_path or (Path(os.environ["PMOS_REVIEWER_ROSTER_PATH"]) if os.getenv("PMOS_REVIEWER_ROSTER_PATH") else None);roster=None;roster_hash=None;error=None
    if requested:
        try:roster,roster_hash=load_reviewer_roster(requested,repo_root)
        except (ReviewerRosterError,OSError) as exc:error=str(exc) if isinstance(exc,ReviewerRosterError) else "reviewer roster file is unavailable"
    else:error="PMOS_REVIEWER_ROSTER_PATH is not configured"
    batches=_required_batches(session);gaps=[];reviewers=roster["reviewers"] if roster else []
    for kind,universe,item_count,maker_permission,checker_permission,assign_permission in batches:
        def eligible(permission,role):return [x for x in reviewers if universe in x["universes"] and permission in x["permissions"] and role in x["roles"]]
        makers=eligible(maker_permission,"RESEARCHER");checkers=[x for x in reviewers if universe in x["universes"] and checker_permission in x["permissions"] and set(x["roles"])&{"REVIEWER","COUNSEL"}];assigners=eligible(assign_permission,"ADMIN");separated=bool(makers and checkers and assigners and len({makers[0]["subject"],checkers[0]["subject"],assigners[0]["subject"]})==3)
        if not separated:gaps.append({"workflow":kind,"universe":universe,"item_count":item_count,"maker_available":bool(makers),"checker_available":bool(checkers),"independent_assigner_available":bool(assigners),"three_way_separation":separated})
    status="NOT_CONFIGURED" if not roster else "READY" if not gaps else "GAPS_IDENTIFIED"
    return {"classification":"PMOS PRIVATE AGGREGATE REVIEWER STAFFING ASSESSMENT — NO SUBJECT IDENTITIES","generated_at":datetime.now(timezone.utc).isoformat(),"status":status,"method":"reviewer_roster_preflight_v1","roster_hash":roster_hash,"configuration_error":error,"reviewer_count":len(reviewers),"frozen_batch_count":len(batches),"frozen_item_count":sum(x[2] for x in batches),"gap_count":len(gaps),"gaps":gaps,"limitations":["Roster approval metadata is not a cryptographic signature.","READY proves configuration and separation only; active assignments and completed adjudications are separate operating evidence."]}

def persist_reviewer_roster_assessment(session,report:dict,actor:str="reviewer-roster-worker"):
    canonical=_canonical(report);digest=hashlib.sha256(canonical.encode()).hexdigest();run=ReviewerRosterAssessmentRun(status=report["status"],roster_hash=report["roster_hash"],report_hash=digest,report_json=canonical,actor=actor);session.add(run);session.flush();append_ledger_event(session,"REVIEWER_ROSTER_ASSESSMENT",run.id,actor,"SYSTEM","ASSESSMENT_RECORDED",{"status":run.status,"report_hash":digest,"roster_hash":run.roster_hash,"reviewer_count":report["reviewer_count"],"gap_count":report["gap_count"]});return run
