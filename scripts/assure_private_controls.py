#!/usr/bin/env python3
"""Run aggregate-only private datastore control assurance; print no record values."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from pmos_research.control_assurance import persist_assurance_run,run_control_assurance
from pmos_research.db import SessionLocal,init_db

parser=argparse.ArgumentParser(description="Run aggregate private controls against the datastore selected by PMOS_DB_URL.")
parser.parse_args()
init_db()
with SessionLocal() as db:
    result=run_control_assurance(db);run=persist_assurance_run(db,result);db.commit()
print(json.dumps(result,sort_keys=True))
raise SystemExit(0 if result["status"]=="PASS" else 1)
