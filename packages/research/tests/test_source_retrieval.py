from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Claim,Entity,EvidencePassage,ResearchDocumentSnapshot,ResearchPassageCandidate,ResearchSourceCandidate,SourceDocument
from pmos_research.source_retrieval import extract_predicate_passages,persist_retrieved_candidate,record_retrieval_outcome

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
