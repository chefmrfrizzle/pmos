#!/usr/bin/env python3
"""Validate an external reviewer roster without printing subject identities."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from pmos_research.db import SessionLocal,init_db
from pmos_research.reviewer_roster import build_reviewer_roster_assessment,persist_reviewer_roster_assessment
parser=argparse.ArgumentParser();parser.add_argument("--roster",type=Path);args=parser.parse_args();init_db()
with SessionLocal() as db:report=build_reviewer_roster_assessment(db,ROOT,args.roster);persist_reviewer_roster_assessment(db,report);db.commit()
print(json.dumps(report,sort_keys=True))
