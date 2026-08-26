from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from .db import AuditLedgerEntry

GENESIS = "0" * 64

def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def _hash(previous_hash: str, event: dict) -> str:
    return hashlib.sha256((previous_hash + "|" + _canonical(event)).encode("utf-8")).hexdigest()

def append_ledger_event(session, stream_type: str, stream_id: str | int, actor_id: str, actor_role: str, action: str, payload: dict, correlation_id: str | None = None):
    if not all(str(x).strip() for x in (stream_type, stream_id, actor_id, actor_role, action)):
        raise ValueError("stream, authenticated actor, role, and action are required")
    sid=str(stream_id)
    previous=session.scalar(select(AuditLedgerEntry).where(AuditLedgerEntry.stream_type==stream_type,AuditLedgerEntry.stream_id==sid).order_by(AuditLedgerEntry.sequence.desc()).limit(1))
    sequence=1 if previous is None else previous.sequence+1
    previous_hash=GENESIS if previous is None else previous.event_hash
    occurred_at=datetime.now(timezone.utc)
    correlation_id=correlation_id or str(uuid.uuid4())
    event={"stream_type":stream_type,"stream_id":sid,"sequence":sequence,"actor_id":actor_id,"actor_role":actor_role,"action":action,"payload":payload,"correlation_id":correlation_id,"occurred_at":occurred_at.isoformat()}
    entry=AuditLedgerEntry(stream_type=stream_type,stream_id=sid,sequence=sequence,actor_id=actor_id,actor_role=actor_role,action=action,payload_json=_canonical(payload),previous_hash=previous_hash,event_hash=_hash(previous_hash,event),correlation_id=correlation_id,occurred_at=occurred_at)
    session.add(entry);session.flush();return entry

def verify_ledger(session, stream_type: str | None = None, stream_id: str | int | None = None) -> dict:
    query=select(AuditLedgerEntry)
    if stream_type is not None:query=query.where(AuditLedgerEntry.stream_type==stream_type)
    if stream_id is not None:query=query.where(AuditLedgerEntry.stream_id==str(stream_id))
    rows=session.scalars(query.order_by(AuditLedgerEntry.stream_type,AuditLedgerEntry.stream_id,AuditLedgerEntry.sequence)).all()
    errors=[];previous={}
    for row in rows:
        key=(row.stream_type,row.stream_id);expected_previous=previous.get(key,GENESIS)
        occurred=row.occurred_at
        if occurred.tzinfo is None:occurred=occurred.replace(tzinfo=timezone.utc)
        event={"stream_type":row.stream_type,"stream_id":row.stream_id,"sequence":row.sequence,"actor_id":row.actor_id,"actor_role":row.actor_role,"action":row.action,"payload":json.loads(row.payload_json),"correlation_id":row.correlation_id,"occurred_at":occurred.isoformat()}
        expected_hash=_hash(expected_previous,event)
        if row.previous_hash!=expected_previous:errors.append({"entry_id":row.id,"error":"previous_hash_mismatch"})
        if row.event_hash!=expected_hash:errors.append({"entry_id":row.id,"error":"event_hash_mismatch"})
        previous[key]=row.event_hash
    return {"valid":not errors,"entries":len(rows),"errors":errors}
