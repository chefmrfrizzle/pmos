from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Entity,IdentityReviewBatchItem,ImportBatch,RawImportRow,ResolutionDecision,ReviewQueueItem
from pmos_research.identity_review_batch import build_identity_batch_packet,freeze_identity_batch

def test_identity_batch_freezes_pair_version_without_private_names_and_detects_tampering():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        public=Entity(name="Public Counterparty",canonical_name="public counterparty",universe="venture_capital");private=Entity(name="Private Secret Name",canonical_name="private secret name",universe="imported_private");db.add_all([public,private]);db.flush();source=ImportBatch(source_file="private.csv",source_sha256="a"*64);db.add(source);db.flush();raw=RawImportRow(batch_id=source.id,source_file="private.csv",sheet_name="CSV",source_row_number=2,row_hash="b"*64,original_row_json='{"secret":"value"}',normalized_row_json='{"name":"Private Secret Name"}',disposition="review",entity_id=private.id);db.add(raw);db.flush();decision=ResolutionDecision(raw_row_id=raw.id,candidate_entity_id=public.id,state="PROBABLE_MATCH",confidence=.9,reasons_json='["similar"]');db.add(decision);db.flush();item=ReviewQueueItem(resolution_decision_id=decision.id,queue_type="ENTITY",priority=90,reasons_json='["review"]');db.add(item);db.flush();batch=freeze_identity_batch(db,"assigner","venture_capital",min_priority=80);db.commit();packet=build_identity_batch_packet(db,batch.id)
        assert packet["manifest_valid"] is True and packet["item_count"]==1 and "Private Secret Name" not in str(packet) and "Public Counterparty" not in str(packet)
        frozen=db.scalar(select(IdentityReviewBatchItem).where(IdentityReviewBatchItem.batch_id==batch.id));frozen.pair_fingerprint="0"*64;db.commit();assert build_identity_batch_packet(db,batch.id)["manifest_valid"] is False
