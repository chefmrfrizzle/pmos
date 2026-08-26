#!/usr/bin/env python3
"""Persist an aggregate, deletion-free retention assessment."""
from pathlib import Path
import argparse,json,sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from pmos_research.db import SessionLocal,init_db
from pmos_research.retention import build_retention_assessment,persist_retention_assessment

parser=argparse.ArgumentParser(description="Assess private retention eligibility without deleting or printing records.")
parser.add_argument("--policy",type=Path)
args=parser.parse_args();init_db()
with SessionLocal() as db:report=build_retention_assessment(db,ROOT,args.policy);persist_retention_assessment(db,report);db.commit()
print(json.dumps(report,sort_keys=True))
