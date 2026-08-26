#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from pmos_research.db import SessionLocal,init_db
from pmos_research.identity_review_batch import build_identity_batch_packet,freeze_identity_batch

parser=argparse.ArgumentParser(description="Freeze a privacy-safe identity review population.");parser.add_argument("--universe",required=True);parser.add_argument("--status",default="PENDING");parser.add_argument("--queue-type");parser.add_argument("--resolution-state");parser.add_argument("--min-priority",type=int,default=0);parser.add_argument("--limit",type=int,default=100);parser.add_argument("--actor",default="identity-batch-worker");args=parser.parse_args();init_db()
with SessionLocal() as db:
    batch=freeze_identity_batch(db,args.actor,args.universe,args.status,args.queue_type,args.resolution_state,args.min_priority,args.limit);packet=build_identity_batch_packet(db,batch.id);db.commit()
print(json.dumps({"batch_id":packet["id"],"manifest_hash":packet["manifest_hash"],"manifest_valid":packet["manifest_valid"],"item_count":packet["item_count"]},sort_keys=True))
