from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import Entity, RelationshipAssertion, RelationshipAssertionEvidence, SourceDocument

SENSITIVE_RELATIONSHIPS={"OWNS","CONTROLS","BENEFICIAL_OWNER_OF","TRUSTEE_OF"}
QUALIFYING_CORROBORATION={"S0","S1","S2","S3"}

def _documents(session,ids):
    ids=sorted(set(int(x) for x in ids))
    rows=session.scalars(select(SourceDocument).where(SourceDocument.id.in_(ids))).all() if ids else []
    if len(rows)!=len(ids):raise ValueError("all source documents must exist")
    return rows

def propose_relationship(session,from_entity_id:int,to_entity_id:int,relation_type:str,proposer:str,source_document_ids, jurisdiction:str|None=None):
    relation_type=relation_type.upper()
    if from_entity_id==to_entity_id:raise ValueError("self-relationships require a separate specialist workflow")
    if not session.get(Entity,from_entity_id) or not session.get(Entity,to_entity_id):raise ValueError("both entities must exist")
    documents=_documents(session,source_document_ids)
    if not documents:raise ValueError("relationship assertions require source evidence")
    assertion=RelationshipAssertion(from_entity_id=from_entity_id,to_entity_id=to_entity_id,relation_type=relation_type,jurisdiction=jurisdiction,sensitive=relation_type in SENSITIVE_RELATIONSHIPS,status="HUMAN_REVIEW_REQUIRED",proposed_by=proposer)
    session.add(assertion);session.flush()
    for document in documents:session.add(RelationshipAssertionEvidence(relationship_assertion_id=assertion.id,source_document_id=document.id))
    append_ledger_event(session,"RELATIONSHIP_ASSERTION",assertion.id,proposer,"RESEARCHER","PROPOSED",{"relation_type":relation_type,"source_document_ids":sorted(x.id for x in documents),"sensitive":assertion.sensitive})
    return assertion

def verify_relationship(session,assertion_id:int,reviewer:str,rationale:str):
    assertion=session.get(RelationshipAssertion,assertion_id)
    if not assertion:raise ValueError("unknown relationship assertion")
    if assertion.status!="HUMAN_REVIEW_REQUIRED":raise ValueError("relationship assertion is not reviewable")
    if reviewer==assertion.proposed_by:raise ValueError("independent reviewer required")
    if not rationale.strip():raise ValueError("review rationale is required")
    documents=session.scalars(select(SourceDocument).join(RelationshipAssertionEvidence,RelationshipAssertionEvidence.source_document_id==SourceDocument.id).where(RelationshipAssertionEvidence.relationship_assertion_id==assertion.id)).all()
    ranks={x.source_rank for x in documents};independence={x.publisher_independence_group for x in documents if x.source_rank in QUALIFYING_CORROBORATION}
    if assertion.sensitive:
        sufficient="S0" in ranks
    else:
        sufficient="S0" in ranks or (len(independence)>=2 and bool(ranks & {"S1","S2"}))
    if not sufficient:raise ValueError("evidence does not meet relationship verification policy")
    assertion.status="SPECIALIST_VERIFIED";assertion.reviewed_by=reviewer;assertion.review_rationale=rationale;assertion.reviewed_at=datetime.now(timezone.utc)
    append_ledger_event(session,"RELATIONSHIP_ASSERTION",assertion.id,reviewer,"REVIEWER","SPECIALIST_VERIFIED",{"rationale":rationale,"source_ranks":sorted(ranks),"independence_groups":sorted(independence)})
    return assertion
