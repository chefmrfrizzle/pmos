#!/usr/bin/env python3
from pathlib import Path
from collections import Counter
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from sqlalchemy import select
from pmos_research.adjudication import run_corroboration_job
from pmos_research.adapters.official_web import OfficialWebAdapter
from pmos_research.db import CorroborationJob,SessionLocal,init_db

parser=argparse.ArgumentParser(description="Run bounded, resumable first-party corroboration jobs.")
parser.add_argument("--limit",type=int,default=10)
args=parser.parse_args()
if args.limit<1 or args.limit>100:raise SystemExit("--limit must be between 1 and 100")
init_db();adapter=OfficialWebAdapter();counts=Counter()
with SessionLocal() as db:
    jobs=db.scalars(select(CorroborationJob).where(CorroborationJob.status=="PENDING").order_by(CorroborationJob.id).limit(args.limit)).all()
    for job in jobs:
        counts[run_corroboration_job(db,job,adapter)]+=1;db.commit()
print(json.dumps({"attempted":sum(counts.values()),"outcomes":dict(sorted(counts.items()))},sort_keys=True))
