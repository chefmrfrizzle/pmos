from __future__ import annotations

import hashlib,json,secrets
from sqlalchemy import select

from .adjudication import AdjudicationInputError,_identity_pair,_version
from .audit_ledger import append_ledger_event
from .db import IdentityReviewBatch,IdentityReviewBatchItem,ResolutionDecision,ReviewQueueItem
from .identity_review import build_review_packet

class IdentityReviewBatchError(ValueError):pass
def _canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def pair_fingerprint(session,item,decision)->str:
    try:kind,ids=_identity_pair(session,item,decision);value=f"{kind}|{'|'.join(str(x) for x in sorted(ids))}|{decision.id}"
    except AdjudicationInputError:value=f"UNRESOLVED|{item.id}|{decision.id}"
    return hashlib.sha256(value.encode()).hexdigest()

def freeze_identity_batch(session,actor:str,universe:str,status:str="PENDING",queue_type:str|None=None,resolution_state:str|None=None,min_priority:int=0,limit:int=100)->IdentityReviewBatch:
    status=status.upper();queue_type=queue_type.upper() if queue_type else None;resolution_state=resolution_state.upper() if resolution_state else None
    if not universe.strip() or status not in {"PENDING","DEFERRED","PROPOSED"} or not 0<=min_priority<=100 or not 1<=limit<=100:raise IdentityReviewBatchError("invalid identity batch criteria")
    query=select(ReviewQueueItem).join(ResolutionDecision).where(ReviewQueueItem.status==status,ReviewQueueItem.priority>=min_priority)
    if queue_type:query=query.where(ReviewQueueItem.queue_type==queue_type)
    if resolution_state:query=query.where(ResolutionDecision.state==resolution_state)
    candidates=session.scalars(query.order_by(ReviewQueueItem.priority.desc(),ReviewQueueItem.id).limit(limit*50)).all();items=[]
    for item in candidates:
        packet=build_review_packet(session,item.id)
        if packet["universe"]!=universe:continue
        decision=session.get(ResolutionDecision,item.resolution_decision_id);items.append({"queue_item_id":item.id,"item_version":_version(item),"queue_type":item.queue_type,"priority":item.priority,"resolution_state":decision.state,"pair_fingerprint":pair_fingerprint(session,item,decision)})
        if len(items)>=limit:break
    criteria={"universe":universe,"status":status,"queue_type":queue_type,"resolution_state":resolution_state,"min_priority":min_priority,"limit":limit};manifest={"criteria":criteria,"items":items};digest=hashlib.sha256(_canonical(manifest).encode()).hexdigest();existing=session.scalar(select(IdentityReviewBatch).where(IdentityReviewBatch.manifest_hash==digest))
    if existing:return existing
    batch=IdentityReviewBatch(criteria_json=_canonical(criteria),manifest_hash=digest,item_count=len(items),created_by=actor);session.add(batch);session.flush()
    for item in items:session.add(IdentityReviewBatchItem(batch_id=batch.id,**item))
    session.flush();append_ledger_event(session,"IDENTITY_REVIEW_BATCH",batch.id,actor,"REVIEWER","BATCH_FROZEN",{"manifest_hash":digest,"item_count":len(items),"criteria":criteria});return batch

def build_identity_batch_packet(session,batch_id:int)->dict:
    batch=session.get(IdentityReviewBatch,batch_id)
    if not batch:raise IdentityReviewBatchError("unknown identity review batch")
    rows=session.scalars(select(IdentityReviewBatchItem).where(IdentityReviewBatchItem.batch_id==batch.id).order_by(IdentityReviewBatchItem.id)).all();items=[{"queue_item_id":x.queue_item_id,"item_version":x.item_version,"queue_type":x.queue_type,"priority":x.priority,"resolution_state":x.resolution_state,"pair_fingerprint":x.pair_fingerprint} for x in rows];manifest={"criteria":json.loads(batch.criteria_json),"items":items};valid=secrets.compare_digest(hashlib.sha256(_canonical(manifest).encode()).hexdigest(),batch.manifest_hash) and len(items)==batch.item_count
    return {"classification":"PRIVATE—AUTHORIZED IDENTITY REVIEW BATCH","id":batch.id,"status":batch.status,"criteria":manifest["criteria"],"manifest_hash":batch.manifest_hash,"item_count":batch.item_count,"manifest_valid":valid,"created_by":batch.created_by,"created_at":batch.created_at.isoformat(),"items":items}

def validate_identity_assignment(session,batch_id:int,item,decision,action:str)->IdentityReviewBatchItem:
    batch=session.get(IdentityReviewBatch,batch_id);batch_item=session.scalar(select(IdentityReviewBatchItem).where(IdentityReviewBatchItem.batch_id==batch_id,IdentityReviewBatchItem.queue_item_id==item.id)) if batch else None
    if not batch or batch.status!="FROZEN" or not batch_item or not build_identity_batch_packet(session,batch_id)["manifest_valid"]:raise IdentityReviewBatchError("a valid frozen identity review batch is required")
    if not secrets.compare_digest(batch_item.pair_fingerprint,pair_fingerprint(session,item,decision)):raise IdentityReviewBatchError("identity pair changed after batch assignment")
    if action!="APPROVE_MATCH" and batch_item.item_version!=_version(item):raise IdentityReviewBatchError("identity item changed after batch assignment; freeze a new batch")
    return batch_item
