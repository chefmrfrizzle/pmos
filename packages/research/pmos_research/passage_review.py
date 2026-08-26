from __future__ import annotations

from sqlalchemy import select

from .db import Entity,EvidencePassage,ResearchPassageAdjudicationEvent,ResearchPassageCandidate,ResearchSourceCandidate,SourceDocument

def build_passage_packet(session,candidate_id:int)->dict:
    candidate=session.get(ResearchPassageCandidate,candidate_id)
    if not candidate:raise ValueError("unknown passage candidate")
    source=session.get(ResearchSourceCandidate,candidate.source_candidate_id);entity=session.get(Entity,source.entity_id) if source else None
    passage=session.get(EvidencePassage,candidate.evidence_passage_id);document=session.get(SourceDocument,passage.document_id) if passage else None
    if not source or not entity or not passage or not document or document.entity_id!=entity.id:raise ValueError("candidate evidence chain is incomplete")
    events=session.scalars(select(ResearchPassageAdjudicationEvent).where(ResearchPassageAdjudicationEvent.passage_candidate_id==candidate.id).order_by(ResearchPassageAdjudicationEvent.id)).all()
    return {"classification":"PRIVATE—AUTHORIZED EVIDENCE REVIEW ONLY","id":candidate.id,"status":candidate.status,"predicate":candidate.predicate,"confidence":candidate.confidence,"universe":entity.universe,"entity":{"id":entity.id,"name":entity.name,"entity_type":entity.entity_type,"country":entity.country},"source":{"document_type":source.document_type,"source_rank":document.source_rank,"publisher":document.publisher,"source_url":document.source_url,"retrieved_at":document.retrieved_at.isoformat(),"content_hash":document.content_hash},"evidence":{"passage_id":passage.id,"section":passage.section,"passage":passage.passage,"passage_hash":passage.passage_hash,"start_offset":passage.start_offset,"end_offset":passage.end_offset},"history":[{"action":x.action,"prior_state":x.prior_state,"resulting_state":x.resulting_state,"reviewer":x.reviewer,"rationale":x.rationale,"claim_value":x.claim_value,"resulting_claim_id":x.resulting_claim_id,"occurred_at":x.occurred_at.isoformat()} for x in events]}
