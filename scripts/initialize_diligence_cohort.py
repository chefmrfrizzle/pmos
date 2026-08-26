#!/usr/bin/env python3
"""Create a bounded, review-first institutional diligence cohort."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from sqlalchemy import select
from pmos_research.db import DiligenceCase,Entity,SessionLocal,init_db
from pmos_research.diligence import open_case
from pmos_research.adjudication import enqueue_case_corroboration

UNIVERSE_TYPES={
    "venture_capital":"venture capital",
    "private_equity":"private equity",
    "hedge_funds":"hedge fund",
    "corporate_venture_capital":"corporate venture capital",
    "sovereign_wealth":"sovereign wealth",
    "pensions":"pension",
    "private_banks":"default",
    "multifamily_offices":"default",
}

parser=argparse.ArgumentParser(description="Open bounded PMOS diligence cases without verifying or merging identities.")
parser.add_argument("--per-universe",type=int,default=2,choices=range(1,11))
parser.add_argument("--universes",nargs="*",default=list(UNIVERSE_TYPES),choices=list(UNIVERSE_TYPES))
parser.add_argument("--owner",default="system-intake")
args=parser.parse_args();init_db();counts={}
with SessionLocal() as db:
    existing=set(db.scalars(select(DiligenceCase.entity_id)).all())
    for universe in args.universes:
        entities=db.scalars(select(Entity).where(Entity.universe==universe,Entity.official_url.is_not(None),Entity.official_url!="").order_by(Entity.canonical_name,Entity.id)).all()
        cohort_count=sum(1 for entity in entities if entity.id in existing)
        target_new=max(0,args.per_universe-cohort_count)
        created=0;seen=set()
        for entity in entities:
            if created>=target_new:break
            if entity.id in existing or entity.canonical_name in seen:continue
            seen.add(entity.canonical_name)
            open_case(db,entity.id,UNIVERSE_TYPES[universe],"institutional counterparty diligence","private internal decision support; no autonomous outreach",args.owner,[entity.country] if entity.country else [])
            existing.add(entity.id);created+=1
        counts[universe]={"created":created,"cohort_total":cohort_count+created,"eligible_seen":len(entities)}
    corroboration=enqueue_case_corroboration(db);db.commit()
print(json.dumps({"cohort":counts,"cases_created":sum(x["created"] for x in counts.values()),"corroboration":dict(corroboration)},sort_keys=True))
