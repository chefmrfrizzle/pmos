from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Entity,Evidence,ImportBatch,RawImportRow,ResolutionDecision,ReviewQueueItem
from pmos_research.identity_review import build_review_packet

def test_review_packet_omits_raw_rows_and_contact_secrets():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        source=Entity(name="Source Name",canonical_name="source name",universe="imported_private",country="US")
        candidate=Entity(name="Candidate Name",canonical_name="candidate name",universe="venture_capital",country="US",official_url="https://www.candidate.example/about")
        db.add_all([source,candidate]);db.flush();batch=ImportBatch(source_file="logical/source.csv",source_sha256="a"*64);db.add(batch);db.flush()
        raw=RawImportRow(batch_id=batch.id,source_file="logical/source.csv",sheet_name="CSV",source_row_number=2,row_hash="b"*64,original_row_json='{"secret":"must not appear"}',normalized_row_json='{"name":"Source Name"}',disposition="review",entity_id=source.id);db.add(raw);db.flush()
        decision=ResolutionDecision(raw_row_id=raw.id,candidate_entity_id=candidate.id,state="PROBABLE_MATCH",confidence=.9,reasons_json='["similar name"]');db.add(decision);db.flush()
        item=ReviewQueueItem(resolution_decision_id=decision.id,queue_type="ENTITY",priority=90,reasons_json='["review"]');db.add(item);db.flush()
        evidence=Evidence(entity_id=candidate.id,source_url="https://candidate.example/about",content_hash="c"*64,text_excerpt="official evidence");db.add(evidence);db.commit()
        packet=build_review_packet(db,item.id)
        assert packet["universe"]=="venture_capital" and packet["raw_row_exposed"] is False
        assert "secret" not in str(packet) and "text_excerpt" not in packet["evidence"][0]
        assert packet["candidate_identity"]["official_domain"]=="candidate.example"
        assert packet["adjudication_controls"]=={"distinct_pair":True,"active_cluster_count":0,"exact_pair_proposal_present":False,"can_propose":True,"can_approve":False,"blockers":[]}
