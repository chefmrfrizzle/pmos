#!/usr/bin/env python3
"""Retrieve bounded first-party candidates and queue exact passages for review."""
from __future__ import annotations

import argparse,json,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from sqlalchemy import select
from pmos_research.adapters.official_web import OfficialWebAdapter
from pmos_research.db import ResearchSourceCandidate,SessionLocal,init_db
from pmos_research.source_retrieval import persist_retrieved_candidate,record_retrieval_outcome

parser=argparse.ArgumentParser(description="Retrieve review-only same-domain source candidates without creating claims.");parser.add_argument("--limit",type=int,default=5);args=parser.parse_args()
if not 1<=args.limit<=25:raise SystemExit("--limit must be between 1 and 25")
init_db();adapter=OfficialWebAdapter();counts=Counter()
with SessionLocal() as db:
    rows=db.scalars(select(ResearchSourceCandidate).where(ResearchSourceCandidate.status=="PENDING_REVIEW").order_by(ResearchSourceCandidate.discovery_score.desc(),ResearchSourceCandidate.id).limit(args.limit)).all()
    for candidate in rows:
        candidate_id=candidate.id
        try:snapshot=adapter.fetch(candidate.source_url)
        except Exception as exc:
            outcome=f"failed_{type(exc).__name__}";counts[outcome]+=1;db.rollback();record_retrieval_outcome(db,db.get(ResearchSourceCandidate,candidate_id),outcome);db.commit();continue
        if snapshot.get("status")!="ok":
            outcome=snapshot.get("status","failed");counts[outcome]+=1;record_retrieval_outcome(db,candidate,outcome);db.commit();continue
        try:counts.update(persist_retrieved_candidate(db,candidate,snapshot));db.commit()
        except Exception as exc:counts[f"persist_failed_{type(exc).__name__}"]+=1;db.rollback()
print(json.dumps({"attempted":len(rows),"outcomes":dict(sorted(counts.items()))},sort_keys=True))
