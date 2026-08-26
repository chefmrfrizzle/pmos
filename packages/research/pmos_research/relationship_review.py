from __future__ import annotations

from sqlalchemy import select

from .db import Entity,EvidencePassage,RelationshipAdjudicationEvent,RelationshipAssertion,RelationshipAssertionEvidence,SourceDocument
from .relationship_controls import relationship_evidence_controls

def build_relationship_packet(session,assertion_id:int)->dict:
    assertion=session.get(RelationshipAssertion,assertion_id)
    if not assertion:raise ValueError("unknown relationship assertion")
    source=session.get(Entity,assertion.from_entity_id);target=session.get(Entity,assertion.to_entity_id)
    if not source or not target:raise ValueError("relationship entity chain is incomplete")
    rows=session.execute(select(RelationshipAssertionEvidence,EvidencePassage,SourceDocument).join(EvidencePassage,RelationshipAssertionEvidence.evidence_passage_id==EvidencePassage.id).join(SourceDocument,RelationshipAssertionEvidence.source_document_id==SourceDocument.id).where(RelationshipAssertionEvidence.relationship_assertion_id==assertion.id).order_by(SourceDocument.id,EvidencePassage.id)).all()
    events=session.scalars(select(RelationshipAdjudicationEvent).where(RelationshipAdjudicationEvent.relationship_assertion_id==assertion.id).order_by(RelationshipAdjudicationEvent.id)).all()
    evidence=[{"source_document_id":document.id,"passage_id":passage.id,"source_rank":document.source_rank,"publisher":document.publisher,"independence_group":document.publisher_independence_group,"source_url":document.source_url,"retrieved_at":document.retrieved_at.isoformat(),"document_hash":document.content_hash,"passage_hash":passage.passage_hash,"page":passage.page,"section":passage.section,"passage":passage.passage} for _,passage,document in rows]
    history=[{"action":x.action,"prior_state":x.prior_state,"resulting_state":x.resulting_state,"actor":x.actor,"rationale":x.rationale,"evidence_package_hash":x.evidence_package_hash,"occurred_at":x.occurred_at.isoformat()} for x in events]
    return {"classification":"PRIVATE—AUTHORIZED RELATIONSHIP REVIEW ONLY","id":assertion.id,"status":assertion.status,"relation_type":assertion.relation_type,"sensitive":assertion.sensitive,"jurisdiction":assertion.jurisdiction,"source_entity":{"id":source.id,"name":source.name,"universe":source.universe,"entity_type":source.entity_type,"country":source.country},"target_entity":{"id":target.id,"name":target.name,"universe":target.universe,"entity_type":target.entity_type,"country":target.country},"evidence_controls":relationship_evidence_controls(session,assertion),"evidence":evidence,"history":history,"proposed_by":assertion.proposed_by,"reviewed_by":assertion.reviewed_by,"review_rationale":assertion.review_rationale}
