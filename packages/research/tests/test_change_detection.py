from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker

from pmos_research.change_detection import persist_reverification
from pmos_research.change_review import adjudicate_change,build_change_packet
from pmos_research.db import Base,Claim,Entity,ResearchDocumentSnapshot,ResearchSourceCandidate,SourceChangeEvent,SourceChangeReviewEvent
from pmos_research.source_retrieval import persist_retrieved_candidate

def test_reverification_preserves_snapshots_and_queues_changed_source_for_review():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Example Institution",canonical_name="example institution",universe="pension");db.add(entity);db.flush()
        candidate=ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example/strategy",source_domain="official.example",document_type="INVESTMENT_STRATEGY",target_predicates_json='["mandate"]',discovered_from_url="https://official.example",discovery_score=80);db.add(candidate);db.flush()
        first={"status":"ok","url":candidate.source_url,"title":"Strategy","text":"Our investment mandate covers private markets.","hash":"a"*64};persist_retrieved_candidate(db,candidate,first);db.commit()
        second={"status":"ok","url":candidate.source_url,"title":"Strategy","text":"Our investment mandate covers private markets and infrastructure.","hash":"b"*64};result=persist_reverification(db,candidate,second);db.commit()
        assert result["status"]=="HUMAN_REVIEW_REQUIRED" and result["similarity"]<1
        assert db.scalar(select(func.count()).select_from(ResearchDocumentSnapshot))==2
        assert db.scalar(select(func.count()).select_from(Claim))==0
        event=db.get(SourceChangeEvent,result["change_event_id"]);packet=build_change_packet(db,event.id)
        assert packet["comparison"]["changes"] and packet["comparison"]["resulting_hash"]!=packet["comparison"]["prior_hash"]
        decision=adjudicate_change(db,event.id,"ACKNOWLEDGE","reviewer","Reviewed the strategy addition and queued predicate reassessment","HUMAN_REVIEW_REQUIRED");db.commit()
        assert decision["resulting_state"]=="ACKNOWLEDGED" and db.scalar(select(func.count()).select_from(SourceChangeReviewEvent))==1

def test_unchanged_reverification_reuses_snapshot_and_creates_no_claim():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Example Institution",canonical_name="example institution",universe="pension");db.add(entity);db.flush()
        candidate=ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example/about",source_domain="official.example",document_type="LEGAL_IDENTITY",target_predicates_json='["legal_identity"]',discovered_from_url="https://official.example",discovery_score=80);db.add(candidate);db.flush()
        snapshot={"status":"ok","url":candidate.source_url,"title":"About","text":"The legal name is Example Institution.","hash":"a"*64};persist_retrieved_candidate(db,candidate,snapshot);db.commit()
        result=persist_reverification(db,candidate,snapshot);db.commit()
        assert result["status"]=="UNCHANGED" and result["similarity"]==1
        assert db.scalar(select(func.count()).select_from(ResearchDocumentSnapshot))==1
        assert db.scalar(select(func.count()).select_from(Claim))==0
