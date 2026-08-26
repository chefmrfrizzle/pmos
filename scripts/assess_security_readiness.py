#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import json,subprocess,sys
from sqlalchemy.engine import make_url

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from pmos_research.backup import verify_backup_manifest
from pmos_research.db import DB_URL,SessionLocal,init_db
from pmos_research.security_readiness import build_security_readiness,persist_security_readiness

def gate(command,cwd=ROOT):return subprocess.run(command,cwd=cwd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False).returncode==0

technical={
    "public_release_check":gate([sys.executable,"scripts/public_release_check.py"]),
    "backend_tests":gate([sys.executable,"-m","pytest","-q","packages/research/tests","apps/api/tests"]),
    "web_build":gate(["npm","run","build"],ROOT/"apps/web"),
    "browser_tests":gate(["npx","playwright","test"],ROOT/"apps/web"),
}
backup_verified=False;url=make_url(DB_URL)
if url.drivername.startswith("sqlite") and url.database and url.database!=":memory:":
    source=Path(url.database).resolve();backup_root=source.parent.parent/"backups" if source.parent.name=="datastore" else source.parent/"backups";manifests=sorted(backup_root.glob("*.manifest.json"),key=lambda x:x.stat().st_mtime,reverse=True)
    if manifests:
        try:verify_backup_manifest(manifests[0],ROOT);backup_verified=True
        except Exception:backup_verified=False
init_db()
with SessionLocal() as db:
    report=build_security_readiness(db,ROOT,technical,backup_verified=backup_verified);run=persist_security_readiness(db,report);db.commit()
print(json.dumps({"status":report["status"],"report_hash":run.report_hash,"summary":report["summary"],"technical_gates":technical,"backup_verified":backup_verified},sort_keys=True))
raise SystemExit(0 if all(technical.values()) and backup_verified else 1)
