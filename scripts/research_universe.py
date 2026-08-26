#!/usr/bin/env python3
"""Run bounded public-registry research through the controlled claim pipeline."""
from pathlib import Path
from collections import Counter
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from sqlalchemy import select
from pmos_research.adjudication import normalize_public_url,run_corroboration_job
from pmos_research.adapters.official_web import OfficialWebAdapter
from pmos_research.db import CorroborationJob,Entity,SessionLocal,init_db

parser=argparse.ArgumentParser(description="Research public-registry institutions without exposing private identities.")
parser.add_argument("--universe")
parser.add_argument("--country",action="append",dest="countries",help="ISO 3166-1 alpha-2 country filter; repeatable")
parser.add_argument("--limit",type=int,default=25)
args=parser.parse_args()
if args.universe=="imported_private":raise SystemExit("private-import research requires an explicitly scoped diligence-case workflow")
if args.limit<1 or args.limit>100:raise SystemExit("--limit must be between 1 and 100")
countries={value.strip().upper() for value in (args.countries or [])}
if any(len(value)!=2 or not value.isalpha() for value in countries):raise SystemExit("--country must be an ISO 3166-1 alpha-2 code")
init_db();adapter=OfficialWebAdapter();counts=Counter()
with SessionLocal() as db:
    entities=select(Entity).where(Entity.universe!="imported_private",Entity.official_url.is_not(None),Entity.official_url!="")
    if args.universe:entities=entities.where(Entity.universe==args.universe)
    if countries:entities=entities.where(Entity.country.in_(sorted(countries)))
    rows=db.scalars(entities.order_by(Entity.universe,Entity.canonical_name,Entity.id)).all();entity_ids={x.id for x in rows}
    existing={(x.entity_id,x.source_url) for x in db.scalars(select(CorroborationJob).where(CorroborationJob.entity_id.in_(entity_ids))).all()} if entity_ids else set()
    for entity in rows:
        url=normalize_public_url(entity.official_url)
        if not url:counts["invalid_url"]+=1;continue
        key=(entity.id,url)
        if key not in existing:
            from urllib.parse import urlparse
            db.add(CorroborationJob(entity_id=entity.id,source_url=url,source_domain=(urlparse(url).hostname or "").removeprefix("www."),status="PENDING",checkpoint_json="{}"));existing.add(key);counts["queued"]+=1
    db.flush()
    jobs=db.scalars(select(CorroborationJob).where(CorroborationJob.entity_id.in_(entity_ids),CorroborationJob.status=="PENDING").order_by(CorroborationJob.id).limit(args.limit)).all() if entity_ids else []
    for job in jobs:counts[run_corroboration_job(db,job,adapter)]+=1;db.commit()
print(json.dumps({"eligible_public_entities":len(entity_ids),"attempted":len(jobs),"outcomes":dict(sorted(counts.items()))},sort_keys=True))
