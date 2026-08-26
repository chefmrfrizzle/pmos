#!/usr/bin/env python3
"""Backfill exact passages for supported official identity claims; never promotes state."""
from pathlib import Path
from collections import Counter
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from sqlalchemy import select
from pmos_research.db import Claim,Entity,Evidence,SessionLocal,init_db
from pmos_research.evidence_capture import capture_official_identity_evidence
from pmos_research.audit_ledger import append_ledger_event

init_db();counts=Counter()
with SessionLocal() as db:
    claims=db.scalars(select(Claim).where(Claim.field=="official_identity",Claim.verification_status=="SUPPORTED",Claim.source_type=="official").order_by(Claim.id)).all()
    for claim in claims:
        entity=db.get(Entity,claim.entity_id)
        evidence=db.scalar(select(Evidence).where(Evidence.entity_id==claim.entity_id,Evidence.source_url==claim.source_url,Evidence.content_hash==claim.evidence_hash))
        if not evidence:counts["missing_snapshot"]+=1;continue
        try:
            result=capture_official_identity_evidence(db,entity,claim,claim.source_url,claim.evidence_hash,evidence.title or "",evidence.text_excerpt or "",evidence.retrieved_at)
            counts["created" if result["link_created"] else "already_linked"]+=1
        except ValueError:counts["passage_not_found"]+=1
    append_ledger_event(db,"MAINTENANCE_JOB","IDENTITY_PASSAGE_BACKFILL","research-worker","SYSTEM","BACKFILL_COMPLETED",{"claims_seen":len(claims),"outcomes":dict(sorted(counts.items()))})
    db.commit()
print(json.dumps({"claims_seen":len(claims),"outcomes":dict(sorted(counts.items()))},sort_keys=True))
