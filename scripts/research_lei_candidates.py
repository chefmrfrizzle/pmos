#!/usr/bin/env python3
"""Create reviewable LEI candidates for the public diligence cohort."""
from pathlib import Path
from collections import Counter
import argparse,json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from sqlalchemy import select
from pmos_research.db import DiligenceCase,Entity,RegistryIdentifierCandidate,SessionLocal,init_db
from pmos_research.registry_research import research_entity_lei

parser=argparse.ArgumentParser();parser.add_argument("--limit",type=int,default=32);parser.add_argument("--refresh",action="store_true");args=parser.parse_args()
if args.limit<1 or args.limit>100:raise SystemExit("--limit must be between 1 and 100")
init_db();counts=Counter()
with SessionLocal() as db:
    query=select(Entity).join(DiligenceCase,DiligenceCase.entity_id==Entity.id).where(Entity.universe!="imported_private").order_by(Entity.universe,Entity.canonical_name,Entity.id)
    entities=db.scalars(query).unique().all();processed=0
    for entity in entities:
        if processed>=args.limit:break
        if not args.refresh and db.scalar(select(RegistryIdentifierCandidate.id).where(RegistryIdentifierCandidate.entity_id==entity.id).limit(1)):
            counts["skipped_existing"]+=1;continue
        try:
            result=research_entity_lei(db,entity);db.commit();processed+=1;counts["searched"]+=1;counts["records_returned"]+=result["records_returned"]
            for key,value in result["candidate_outcomes"].items():counts[key]+=value
        except Exception:
            db.rollback();processed+=1;counts["failed"]+=1
        time.sleep(.5)
print(json.dumps({"processed":processed,"outcomes":dict(sorted(counts.items()))},sort_keys=True))
