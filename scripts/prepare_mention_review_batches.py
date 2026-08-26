#!/usr/bin/env python3
"""Freeze aggregate mention-review cohorts without printing record values."""
from pathlib import Path
import argparse,json,sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from pmos_research.db import SessionLocal,init_db
from pmos_research.relationship_mention_review import RelationshipMentionReviewError,freeze_pending_mention_batches

parser=argparse.ArgumentParser(description="Freeze pending relationship-mention review batches by universe.")
parser.add_argument("--status",choices=("ENTITY_RESOLUTION_REQUIRED","TARGET_PROPOSED"),default="ENTITY_RESOLUTION_REQUIRED")
parser.add_argument("--limit-per-universe",type=int,default=100)
args=parser.parse_args()
try:
    init_db()
    with SessionLocal() as db:result=freeze_pending_mention_batches(db,status=args.status,limit_per_universe=args.limit_per_universe);db.commit()
    print(json.dumps(result,sort_keys=True))
except RelationshipMentionReviewError as exc:raise SystemExit(str(exc))
