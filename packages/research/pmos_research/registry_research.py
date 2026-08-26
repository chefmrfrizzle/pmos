from __future__ import annotations

import hashlib
import json
from difflib import SequenceMatcher
from sqlalchemy import select

from .adapters.gleif import search_lei
from .audit_ledger import append_ledger_event
from .db import Claim,ClaimEvidence,Entity,EvidencePassage,RegistryIdentifierCandidate,SourceDocument
from .entity_resolution import canonicalize_name

def assess_lei_candidate(entity:Entity,record:dict)->tuple[str,float,list[str]]:
    incoming=canonicalize_name(entity.name);legal=canonicalize_name(record["legal_name"]);similarity=SequenceMatcher(None,incoming,legal).ratio();reasons=[]
    country=(record.get("jurisdiction") or record.get("legal_address_country") or "").split("-",1)[0].casefold();expected=(entity.country or "").casefold()
    if incoming==legal:reasons.append("same normalized legal name")
    else:reasons.append(f"legal-name similarity {similarity:.2f}")
    if expected and country==expected:reasons.append("compatible jurisdiction")
    elif expected and country and country!=expected:return "CONFLICT",.25,reasons+["conflicting jurisdiction"]
    if incoming==legal and expected and country==expected:return "PROBABLE_MATCH",.92,reasons
    if incoming==legal:return "POSSIBLE_MATCH",.8,reasons+["jurisdiction not corroborated"]
    if similarity>=.9 and (not expected or country==expected):return "POSSIBLE_MATCH",round(similarity*.85,2),reasons
    return "REQUIRES_REVIEW",round(similarity*.6,2),reasons

def persist_lei_candidate(session,entity:Entity,record:dict):
    existing=session.scalar(select(RegistryIdentifierCandidate).where(RegistryIdentifierCandidate.entity_id==entity.id,RegistryIdentifierCandidate.identifier_type=="LEI",RegistryIdentifierCandidate.identifier_value==record["lei"]))
    if existing:return existing,False
    state,confidence,reasons=assess_lei_candidate(entity,record);source_url=record["record_url"]
    document=session.scalar(select(SourceDocument).where(SourceDocument.source_url==source_url,SourceDocument.content_hash==record["content_hash"]))
    if not document:
        document=SourceDocument(entity_id=entity.id,publisher="Global Legal Entity Identifier Foundation",publisher_independence_group="gleif.org",source_rank="S2",source_type="market_infrastructure",source_url=source_url,document_id=record["lei"],title=f"GLEIF LEI record {record['lei']}",jurisdiction=record.get("jurisdiction"),content_hash=record["content_hash"]);session.add(document);session.flush()
    passage_value=json.dumps({k:record.get(k) for k in ("lei","legal_name","entity_status","jurisdiction","legal_address_country","legal_form_id","registration_authority_id","registration_authority_entity_id","lei_registration_status","initial_registration_date","last_update_date","next_renewal_date")},sort_keys=True,separators=(",",":"),ensure_ascii=False)
    passage_hash=hashlib.sha256(passage_value.encode()).hexdigest();passage=session.scalar(select(EvidencePassage).where(EvidencePassage.document_id==document.id,EvidencePassage.passage_hash==passage_hash))
    if not passage:
        passage=EvidencePassage(document_id=document.id,section="structured LEI record",passage=passage_value,passage_hash=passage_hash);session.add(passage);session.flush()
    claim=Claim(entity_id=entity.id,field="lei_candidate",value=record["lei"],source_url=source_url,source_type="market_infrastructure",confidence=confidence,verification_status="CANDIDATE",extractor="gleif_candidate_v1",evidence_hash=record["content_hash"]);session.add(claim);session.flush()
    session.add(ClaimEvidence(claim_id=claim.id,passage_id=passage.id,directness=.98,supports=True));session.flush()
    candidate=RegistryIdentifierCandidate(entity_id=entity.id,identifier_type="LEI",identifier_value=record["lei"],legal_name=record["legal_name"],jurisdiction=record.get("jurisdiction") or record.get("legal_address_country"),registry_status=record.get("lei_registration_status"),source_document_id=document.id,claim_id=claim.id,match_state=state,confidence=confidence,reasons_json=json.dumps(reasons),status="PENDING_REVIEW")
    session.add(candidate);session.flush();return candidate,True

def research_entity_lei(session,entity:Entity,limit=5)->dict:
    records=search_lei(entity.name,entity.country,limit);counts={}
    for record in records:
        candidate,created=persist_lei_candidate(session,entity,record);key=("created:" if created else "existing:")+candidate.match_state;counts[key]=counts.get(key,0)+1
    append_ledger_event(session,"REGISTRY_RESEARCH",entity.id,"registry-worker","SYSTEM","GLEIF_SEARCH_COMPLETED",{"records_returned":len(records),"candidate_outcomes":dict(sorted(counts.items()))})
    return {"records_returned":len(records),"candidate_outcomes":dict(sorted(counts.items()))}
