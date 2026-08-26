from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.db import Base,Entity,Evidence,ImportBatch,RawImportRow,ResolutionDecision,ReviewQueueItem

def test_private_identity_review_is_scoped_evidence_bound_and_maker_checker(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        source=Entity(name="Source Capital",canonical_name="source capital",universe="imported_private")
        candidate=Entity(name="Source Capital LP",canonical_name="source capital",universe="venture_capital",official_url="https://source.example")
        unrelated=Entity(name="Unrelated",canonical_name="unrelated",universe="private_equity")
        db.add_all([source,candidate,unrelated]);db.flush();batch=ImportBatch(source_file="logical/source.csv",source_sha256="a"*64);db.add(batch);db.flush()
        raw=RawImportRow(batch_id=batch.id,source_file="logical/source.csv",sheet_name="CSV",source_row_number=2,row_hash="b"*64,original_row_json='{"private":"secret"}',normalized_row_json='{"name":"Source Capital"}',disposition="review",entity_id=source.id);db.add(raw);db.flush()
        decision=ResolutionDecision(raw_row_id=raw.id,candidate_entity_id=candidate.id,state="PROBABLE_MATCH",confidence=.9,reasons_json='["name and domain"]');db.add(decision);db.flush()
        item=ReviewQueueItem(resolution_decision_id=decision.id,queue_type="ENTITY",priority=90,reasons_json='["review"]');db.add(item);db.flush()
        evidence=Evidence(entity_id=candidate.id,source_url="https://source.example/about",source_type="official",content_hash="c"*64,text_excerpt="Source Capital LP official site");wrong=Evidence(entity_id=unrelated.id,source_url="https://unrelated.example",source_type="official",content_hash="d"*64)
        db.add_all([evidence,wrong]);db.commit();item_id=item.id;evidence_id=evidence.id;wrong_id=wrong.id
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    maker=Principal("maker",frozenset({"RESEARCHER"}),frozenset({"identity:review","identity:write"}),frozenset({"venture_capital"}),"oidc","maker-correlation","tenant-a",frozenset({"identity adjudication"}),"identity adjudication")
    main.app.dependency_overrides[authenticate_private_request]=lambda:maker
    try:
        with TestClient(main.app) as client:
            listing=client.get("/identity-review");assert listing.status_code==200 and len(listing.json())==1
            packet=listing.json()[0];assert packet["raw_row_exposed"] is False and "secret" not in str(packet)
            assert len(client.get("/identity-review",params={"resolution_state":"PROBABLE_MATCH","min_priority":90}).json())==1
            assert client.get("/identity-review",params={"resolution_state":"EXACT_MATCH"}).status_code==422
            assert client.get("/identity-review",params={"min_priority":101}).status_code==422
            body={"action":"PROPOSE_MATCH","rationale":"Official evidence supports the proposed identity match","evidence_ids":[wrong_id],"expected_version":packet["version"]}
            assert client.post(f"/identity-review/{item_id}/actions",json=body).status_code==422
            body["evidence_ids"]=[evidence_id];proposal=client.post(f"/identity-review/{item_id}/actions",json=body);assert proposal.status_code==200
        checker=Principal("checker",frozenset({"REVIEWER"}),frozenset({"identity:approve"}),frozenset({"venture_capital"}),"oidc","checker-correlation","tenant-a",frozenset({"identity adjudication"}),"identity adjudication")
        main.app.dependency_overrides[authenticate_private_request]=lambda:checker
        with TestClient(main.app) as client:
            response=client.post(f"/identity-review/{item_id}/actions",json={"action":"APPROVE_MATCH","rationale":"Independent review confirms the same evidence package","evidence_ids":[evidence_id],"expected_version":proposal.json()["version"]})
            assert response.status_code==200 and response.json()["resulting_state"]=="ACCEPTED"
    finally:main.app.dependency_overrides.clear()
