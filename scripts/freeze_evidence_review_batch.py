#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from pmos_research.db import SessionLocal,init_db
from pmos_research.evidence_review_batch import build_batch_packet,freeze_review_batch

parser=argparse.ArgumentParser(description="Freeze a content-hashed specialist evidence review population.")
parser.add_argument("--universe",required=True);parser.add_argument("--status",default="HUMAN_REVIEW_REQUIRED");parser.add_argument("--predicate");parser.add_argument("--min-confidence",type=float,default=0);parser.add_argument("--limit",type=int,default=50);parser.add_argument("--actor",default="evidence-batch-worker")
args=parser.parse_args();init_db()
with SessionLocal() as db:
    batch=freeze_review_batch(db,args.actor,args.universe,args.status,args.predicate,args.min_confidence,args.limit);packet=build_batch_packet(db,batch.id);db.commit()
print(json.dumps({"batch_id":packet["id"],"manifest_hash":packet["manifest_hash"],"manifest_valid":packet["manifest_valid"],"item_count":packet["item_count"]},sort_keys=True))
