#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from pmos_research.audit_ledger import verify_ledger
from pmos_research.db import SessionLocal,init_db

parser=argparse.ArgumentParser(description="Verify the append-only PMOS audit ledger selected by PMOS_DB_URL.")
parser.parse_args()
init_db()
with SessionLocal() as db:result=verify_ledger(db)
print(json.dumps(result,sort_keys=True))
raise SystemExit(0 if result["valid"] else 1)
