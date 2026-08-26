import hashlib
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Entity,EvidencePassage,SourceDocument
from pmos_research.publisher_independence import PublisherIndependenceError,adjudicate_publisher_independence,approved_independence_group,build_publisher_independence_packet,propose_publisher_independence

def _fixture(db):
    entity=Entity(name="Example",canonical_name="example",universe="private_equity");db.add(entity);db.flush();text="The publisher disclosure identifies Example Media Holdings as the controlling publisher group.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=entity.id,publisher="news.example",publisher_independence_group="example-media",source_rank="S2",source_type="publisher_disclosure",source_url="https://news.example/ownership",content_hash=digest);db.add(document);db.flush();passage=EvidencePassage(document_id=document.id,section="ownership",passage=text,passage_hash=digest);db.add(passage);db.flush();return document,passage

def test_publisher_independence_requires_exact_evidence_and_maker_checker():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        document,passage=_fixture(db);assessment=propose_publisher_independence(db,"news.example","example-media","maker","Publisher ownership disclosure supports the proposed group",[passage.id])
        assert approved_independence_group(db,document) is None
        with pytest.raises(PublisherIndependenceError,match="independent reviewer"):adjudicate_publisher_independence(db,assessment.id,"APPROVE","maker","Maker cannot approve the same assessment","HUMAN_REVIEW_REQUIRED")
        adjudicate_publisher_independence(db,assessment.id,"APPROVE","checker","Independent review confirms the disclosed control group","HUMAN_REVIEW_REQUIRED")
        packet=build_publisher_independence_packet(db,assessment.id);assert packet["status"]=="APPROVED" and len(packet["evidence"])==1 and approved_independence_group(db,document)=="example-media"

def test_publisher_independence_rejects_domain_substring_and_changed_evidence():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        _,passage=_fixture(db)
        with pytest.raises(PublisherIndependenceError,match="not been observed"):propose_publisher_independence(db,"evil-news.example","example-media","maker","Substring domains must not be accepted",[passage.id])
        assessment=propose_publisher_independence(db,"news.example","example-media","maker","Publisher ownership disclosure supports the proposed group",[passage.id]);passage.passage_hash="0"*64;db.flush()
        with pytest.raises(PublisherIndependenceError,match="changed after proposal"):adjudicate_publisher_independence(db,assessment.id,"APPROVE","checker","Changed evidence cannot support approval","HUMAN_REVIEW_REQUIRED")

def test_rejected_publisher_assessment_can_be_reproposed_as_new_version():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        _,passage=_fixture(db);first=propose_publisher_independence(db,"news.example","example-media","maker","Initial publisher control assessment",[passage.id]);adjudicate_publisher_independence(db,first.id,"REJECT","checker","Evidence does not yet establish ultimate control","HUMAN_REVIEW_REQUIRED")
        second=propose_publisher_independence(db,"news.example","example-media","maker-2","Revised publisher control assessment with reviewed evidence",[passage.id]);assert first.version==1 and second.version==2 and second.status=="HUMAN_REVIEW_REQUIRED"
