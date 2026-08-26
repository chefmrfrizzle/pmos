from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Claim,Entity,EvidencePassage,ResearchDocumentSnapshot,ResearchPassageCandidate,ResearchSourceCandidate,SourceDocument,SourceRetrievalAttempt
from pmos_research.source_retrieval import classify_http_status,extract_predicate_passages,persist_retrieved_candidate,record_retrieval_attempt,record_retrieval_outcome

def test_candidate_retrieval_queues_exact_passages_without_creating_claims():
    text="Our investment strategy focuses on private markets. We are regulated by the Example Authority."
    passages=extract_predicate_passages(text,["mandate","regulatory_status","ownership_control"])
    assert [x["predicate"] for x in passages]==["mandate","regulatory_status"] and all(x["passage"] in text for x in passages)
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Institution",canonical_name="institution",universe="asset_manager");db.add(entity);db.flush()
        candidate=ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example/strategy",source_domain="official.example",document_type="INVESTMENT_STRATEGY",target_predicates_json='["mandate","regulatory_status"]',discovered_from_url="https://official.example",discovery_score=80);db.add(candidate);db.flush()
        result=persist_retrieved_candidate(db,candidate,{"status":"ok","url":candidate.source_url,"title":"Strategy","text":text,"pages":[{"page":7,"text":text,"text_hash":"z"*64}],"hash":"wire-hash"});db.commit()
        assert result=={"passages_queued":2,"retrieved":1} and candidate.status=="RETRIEVED_REVIEW_REQUIRED"
        assert db.scalar(select(func.count()).select_from(ResearchDocumentSnapshot))==1
        assert db.scalar(select(func.count()).select_from(ResearchPassageCandidate))==2
        assert db.scalar(select(func.count()).select_from(SourceDocument))==1
        assert db.scalar(select(func.count()).select_from(Claim))==0
        assert {x.page for x in db.query(EvidencePassage).all()}=={"7"}

def test_nonretrievable_candidate_leaves_pending_queue_with_ledgered_outcome():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Institution",canonical_name="institution",universe="pension");db.add(entity);db.flush()
        candidate=ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example/report.pdf",source_domain="official.example",document_type="ANNUAL_REPORT",target_predicates_json='["governance"]',discovered_from_url="https://official.example",discovery_score=100);db.add(candidate);db.flush()
        assert record_retrieval_outcome(db,candidate,"unsupported_content_type")=="UNSUPPORTED_CONTENT_TYPE"
        assert candidate.status=="UNSUPPORTED_CONTENT_TYPE"

def test_institutional_phrase_variants_queue_only_requested_predicates():
    text="The supervisory board oversees our investment objectives. The management company is authorised by the regulator."
    passages=extract_predicate_passages(text,["governance","mandate","fund_manager","regulatory_status","legal_identity"])
    assert [x["predicate"] for x in passages]==["fund_manager","governance","mandate","regulatory_status"]
    assert all(x["passage"] in text for x in passages)

def test_generic_words_do_not_create_passage_candidates():
    text="Our board met to discuss investments and company news."
    assert extract_predicate_passages(text,["governance","mandate","legal_identity"])==[]

def test_investing_in_phrase_is_a_review_candidate_but_generic_investments_are_not():
    assert extract_predicate_passages("We focus on investing in climate technology.",["mandate"])[0]["matched_term"]=="investing in"

def test_retrieval_attempts_use_bounded_backoff_and_exhaust_after_three_attempts():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Institution",canonical_name="institution",universe="test");db.add(entity);db.flush()
        candidate=ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example/contact",source_domain="official.example",document_type="CONTACT_LOCATION",target_predicates_json='["address"]',discovered_from_url="https://official.example",status="RETRY_REQUIRED");db.add(candidate);db.flush()
        first=record_retrieval_attempt(db,candidate,"http_transient_error",True,"HTTPStatusError",503);second=record_retrieval_attempt(db,candidate,"http_transient_error",True,"HTTPStatusError",503);third=record_retrieval_attempt(db,candidate,"http_transient_error",True,"HTTPStatusError",503)
        assert first.retryable and second.retryable and first.next_attempt_at<second.next_attempt_at
        assert not third.retryable and third.next_attempt_at is None and candidate.status=="RETRY_EXHAUSTED"
        assert db.query(SourceRetrievalAttempt).count()==3
        assert classify_http_status(503)==("http_transient_error",True) and classify_http_status(404)==("http_permanent_error",False)
