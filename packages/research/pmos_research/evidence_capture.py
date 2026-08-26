from __future__ import annotations

import hashlib
from urllib.parse import urlparse
from sqlalchemy import select

from .db import Claim,ClaimEvidence,Entity,EvidencePassage,SourceDocument
from .fact_extraction import identity_evidence_passage

def capture_official_identity_evidence(session,entity:Entity,claim:Claim,source_url:str,content_hash:str,title:str,text:str,retrieved_at=None):
    passage_data=identity_evidence_passage(entity.name,title,text)
    if not passage_data:raise ValueError("claim has no bounded identity evidence passage")
    host=(urlparse(source_url).hostname or "unknown").casefold().removeprefix("www.")
    document=session.scalar(select(SourceDocument).where(SourceDocument.source_url==source_url,SourceDocument.content_hash==content_hash))
    document_created=document is None
    if not document:
        document=SourceDocument(entity_id=entity.id,publisher=host,publisher_independence_group=host,source_rank="S1",source_type="official_website",source_url=source_url,title=title or None,content_hash=content_hash)
        if retrieved_at is not None:document.retrieved_at=retrieved_at
        session.add(document);session.flush()
    passage_hash=hashlib.sha256(passage_data["passage"].encode("utf-8")).hexdigest()
    passage=session.scalar(select(EvidencePassage).where(EvidencePassage.document_id==document.id,EvidencePassage.passage_hash==passage_hash))
    passage_created=passage is None
    if not passage:
        passage=EvidencePassage(document_id=document.id,section=passage_data["section"],start_offset=passage_data["start_offset"],end_offset=passage_data["end_offset"],passage=passage_data["passage"],passage_hash=passage_hash)
        session.add(passage);session.flush()
    link=session.scalar(select(ClaimEvidence).where(ClaimEvidence.claim_id==claim.id,ClaimEvidence.passage_id==passage.id))
    link_created=link is None
    if not link:
        link=ClaimEvidence(claim_id=claim.id,passage_id=passage.id,directness=passage_data["directness"],supports=True);session.add(link);session.flush()
    return {"document_id":document.id,"passage_id":passage.id,"claim_evidence_id":link.id,"document_created":document_created,"passage_created":passage_created,"link_created":link_created}
