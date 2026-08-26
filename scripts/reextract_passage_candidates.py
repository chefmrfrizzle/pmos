#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"packages/research"))

from pmos_research.audit_ledger import append_ledger_event
from pmos_research.db import ResearchDocumentSnapshot,ResearchSourceCandidate,SourceDocument
from pmos_research.source_retrieval import queue_passage_candidates

def main()->int:
    parser=argparse.ArgumentParser(description="Re-extract deterministic passage candidates from stored first-party snapshots.")
    parser.add_argument("--limit",type=int,default=25)
    args=parser.parse_args()
    if not 1<=args.limit<=100:parser.error("limit must be between 1 and 100")
    db_url=os.environ.get("PMOS_DB_URL")
    if not db_url:parser.error("PMOS_DB_URL is required")
    factory=sessionmaker(bind=create_engine(db_url))
    totals=Counter()
    with factory() as db:
        rows=db.execute(select(ResearchSourceCandidate,ResearchDocumentSnapshot,SourceDocument).join(ResearchDocumentSnapshot,ResearchDocumentSnapshot.source_candidate_id==ResearchSourceCandidate.id).join(SourceDocument,SourceDocument.id==ResearchDocumentSnapshot.source_document_id).where(ResearchSourceCandidate.status=="RETRIEVED_REVIEW_REQUIRED").order_by(ResearchDocumentSnapshot.retrieved_at.desc()).limit(args.limit)).all()
        for candidate,snapshot,document in rows:
            counts=queue_passage_candidates(db,candidate,document,snapshot.normalized_text,json.loads(candidate.target_predicates_json))
            totals.update(counts);totals["snapshots_examined"]+=1
        append_ledger_event(db,"RESEARCH_BATCH","passage-reextraction","research-worker","SYSTEM","PASSAGE_REEXTRACTION_COMPLETED",dict(totals))
        db.commit()
    print(json.dumps(dict(totals),sort_keys=True))
    return 0

if __name__=="__main__":raise SystemExit(main())
