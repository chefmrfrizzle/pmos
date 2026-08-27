#!/usr/bin/env python3
"""Quarantine unattempted private-universe web jobs and open aggregate-governed review cases for legacy attempts."""
from pathlib import Path
from collections import Counter
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from sqlalchemy import select
from pmos_research.audit_ledger import append_ledger_event
from pmos_research.db import CorroborationJob,Entity,PrivateEgressReviewCase,ResearchSourceCandidate,SourceRetrievalAttempt,SessionLocal,init_db
init_db();counts=Counter()
with SessionLocal() as db:
    jobs=db.scalars(select(CorroborationJob).join(Entity,Entity.id==CorroborationJob.entity_id).where(Entity.universe=="imported_private").order_by(CorroborationJob.id)).all()
    existing=set(db.scalars(select(PrivateEgressReviewCase.corroboration_job_id)).all())
    for job in jobs:
        if job.attempts==0:
            if job.status!="PRIVATE_EGRESS_QUARANTINED":job.status="PRIVATE_EGRESS_QUARANTINED";job.next_attempt_at=None;counts["quarantined_unattempted"]+=1
            else:counts["already_quarantined"]+=1
        elif job.id not in existing:
            db.add(PrivateEgressReviewCase(corroboration_job_id=job.id,prior_status=job.status,attempts_observed=job.attempts,status="OPEN",reason="Legacy public-web corroboration attempt involved an imported-private entity; security and policy review required."));counts["legacy_attempt_review_opened"]+=1
    candidates=db.scalars(select(ResearchSourceCandidate).join(Entity,Entity.id==ResearchSourceCandidate.entity_id).where(Entity.universe=="imported_private")).all()
    for candidate in candidates:
        attempts=len(db.scalars(select(SourceRetrievalAttempt).where(SourceRetrievalAttempt.source_candidate_id==candidate.id)).all())
        if attempts:counts["legacy_private_source_attempt_review_required"]+=1
        elif candidate.status!="PRIVATE_EGRESS_QUARANTINED":candidate.status="PRIVATE_EGRESS_QUARANTINED";counts["quarantined_unattempted_sources"]+=1
    append_ledger_event(db,"PRIVATE_EGRESS_CONTROL","CORROBORATION","security-migration","SYSTEM","PRIVATE_CORROBORATION_QUARANTINED",dict(sorted(counts.items())));db.commit()
print(json.dumps(dict(sorted(counts.items())),sort_keys=True))
