#!/usr/bin/env python3
"""Explicitly requeue official PDF candidates after bounded PDF support is installed."""
from __future__ import annotations

import argparse,json,sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from sqlalchemy import select
from pmos_research.audit_ledger import append_ledger_event
from pmos_research.db import ResearchSourceCandidate,SessionLocal,init_db

parser=argparse.ArgumentParser(description="Requeue previously unsupported official PDFs with an auditable capability-migration event.");parser.add_argument("--limit",type=int,default=10);args=parser.parse_args()
if not 1<=args.limit<=25:raise SystemExit("--limit must be between 1 and 25")
init_db();counts=Counter()
with SessionLocal() as db:
    rows=db.scalars(select(ResearchSourceCandidate).where(ResearchSourceCandidate.status=="UNSUPPORTED_CONTENT_TYPE").order_by(ResearchSourceCandidate.id)).all()
    for candidate in rows:
        if counts["requeued"]>=args.limit:break
        parsed=urlparse(candidate.source_url)
        if not parsed.path.casefold().endswith(".pdf") or (parsed.hostname or "").casefold().removeprefix("www.")!=candidate.source_domain:counts["ineligible"]+=1;continue
        prior=candidate.status;candidate.status="PENDING_REVIEW";candidate.updated_at=datetime.now(timezone.utc)
        append_ledger_event(db,"SOURCE_CANDIDATE",candidate.id,"capability-migration","SYSTEM","PDF_REQUEUED",{"prior_state":prior,"resulting_state":candidate.status,"reason":"bounded_pdf_extractor_v1_installed"});counts["requeued"]+=1
    db.commit()
print(json.dumps(dict(sorted(counts.items())),sort_keys=True))
