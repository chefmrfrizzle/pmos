#!/usr/bin/env python3
from __future__ import annotations

import argparse,json,sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from sqlalchemy import select
from pmos_research.audit_ledger import append_ledger_event
from pmos_research.db import ResearchSourceCandidate,SessionLocal,SourceRetrievalAttempt,init_db

def main()->int:
    parser=argparse.ArgumentParser(description="Requeue bounded due source retries after recorded backoff.");parser.add_argument("--limit",type=int,default=5);parser.add_argument("--include-legacy",action="store_true");args=parser.parse_args()
    if not 1<=args.limit<=25:parser.error("limit must be between 1 and 25")
    init_db();now=datetime.now(timezone.utc);counts=Counter()
    with SessionLocal() as db:
        candidates=db.scalars(select(ResearchSourceCandidate).where(ResearchSourceCandidate.status=="RETRY_REQUIRED").order_by(ResearchSourceCandidate.updated_at,ResearchSourceCandidate.id)).all()
        for candidate in candidates:
            latest=db.scalars(select(SourceRetrievalAttempt).where(SourceRetrievalAttempt.source_candidate_id==candidate.id).order_by(SourceRetrievalAttempt.attempt_number.desc()).limit(1)).first()
            if not latest:
                if not args.include_legacy:counts["legacy_requires_explicit_flag"]+=1;continue
            elif not latest.retryable or not latest.next_attempt_at:counts["retry_exhausted_or_not_allowed"]+=1;continue
            elif (latest.next_attempt_at.replace(tzinfo=timezone.utc) if latest.next_attempt_at.tzinfo is None else latest.next_attempt_at)>now:counts["backoff_not_elapsed"]+=1;continue
            prior=candidate.status;candidate.status="PENDING_REVIEW";candidate.updated_at=now
            append_ledger_event(db,"SOURCE_CANDIDATE",candidate.id,"retry-scheduler","SYSTEM","SOURCE_RETRY_REQUEUED",{"prior_state":prior,"resulting_state":candidate.status,"prior_attempt_number":latest.attempt_number if latest else 0,"legacy_attempt_history":latest is None})
            counts["requeued"]+=1
            if counts["requeued"]>=args.limit:break
        db.commit()
    print(json.dumps(dict(sorted(counts.items())),sort_keys=True));return 0

if __name__=="__main__":raise SystemExit(main())
