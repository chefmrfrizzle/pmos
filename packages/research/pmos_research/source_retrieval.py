from __future__ import annotations

import hashlib,json,re
from collections import Counter
from datetime import datetime,timedelta,timezone
from urllib.parse import urlparse

from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import EvidencePassage,ResearchDocumentSnapshot,ResearchPassageCandidate,ResearchSourceCandidate,SourceDocument,SourceRetrievalAttempt

PREDICATE_TERMS={
    "legal_identity":("legal name","incorporated","registered as","company number","registered company","legal entity"),
    "legal_status":("statutory body","public authority","established by","legal status","formed under the laws"),
    "regulatory_status":("regulated by","authorised by","authorized by","registered with","supervised by","licence","license"),
    "governance":("board of directors","board of trustees","supervisory board","governing body","management committee","governance","executive committee"),
    "mandate":("investment strategy","investment mandate","investment objective","investment objectives","investment focus","investment themes","portfolio strategy","asset allocation","we invest","invests in","investing in","asset classes","investment approach"),
    "fund_manager":("fund manager","investment manager","management company","investment adviser","investment advisor","general partner","managed by","advised by"),
    "fund_domicile":("fund domicile","domiciled in","established in","registered in","registered office","formed under the laws"),
    "address":("registered office","head office","contact us","our offices"),
    "relationship":("partnered with","partnership with","strategic partnership","co-invested with","co-investment with","invested in","investment in","allocated to","allocation to","advises","advisor to","adviser to","manages","manager of"),
}
OUTCOME_STATES={
    "robots_blocked_or_unavailable":"BLOCKED_ROBOTS",
    "unsupported_content_type":"UNSUPPORTED_CONTENT_TYPE",
    "response_too_large":"BLOCKED_SIZE",
    "invalid_pdf_signature":"INVALID_PDF",
    "pdf_extraction_failed":"PDF_EXTRACTION_FAILED",
    "pdf_no_extractable_text":"PDF_NO_EXTRACTABLE_TEXT",
    "http_permanent_error":"HTTP_ERROR_REVIEW_REQUIRED",
    "http_transient_error":"RETRY_REQUIRED",
    "persist_failed":"RETRY_REQUIRED",
}

def classify_http_status(status:int)->tuple[str,bool]:
    retryable=status in {408,425,429} or status>=500
    return ("http_transient_error",True) if retryable else ("http_permanent_error",False)

def record_retrieval_attempt(session,candidate:ResearchSourceCandidate,outcome:str,retryable:bool,error_class:str|None=None,http_status:int|None=None,actor:str="research-worker")->SourceRetrievalAttempt:
    previous=session.scalars(select(SourceRetrievalAttempt).where(SourceRetrievalAttempt.source_candidate_id==candidate.id).order_by(SourceRetrievalAttempt.attempt_number.desc()).limit(1)).first()
    number=(previous.attempt_number if previous else 0)+1
    delay=min(24*60,15*(2**(number-1))) if retryable else 0
    next_at=datetime.now(timezone.utc)+timedelta(minutes=delay) if retryable and number<3 else None
    attempt=SourceRetrievalAttempt(source_candidate_id=candidate.id,attempt_number=number,outcome=outcome,error_class=error_class,http_status=http_status,retryable=retryable and number<3,next_attempt_at=next_at);session.add(attempt);session.flush()
    if retryable and number>=3:candidate.status="RETRY_EXHAUSTED";candidate.updated_at=datetime.now(timezone.utc)
    append_ledger_event(session,"SOURCE_RETRIEVAL_ATTEMPT",attempt.id,actor,"SYSTEM","ATTEMPT_RECORDED",{"source_candidate_id":candidate.id,"attempt_number":number,"outcome":outcome,"error_class":error_class,"http_status":http_status,"retryable":attempt.retryable,"next_attempt_at":next_at.isoformat() if next_at else None})
    return attempt

