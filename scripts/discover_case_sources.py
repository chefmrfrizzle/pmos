#!/usr/bin/env python3
"""Discover review-only first-party source candidates for the diligence cohort."""
from __future__ import annotations

import argparse,json,sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from sqlalchemy import select
from pmos_research.adapters.official_web import OfficialWebAdapter
from pmos_research.db import CorroborationJob,DiligenceCase,Entity,SessionLocal,init_db
from pmos_research.source_discovery import persist_source_candidates

parser=argparse.ArgumentParser(description="Discover bounded same-domain diligence sources without creating factual claims.")
parser.add_argument("--limit",type=int,default=10);parser.add_argument("--per-entity",type=int,default=20);parser.add_argument("--refresh",action="store_true")
args=parser.parse_args()
if not 1<=args.limit<=100 or not 1<=args.per_entity<=50:raise SystemExit("limits are outside safe bounds")
init_db();adapter=OfficialWebAdapter();counts=Counter()
with SessionLocal() as db:
    jobs=db.scalars(select(CorroborationJob).join(Entity,Entity.id==CorroborationJob.entity_id).join(DiligenceCase,DiligenceCase.entity_id==Entity.id).where(Entity.universe!="imported_private",CorroborationJob.status=="SUPPORTED").order_by(CorroborationJob.id)).unique().all()
    attempted=0
    for job in jobs:
        checkpoint=json.loads(job.checkpoint_json or "{}")
        if checkpoint.get("source_discovery_completed_at") and not args.refresh:counts["already_completed"]+=1;continue
        if attempted>=args.limit:break
        attempted+=1
        try:snapshot=adapter.fetch(job.source_url)
        except Exception as exc:
            counts[f"failed_{type(exc).__name__}"]+=1;db.rollback();continue
        status=snapshot.get("status","failed")
        if status!="ok":counts[status]+=1;continue
        entity=db.get(Entity,job.entity_id);result=persist_source_candidates(db,entity,snapshot["url"],snapshot.get("html",""),limit=args.per_entity)
        counts.update(result);checkpoint.update({"source_discovery_completed_at":datetime.now(timezone.utc).isoformat(),"source_discovery_hash":snapshot["hash"],"source_candidates_queued":result.get("queued",0)});job.checkpoint_json=json.dumps(checkpoint,sort_keys=True);db.commit()
print(json.dumps({"attempted":attempted,"outcomes":dict(sorted(counts.items()))},sort_keys=True))
