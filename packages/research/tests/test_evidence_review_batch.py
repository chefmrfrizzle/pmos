import hashlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Entity,EvidencePassage,EvidenceReviewBatchItem,ResearchDocumentSnapshot,ResearchPassageCandidate,ResearchSourceCandidate,SourceDocument
from pmos_research.evidence_review_batch import build_batch_packet,freeze_review_batch

def _fixture(db):
    entity=Entity(name="Example",canonical_name="example",universe="pensions");db.add(entity);db.flush();source=ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example/about",source_domain="official.example",document_type="LEGAL_IDENTITY",target_predicates_json='["legal_identity"]',discovered_from_url="https://official.example",status="RETRIEVED_REVIEW_REQUIRED");db.add(source);db.flush();text="The legal name is Example Pension Fund.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=entity.id,publisher="official.example",publisher_independence_group="official.example",source_rank="S1",source_type="official_website",source_url=source.source_url,content_hash=digest);db.add(document);db.flush();db.add(ResearchDocumentSnapshot(source_candidate_id=source.id,source_document_id=document.id,normalized_text=text,text_hash=digest));passage=EvidencePassage(document_id=document.id,passage=text,passage_hash=digest);db.add(passage);db.flush();candidate=ResearchPassageCandidate(source_candidate_id=source.id,evidence_passage_id=passage.id,predicate="legal_identity",confidence=.9);db.add(candidate);db.flush();return candidate

def test_review_batch_freezes_hashes_and_detects_manifest_tampering():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        candidate=_fixture(db);batch=freeze_review_batch(db,"reviewer","pensions",min_confidence=.8);db.commit();packet=build_batch_packet(db,batch.id)
        assert packet["manifest_valid"] is True and packet["item_count"]==1 and packet["items"][0]["passage_candidate_id"]==candidate.id
        item=db.query(EvidenceReviewBatchItem).filter_by(batch_id=batch.id).one();item.document_hash="0"*64;db.commit();assert build_batch_packet(db,batch.id)["manifest_valid"] is False

def test_freeze_excludes_candidates_already_in_active_batch_and_is_idempotent():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        first_candidate=_fixture(db);first=freeze_review_batch(db,"reviewer","pensions",min_confidence=.8);assert freeze_review_batch(db,"reviewer","pensions",min_confidence=.8).id==first.id
        source=db.get(ResearchSourceCandidate,first_candidate.source_candidate_id);document=db.get(SourceDocument,db.get(EvidencePassage,first_candidate.evidence_passage_id).document_id);text="Second exact evidence passage";passage=EvidencePassage(document_id=document.id,section="second",passage=text,passage_hash=hashlib.sha256(text.encode()).hexdigest());db.add(passage);db.flush();second_candidate=ResearchPassageCandidate(source_candidate_id=source.id,evidence_passage_id=passage.id,predicate="mandate",confidence=.9,extractor="test",status="HUMAN_REVIEW_REQUIRED");db.add(second_candidate);db.flush();second=freeze_review_batch(db,"reviewer","pensions",min_confidence=.8);packet=build_batch_packet(db,second.id);assert second.id!=first.id and packet["item_count"]==1 and packet["items"][0]["passage_candidate_id"]==second_candidate.id
