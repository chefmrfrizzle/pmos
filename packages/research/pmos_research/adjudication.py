from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse
from sqlalchemy import select
from .db import Claim, CorroborationJob, Entity, Evidence, RawImportRow, ResolutionDecision, ReviewQueueItem
from .fact_extraction import identity_supported

PRIORITY_TYPES={"venture capital","private equity","corporate venture capital","family office","asset manager","hedge fund","government","limited partner","pension","sovereign wealth"}

def _domain(url:str|None)->str:
    return urlparse(url or "").netloc.lower().split(":")[0].removeprefix("www.")

def normalize_public_url(url:str|None)->str:
    value=(url or "").strip()
    if value and "://" not in value:value="https://"+value
    parsed=urlparse(value)
    return value if parsed.scheme in {"http","https"} and parsed.netloc else ""

def queue_priority(decision:ResolutionDecision,raw:RawImportRow|None,entity:Entity|None)->tuple[int,str,list[str]]:
    reasons=[]
    if decision.state=="CONFLICT":priority=100;reasons.append("deterministic conflict")
    elif decision.state=="PROBABLE_MATCH":priority=75;reasons.append("probable match requires human adjudication")
    else:priority=45;reasons.append("insufficient deterministic identity evidence")
    if decision.candidate_entity_id:
        kind="ENTITY"
        if entity and entity.official_url:priority+=10;reasons.append("candidate official URL available")
        if entity and (entity.entity_type or "").casefold() in PRIORITY_TYPES:priority+=10;reasons.append("priority institutional type")
    elif decision.candidate_contact_id:kind="CONTACT";priority+=5
    else:kind="UNRESOLVED"
    return min(priority,100),kind,reasons

def build_review_queue(session)->Counter:
    counts=Counter()
    decisions=session.scalars(select(ResolutionDecision).where(ResolutionDecision.state!="EXACT_MATCH").order_by(ResolutionDecision.id)).all()
    existing=set(session.scalars(select(ReviewQueueItem.resolution_decision_id)).all())
    for decision in decisions:
        if decision.id in existing:counts["existing"]+=1;continue
        raw=session.get(RawImportRow,decision.raw_row_id);entity=session.get(Entity,raw.entity_id) if raw and raw.entity_id else None
        priority,kind,reasons=queue_priority(decision,raw,entity)
        session.add(ReviewQueueItem(resolution_decision_id=decision.id,queue_type=kind,priority=priority,reasons_json=json.dumps(reasons)))
        counts[kind]+=1
    session.flush();return counts

def enqueue_corroboration(session,limit:int=0)->Counter:
    counts=Counter();seen=set()
    existing={(x.entity_id,x.source_url) for x in session.scalars(select(CorroborationJob)).all()}
    entities=session.scalars(select(Entity).where(Entity.official_url.is_not(None),Entity.official_url!="",Entity.mandate.is_not(None),Entity.mandate!="").order_by(Entity.entity_type,Entity.canonical_name,Entity.id)).all()
    for entity in entities:
        if entity.canonical_name in seen:counts["canonical_duplicate_skipped"]+=1;continue
        seen.add(entity.canonical_name);source_url=normalize_public_url(entity.official_url);domain=_domain(source_url)
        if not domain:counts["invalid_url"]+=1;continue
        if (entity.id,source_url) in existing:counts["existing"]+=1;continue
        session.add(CorroborationJob(entity_id=entity.id,source_url=source_url,source_domain=domain,status="PENDING",checkpoint_json="{}"))
        counts["queued"]+=1
        if limit and counts["queued"]>=limit:break
    session.flush();return counts

def queue_summary(session)->dict:
    review=Counter(x.status for x in session.scalars(select(ReviewQueueItem)).all())
    jobs=Counter(x.status for x in session.scalars(select(CorroborationJob)).all())
    return {"review_queue":dict(sorted(review.items())),"corroboration_jobs":dict(sorted(jobs.items())),"generated_at":datetime.now(timezone.utc).isoformat()}

def run_corroboration_job(session,job:CorroborationJob,adapter)->str:
    job.attempts+=1;job.updated_at=datetime.now(timezone.utc);entity=session.get(Entity,job.entity_id)
    try:
        snapshot=adapter.fetch(job.source_url)
        status=snapshot.get("status","failed")
        if status!="ok":
            job.status="BLOCKED" if status.startswith("robots_") else "NEEDS_REVIEW"
            job.last_error=status;return job.status
        source_url=snapshot["url"];content_hash=snapshot["hash"]
        duplicate=session.scalar(select(Evidence).where(Evidence.entity_id==entity.id,Evidence.source_url==source_url,Evidence.content_hash==content_hash))
        if not duplicate:session.add(Evidence(entity_id=entity.id,source_url=source_url,source_type="official",content_hash=content_hash,title=snapshot["title"],text_excerpt=snapshot["text"][:5000],confidence=.9))
        supported=identity_supported(entity.name,snapshot["title"]+" "+snapshot["text"][:10000])
        if supported:
            existing=session.scalar(select(Claim).where(Claim.entity_id==entity.id,Claim.field=="official_identity",Claim.value==entity.name,Claim.source_url==source_url,Claim.evidence_hash==content_hash))
            if not existing:session.add(Claim(entity_id=entity.id,field="official_identity",value=entity.name,source_url=source_url,source_type="official",confidence=.9,verification_status="SUPPORTED",extractor="deterministic_identity_v1",evidence_hash=content_hash))
            job.status="SUPPORTED";entity.verification_status="SUPPORTED";entity.evidence_confidence=max(entity.evidence_confidence,90)
        else:
            job.status="HUMAN_REVIEW_REQUIRED";entity.verification_status="EVIDENCE_COLLECTED";entity.evidence_confidence=max(entity.evidence_confidence,35)
        job.checkpoint_json=json.dumps({"source_url":source_url,"evidence_hash":content_hash,"identity_supported":supported},sort_keys=True)
        job.last_error=None;return job.status
    except Exception as exc:
        job.status="FAILED";job.last_error=f"{type(exc).__name__}: {exc}"[:1000];return job.status
