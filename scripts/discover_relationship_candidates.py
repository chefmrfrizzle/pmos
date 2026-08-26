#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from pmos_research.db import SessionLocal,init_db
from pmos_research.relationship_research import discover_relationship_candidates
parser=argparse.ArgumentParser();parser.add_argument("--limit",type=int,default=100);args=parser.parse_args();init_db()
with SessionLocal() as db:result=discover_relationship_candidates(db,args.limit);db.commit()
print(json.dumps(result,sort_keys=True))
