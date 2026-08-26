#!/usr/bin/env python3
"""Restore the latest verified backup to encrypted temporary storage and prove recovery integrity."""
from pathlib import Path
import argparse,json,sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from pmos_research.db import DB_URL,SessionLocal,init_db
from pmos_research.backup import sqlite_path_from_url
from pmos_research.restore_drill import RestoreDrillError,run_restore_drill

parser=argparse.ArgumentParser();parser.add_argument("--manifest",type=Path);parser.add_argument("--actor",default="restore-drill-worker");args=parser.parse_args();init_db()
source=sqlite_path_from_url(DB_URL);backup_root=source.parent.parent/"backups" if source.parent.name=="datastore" else source.parent/"backups";manifests=sorted(backup_root.glob("*.manifest.json"),key=lambda x:x.stat().st_mtime,reverse=True);manifest=args.manifest or (manifests[0] if manifests else None)
if not manifest:raise SystemExit("no backup manifest is available")
try:
    with SessionLocal() as db:run,report=run_restore_drill(db,manifest,ROOT,args.actor);db.commit()
    print(json.dumps({"status":run.status,"result_hash":run.result_hash,"ledger_entries":run.ledger_entries,"sqlite_integrity":run.sqlite_integrity,"encrypted_storage_verified":run.encrypted_storage_verified,"temporary_restore_removed":run.temporary_restore_removed},sort_keys=True))
except RestoreDrillError as exc:raise SystemExit(str(exc))
