#!/usr/bin/env python3
"""Exercise synthetic public-leak detection, containment, and clean recovery."""
from pathlib import Path
import argparse,json,os,sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from pmos_research.db import DB_URL,SessionLocal,init_db
from pmos_research.backup import sqlite_path_from_url
from pmos_research.incident_exercise import IncidentExerciseError,run_public_leak_exercise

parser=argparse.ArgumentParser();parser.add_argument("--actor",default="incident-exercise-worker");args=parser.parse_args();init_db();source=sqlite_path_from_url(DB_URL);private_root=Path(os.getenv("PMOS_PRIVATE_ROOT",source.parent.parent));exercise_root=private_root/"incident-exercises"
try:
    with SessionLocal() as db:run,report=run_public_leak_exercise(db,ROOT,exercise_root,args.actor);db.commit()
    print(json.dumps({"status":run.status,"scenario":run.scenario,"report_hash":run.report_hash,"detection_count":run.detection_count,"containment_verified":run.containment_verified,"recovery_verified":run.recovery_verified},sort_keys=True))
except IncidentExerciseError as exc:raise SystemExit(str(exc))
