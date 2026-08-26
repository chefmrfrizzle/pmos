#!/usr/bin/env python3
"""Execute an approved, unexpired dossier export onto encrypted private storage."""
from __future__ import annotations

import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from pmos_research.db import PRIVATE_ROOT,SessionLocal,init_db
from pmos_research.export_governance import execute_export

parser=argparse.ArgumentParser(description="Execute an independently approved private dossier export.");parser.add_argument("--request-id",type=int,required=True);parser.add_argument("--actor",required=True);args=parser.parse_args()
if args.request_id<1 or len(args.actor.strip())<3:raise SystemExit("valid request and executor are required")
init_db()
with SessionLocal() as db:result=execute_export(db,args.request_id,args.actor,PRIVATE_ROOT,ROOT)
print(json.dumps({"artifact_file":result["artifact"].name,"manifest_file":result["manifest"].name,"bytes":result["bytes"],"sha256":result["sha256"]},sort_keys=True))
