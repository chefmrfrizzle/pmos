#!/usr/bin/env python3
"""Create one aggregate baseline for pre-ledger datastore state, then verify."""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from sqlalchemy import func,select
from pmos_research.audit_ledger import append_ledger_event,verify_ledger
from pmos_research.db import AuditLedgerEntry,Claim,DiligenceCase,Entity,Evidence,RawImportRow,ResolutionDecision,SessionLocal,init_db

init_db()
with SessionLocal() as db:
    existing=db.scalar(select(AuditLedgerEntry).where(AuditLedgerEntry.stream_type=="SYSTEM_BASELINE",AuditLedgerEntry.stream_id=="PRIVATE_DATASTORE"))
    created=False
    if not existing:
        counts={
            "entities":db.scalar(select(func.count()).select_from(Entity)),
            "raw_import_rows":db.scalar(select(func.count()).select_from(RawImportRow)),
            "resolution_decisions":db.scalar(select(func.count()).select_from(ResolutionDecision)),
            "claims":db.scalar(select(func.count()).select_from(Claim)),
            "evidence":db.scalar(select(func.count()).select_from(Evidence)),
            "diligence_cases":db.scalar(select(func.count()).select_from(DiligenceCase)),
        }
        append_ledger_event(db,"SYSTEM_BASELINE","PRIVATE_DATASTORE","system-migration","SYSTEM","BASELINE_CREATED",{"aggregate_counts":counts,"limitations":"Pre-ledger actions are represented by aggregate counts only; no historical actor identity is inferred."},"private-v2-ledger-baseline")
        db.commit();created=True
    result=verify_ledger(db)
print(json.dumps({"baseline_created":created,"ledger":result},sort_keys=True))
