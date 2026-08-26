from __future__ import annotations

import hashlib,json,os,tempfile
from datetime import datetime,timezone
from pathlib import Path
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .backup import BackupSafetyError,encrypted_storage_active,restore_private_backup,verify_backup_manifest,verify_sqlite_database
from .db import RestoreDrillRun

class RestoreDrillError(RuntimeError):pass

def _canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def run_restore_drill(session,manifest_path:Path,repo_root:Path,actor:str="restore-drill-worker")->tuple[RestoreDrillRun,dict]:
    actor=actor.strip()
    if not actor:raise RestoreDrillError("restore drill actor is required")
    if not encrypted_storage_active():raise RestoreDrillError("encrypted storage could not be verified")
    try:verified=verify_backup_manifest(manifest_path,repo_root)
    except BackupSafetyError as exc:raise RestoreDrillError(str(exc)) from exc
    drill_root=verified["manifest"].parent.parent/"restore-drills"
    if drill_root.exists() and drill_root.is_symlink():raise RestoreDrillError("restore drill root cannot be a symlink")
    drill_root.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(drill_root,0o700)
    target=None
    try:
        work=Path(tempfile.mkdtemp(prefix="pmos-restore-drill-",dir=drill_root));os.chmod(work,0o700);target=work/"restored.db"
        restored=restore_private_backup(verified["manifest"],target,repo_root,require_encrypted_storage=True)
        check=verify_sqlite_database(restored["target"])
        if check["integrity"]!="ok" or not check["ledger"]["valid"] or restored["sha256"]!=verified["metadata"]["sha256"]:raise RestoreDrillError("restored artifact failed integrity verification")
        target.unlink();work.rmdir();removed=not target.exists() and not work.exists()
    except Exception:
        if target and target.exists():target.unlink()
        if target and target.parent.exists():target.parent.rmdir()
        raise
    report={"classification":"PMOS PRIVATE AGGREGATE RESTORE DRILL — NO PATHS OR RECORD VALUES","completed_at":datetime.now(timezone.utc).isoformat(),"status":"PASS","method":"verified_restore_drill_v1","backup_sha256":verified["metadata"]["sha256"],"sqlite_integrity":check["integrity"],"audit_ledger_valid":check["ledger"]["valid"],"ledger_entries":check["ledger"]["entries"],"encrypted_storage_verified":True,"temporary_restore_removed":removed}
    digest=hashlib.sha256(_canonical(report).encode()).hexdigest();existing=session.scalar(select(RestoreDrillRun).where(RestoreDrillRun.result_hash==digest))
    if existing:return existing,report
    run=RestoreDrillRun(status="PASS",backup_sha256=report["backup_sha256"],result_hash=digest,report_json=_canonical(report),ledger_entries=report["ledger_entries"],sqlite_integrity="ok",encrypted_storage_verified=True,temporary_restore_removed=removed,actor=actor,completed_at=datetime.fromisoformat(report["completed_at"]));session.add(run);session.flush();append_ledger_event(session,"RESTORE_DRILL",run.id,actor,"SYSTEM","DRILL_COMPLETED",{"status":run.status,"result_hash":digest,"backup_sha256":run.backup_sha256,"ledger_entries":run.ledger_entries,"temporary_restore_removed":removed});return run,report
