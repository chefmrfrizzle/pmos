#!/usr/bin/env python3
from pathlib import Path
import argparse,json,os,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from pmos_research.audit_ledger import append_ledger_event,verify_ledger
from pmos_research.backup import BackupSafetyError,create_private_backup
from pmos_research.db import DB_URL,SessionLocal

parser=argparse.ArgumentParser(description="Create and verify a consistent PMOS private SQLite backup.")
parser.add_argument("--backup-root",type=Path)
parser.add_argument("--allow-unverified-storage",action="store_true",help="Development only: do not require FileVault or explicit encrypted-storage attestation.")
args=parser.parse_args();repo=Path(__file__).resolve().parents[1]
try:
    result=create_private_backup(DB_URL,repo,args.backup_root,not args.allow_unverified_storage)
    with SessionLocal() as db:
        append_ledger_event(db,"BACKUP","PRIVATE_DATASTORE","backup-worker","SYSTEM","BACKUP_CREATED",{"backup_file":result["metadata"]["backup_file"],"sha256":result["metadata"]["sha256"],"bytes":result["metadata"]["bytes"],"ledger_entries_in_backup":result["metadata"]["audit_ledger_entries"]});db.commit();ledger=verify_ledger(db)
    if not ledger["valid"]:raise BackupSafetyError("source ledger failed after backup event")
    print(json.dumps({"backup_file":result["metadata"]["backup_file"],"manifest_file":result["manifest"].name,"bytes":result["metadata"]["bytes"],"sha256":result["metadata"]["sha256"],"ledger_entries_in_backup":result["metadata"]["audit_ledger_entries"],"source_ledger_entries_after_event":ledger["entries"],"encrypted_storage_verified":result["metadata"]["encrypted_storage_verified"]},sort_keys=True))
except BackupSafetyError as exc:raise SystemExit(str(exc))
