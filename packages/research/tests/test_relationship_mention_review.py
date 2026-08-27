import hashlib
from datetime import datetime,timedelta,timezone
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Entity,EvidencePassage,RelationshipMentionCandidate,RelationshipMentionReviewBatchItem,SourceDocument
from pmos_research.relationship_mention_review import RelationshipMentionReviewError,assign_mention_reviewer,assigned_mention_batch_items,build_mention_review_batch_packet,close_mention_review_batch,freeze_mention_review_batch,freeze_pending_mention_batches,validate_mention_review_decision
from pmos_research.relationship_research import discover_relationship_candidates

def _mention(db):
    source=Entity(name="Alpha Capital",canonical_name="alpha capital",universe="venture_capital");db.add(source);db.flush();text="Alpha Capital partnered with Gamma Partners.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=source.id,publisher="alpha.example",publisher_independence_group="alpha.example",source_rank="S1",source_type="official_website",source_url="https://alpha.example/news",content_hash=digest);db.add(document);db.flush();db.add(EvidencePassage(document_id=document.id,passage=text,passage_hash=digest));db.flush();discover_relationship_candidates(db);return db.scalar(select(RelationshipMentionCandidate))

def test_mention_batch_manifest_detects_tampering_and_close_revokes_assignments():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        _mention(db);batch=freeze_mention_review_batch(db,"admin","venture_capital");
        with pytest.raises(RelationshipMentionReviewError,match="assignment"):assigned_mention_batch_items(db,batch.id,"unassigned","RESEARCHER")
        assign_mention_reviewer(db,batch.id,"maker","RESEARCHER","admin","Maker assigned to frozen mention queue");assert build_mention_review_batch_packet(db,batch.id)["manifest_valid"] and len(assigned_mention_batch_items(db,batch.id,"maker","RESEARCHER"))==1
        item=db.scalar(select(RelationshipMentionReviewBatchItem));item.identity_fingerprint="0"*64;db.flush();assert not build_mention_review_batch_packet(db,batch.id)["manifest_valid"]
        db.rollback()
    with factory() as db:
        _mention(db);batch=freeze_mention_review_batch(db,"admin","venture_capital");assignment=assign_mention_reviewer(db,batch.id,"maker","RESEARCHER","admin","Maker assigned to frozen mention queue");close_mention_review_batch(db,batch.id,"admin","Queue superseded by a refreshed frozen cohort");assert batch.status=="CLOSED" and assignment.status=="REVOKED"

def test_expired_mention_assignment_fails_closed_and_is_marked_expired():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        mention=_mention(db);batch=freeze_mention_review_batch(db,"admin","venture_capital");assignment=assign_mention_reviewer(db,batch.id,"maker","RESEARCHER","admin","Maker assigned to frozen mention queue");assignment.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.flush()
        with pytest.raises(RelationshipMentionReviewError,match="unexpired"):validate_mention_review_decision(db,batch.id,mention,"maker","RESEARCHER",False)
        assert assignment.status=="EXPIRED"

def test_pending_mention_batch_preparation_emits_aggregate_only_counts():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        _mention(db);result=freeze_pending_mention_batches(db);assert result["batch_count"]==1 and result["item_count"]==1 and result["universe_count"]==1 and set(result)=={"classification","status","universe_count","batch_count","item_count","batches"}

def test_mention_freeze_prevents_same_state_overlap_and_allows_next_state_batch():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        mention=_mention(db);first=freeze_mention_review_batch(db,"admin","venture_capital");assert freeze_mention_review_batch(db,"admin","venture_capital").id==first.id;mention.status="TARGET_PROPOSED";db.flush();second=freeze_mention_review_batch(db,"admin","venture_capital","TARGET_PROPOSED");assert second.id!=first.id and second.item_count==1
