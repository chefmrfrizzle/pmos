#!/usr/bin/env python3
"""Retrieve bounded first-party candidates and queue exact passages for review."""
from __future__ import annotations

import argparse,json,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from sqlalchemy import select
from pmos_research.adapters.official_web import OfficialWebAdapter
from pmos_research.db import Entity,ResearchSourceCandidate,SessionLocal,init_db
from pmos_research.source_retrieval import classify_http_status,persist_retrieved_candidate,record_retrieval_attempt,record_retrieval_outcome,require_public_candidate

parser=argparse.ArgumentParser(description="Retrieve review-only same-domain source candidates without creating claims.");parser.add_argument("--limit",type=int,default=5);args=parser.parse_args()
if not 1<=args.limit<=25:raise SystemExit("--limit must be between 1 and 25")
init_db();adapter=OfficialWebAdapter();counts=Counter()
with SessionLocal() as db:
    rows=db.scalars(select(ResearchSourceCandidate).join(Entity,Entity.id==ResearchSourceCandidate.entity_id).where(Entity.universe!="imported_private",ResearchSourceCandidate.status=="PENDING_REVIEW").order_by(ResearchSourceCandidate.discovery_score.desc(),ResearchSourceCandidate.id).limit(args.limit)).all()
    for candidate in rows:
        candidate_id=candidate.id
        require_public_candidate(db,candidate)
        try:snapshot=adapter.fetch(candidate.source_url)
        except Exception as exc:
            status=getattr(getattr(exc,"response",None),"status_code",None);outcome,retryable=classify_http_status(status) if isinstance(status,int) else ("network_or_adapter_error",True)
            counts[outcome]+=1;db.rollback();candidate=db.get(ResearchSourceCandidate,candidate_id);record_retrieval_outcome(db,candidate,outcome);record_retrieval_attempt(db,candidate,outcome,retryable,type(exc).__name__,status);db.commit();continue
        if snapshot.get("status")!="ok":
            outcome=snapshot.get("status","failed");counts[outcome]+=1;record_retrieval_outcome(db,candidate,outcome);record_retrieval_attempt(db,candidate,outcome,False);db.commit();continue
        try:counts.update(persist_retrieved_candidate(db,candidate,snapshot));record_retrieval_attempt(db,candidate,"retrieved",False);db.commit()
        except Exception as exc:
            counts["persist_failed"]+=1;db.rollback();candidate=db.get(ResearchSourceCandidate,candidate_id);record_retrieval_outcome(db,candidate,"persist_failed");record_retrieval_attempt(db,candidate,"persist_failed",True,type(exc).__name__);db.commit()
print(json.dumps({"attempted":len(rows),"outcomes":dict(sorted(counts.items()))},sort_keys=True))
