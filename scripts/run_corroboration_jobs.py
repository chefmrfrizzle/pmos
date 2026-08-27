#!/usr/bin/env python3
from pathlib import Path
from collections import Counter
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from datetime import datetime,timezone
from sqlalchemy import and_,or_,select
from pmos_research.adjudication import run_corroboration_job
from pmos_research.adapters.official_web import OfficialWebAdapter
from pmos_research.db import CorroborationJob,DiligenceCase,Entity,SessionLocal,init_db

parser=argparse.ArgumentParser(description="Run bounded, resumable first-party corroboration jobs.")
parser.add_argument("--limit",type=int,default=10)
parser.add_argument("--case-cohort",action="store_true",help="Run only jobs for entities selected into diligence cases.")
args=parser.parse_args()
if args.limit<1 or args.limit>100:raise SystemExit("--limit must be between 1 and 100")
init_db();adapter=OfficialWebAdapter();counts=Counter()
with SessionLocal() as db:
    now=datetime.now(timezone.utc);query=select(CorroborationJob).join(Entity,Entity.id==CorroborationJob.entity_id).where(Entity.universe!="imported_private",or_(CorroborationJob.status=="PENDING",and_(CorroborationJob.status=="RETRY_REQUIRED",CorroborationJob.next_attempt_at<=now)))
    if args.case_cohort:query=query.join(DiligenceCase,DiligenceCase.entity_id==Entity.id).distinct()
    jobs=db.scalars(query.order_by(CorroborationJob.id).limit(args.limit)).all()
    for job in jobs:
        counts[run_corroboration_job(db,job,adapter)]+=1;db.commit()
print(json.dumps({"attempted":sum(counts.values()),"outcomes":dict(sorted(counts.items()))},sort_keys=True))