def extract_predicate_passages(text:str,predicates:list[str],max_chars:int=700)->list[dict]:
    compact=" ".join((text or "").split());lower=compact.casefold();results=[]
    for predicate in sorted(set(predicates)):
        hits=[]
        for term in PREDICATE_TERMS.get(predicate,()):
            match=re.search(rf"\b{re.escape(term)}\b",lower)
            if match:hits.append((match.start(),term))
        if not hits:continue
        position,term=min(hits);start=max(0,position-max_chars//3);end=min(len(compact),start+max_chars)
        if start:
            boundary=compact.find(" ",start);start=boundary+1 if boundary!=-1 else start
        if end<len(compact):
            boundary=compact.rfind(" ",start,end);end=boundary if boundary>start else end
        passage=compact[start:end].strip()
        results.append({"predicate":predicate,"passage":passage,"start_offset":start,"end_offset":end,"matched_term":term,"confidence":.75 if len(hits)>1 else .6})
    return results

def queue_extracted_passages(session,candidate:ResearchSourceCandidate,document:SourceDocument,items:list[dict])->Counter:
    counts=Counter()
    for item in items:
        passage_hash=hashlib.sha256(item["passage"].encode()).hexdigest()
        passage=session.scalar(select(EvidencePassage).where(EvidencePassage.document_id==document.id,EvidencePassage.passage_hash==passage_hash))
        if not passage:
            passage=EvidencePassage(document_id=document.id,page=item.get("page"),section=f"candidate:{item['predicate']}:{item['matched_term']}",start_offset=item["start_offset"],end_offset=item["end_offset"],passage=item["passage"],passage_hash=passage_hash);session.add(passage);session.flush()
        existing=session.scalar(select(ResearchPassageCandidate).where(ResearchPassageCandidate.source_candidate_id==candidate.id,ResearchPassageCandidate.evidence_passage_id==passage.id,ResearchPassageCandidate.predicate==item["predicate"]))
        if not existing:
            session.add(ResearchPassageCandidate(source_candidate_id=candidate.id,evidence_passage_id=passage.id,predicate=item["predicate"],confidence=item["confidence"]));counts["passages_queued"]+=1
    return counts

def queue_passage_candidates(session,candidate:ResearchSourceCandidate,document:SourceDocument,text:str,predicates:list[str],page:str|None=None)->Counter:
    """Queue deterministic exact passages for human review; never create or promote claims."""
    items=[{**item,"page":page} for item in extract_predicate_passages(text,predicates)]
    return queue_extracted_passages(session,candidate,document,items)

def persist_retrieved_candidate(session,candidate:ResearchSourceCandidate,snapshot:dict,actor:str="research-worker")->Counter:
    if snapshot.get("status")!="ok":raise ValueError("only successful HTML snapshots can be persisted")
    if urlparse(snapshot["url"]).hostname.casefold().removeprefix("www.")!=candidate.source_domain:raise ValueError("retrieved document left the approved source domain")
    text=" ".join(snapshot.get("text","").split())[:50000]
    if not text:raise ValueError("retrieved document has no normalized text")
    digest=hashlib.sha256(text.encode()).hexdigest()
    document=session.scalar(select(SourceDocument).where(SourceDocument.source_url==snapshot["url"],SourceDocument.content_hash==digest))
    if not document:
        document=SourceDocument(entity_id=candidate.entity_id,publisher=candidate.source_domain,publisher_independence_group=candidate.source_domain,source_rank="S1",source_type="official_website",source_url=snapshot["url"],title=snapshot.get("title") or None,content_hash=digest);session.add(document);session.flush()
    stored=session.scalar(select(ResearchDocumentSnapshot).where(ResearchDocumentSnapshot.source_candidate_id==candidate.id,ResearchDocumentSnapshot.text_hash==digest))
    if not stored:session.add(ResearchDocumentSnapshot(source_candidate_id=candidate.id,source_document_id=document.id,normalized_text=text,text_hash=digest));session.flush()
    predicates=json.loads(candidate.target_predicates_json);counts=Counter();passages=[]
    if snapshot.get("pages"):
        for page in snapshot["pages"]:
            for item in extract_predicate_passages(page.get("text",""),predicates):passages.append({**item,"page":str(page["page"])})
    else:passages=[{**item,"page":None} for item in extract_predicate_passages(text,predicates)]
    counts.update(queue_extracted_passages(session,candidate,document,passages[:25]))
    prior=candidate.status;candidate.status="RETRIEVED_REVIEW_REQUIRED";candidate.updated_at=datetime.now(timezone.utc)
    append_ledger_event(session,"SOURCE_CANDIDATE",candidate.id,actor,"SYSTEM","DOCUMENT_RETRIEVED",{"entity_id":candidate.entity_id,"prior_state":prior,"resulting_state":candidate.status,"document_id":document.id,"content_hash":digest,"target_predicates":predicates,"passages_queued":counts["passages_queued"]})
    session.flush();counts["retrieved"]+=1;return counts

def record_retrieval_outcome(session,candidate:ResearchSourceCandidate,outcome:str,actor:str="research-worker")->str:
    prior=candidate.status;result=OUTCOME_STATES.get(outcome,"RETRY_REQUIRED")
    candidate.status=result;candidate.updated_at=datetime.now(timezone.utc)
    append_ledger_event(session,"SOURCE_CANDIDATE",candidate.id,actor,"SYSTEM","RETRIEVAL_NOT_COMPLETED",{"entity_id":candidate.entity_id,"prior_state":prior,"resulting_state":result,"outcome":outcome})
    session.flush();return result
