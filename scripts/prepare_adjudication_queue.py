#!/usr/bin/env python3
from pathlib import Path
import argparse, json, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from pmos_research.adjudication import build_review_queue,enqueue_corroboration,queue_summary
from pmos_research.db import SessionLocal,init_db

parser=argparse.ArgumentParser(description="Build the local private adjudication and first-party corroboration queues.")
parser.add_argument("--corroboration-limit",type=int,default=0,help="Maximum new canonical institutions to enqueue; 0 means all eligible.")
args=parser.parse_args();init_db()
with SessionLocal() as db:
    review=build_review_queue(db);corroboration=enqueue_corroboration(db,args.corroboration_limit);db.commit()
    print(json.dumps({"created_review_items":dict(review),"corroboration":dict(corroboration),**queue_summary(db)},sort_keys=True))
