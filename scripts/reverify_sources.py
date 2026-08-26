#!/usr/bin/env python3
"""Reverify bounded first-party source snapshots without mutating claims."""
from __future__ import annotations

import argparse,json,sys
from collections import Counter
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from sqlalchemy import select
from pmos_research.adapters.official_web import OfficialWebAdapter
from pmos_research.change_detection import persist_reverification,record_reverification_failure
from pmos_research.db import ResearchDocumentSnapshot,ResearchSourceCandidate,SourceChangeEvent,SessionLocal,init_db

parser=argparse.ArgumentParser(description="Reverify stale retrieved sources and create immutable change events.");parser.add_argument("--limit",type=int,default=5);parser.add_argument("--min-age-hours",type=int,default=168);args=parser.parse_args()
if not 1<=args.limit<=25 or not 0<=args.min_age_hours<=8760:raise SystemExit("arguments are outside safe bounds")
init_db();adapter=OfficialWebAdapter();counts=Counter();cutoff=datetime.now(timezone.utc)-timedelta(hours=args.min_age_hours)
with SessionLocal() as db:
    candidates=db.scalars(select(ResearchSourceCandidate).where(ResearchSourceCandidate.status=="RETRIEVED_REVIEW_REQUIRED").order_by(ResearchSourceCandidate.id)).all();eligible=[]
    for candidate in candidates:
        latest=db.scalar(select(ResearchDocumentSnapshot).where(ResearchDocumentSnapshot.source_candidate_id==candidate.id).order_by(ResearchDocumentSnapshot.retrieved_at.desc(),ResearchDocumentSnapshot.id.desc()))
        last_change=db.scalar(select(SourceChangeEvent).where(SourceChangeEvent.source_candidate_id==candidate.id).order_by(SourceChangeEvent.detected_at.desc(),SourceChangeEvent.id.desc()))
        activity=last_change.detected_at if last_change else latest.retrieved_at if latest else None
        if activity and (activity if activity.tzinfo else activity.replace(tzinfo=timezone.utc))<=cutoff:eligible.append(candidate)
        if len(eligible)>=args.limit:break
    for candidate in eligible:
        candidate_id=candidate.id
        try:snapshot=adapter.fetch(candidate.source_url)
        except Exception as exc:
            outcome=f"failed_{type(exc).__name__}";counts[outcome]+=1;db.rollback();record_reverification_failure(db,db.get(ResearchSourceCandidate,candidate_id),outcome);db.commit();continue
        if snapshot.get("status")!="ok":
            outcome=snapshot.get("status","failed");counts[outcome]+=1;record_reverification_failure(db,candidate,outcome);db.commit();continue
        try:result=persist_reverification(db,candidate,snapshot);counts[result["status"]]+=1;counts["passages_queued"]+=result["passages_queued"];db.commit()
        except Exception as exc:
            outcome=f"persist_failed_{type(exc).__name__}";counts[outcome]+=1;db.rollback();record_reverification_failure(db,db.get(ResearchSourceCandidate,candidate_id),outcome);db.commit()
print(json.dumps({"eligible":len(eligible),"outcomes":dict(sorted(counts.items()))},sort_keys=True))
