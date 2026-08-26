from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.change_detection import persist_reverification
from pmos_research.db import Base,Entity,ResearchSourceCandidate
from pmos_research.source_retrieval import persist_retrieved_candidate

def test_change_review_api_is_universe_scoped_and_audited(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Example Institution",canonical_name="example institution",universe="sovereign_wealth");db.add(entity);db.flush()
        candidate=ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example/governance",source_domain="official.example",document_type="GOVERNANCE",target_predicates_json='["governance"]',discovered_from_url="https://official.example",discovery_score=90);db.add(candidate);db.flush()
        first={"status":"ok","url":candidate.source_url,"title":"Governance","text":"Governance is exercised by the Board.","hash":"a"*64};persist_retrieved_candidate(db,candidate,first);db.commit()
        second={**first,"text":"Governance is exercised by the Board and Investment Committee.","hash":"b"*64};result=persist_reverification(db,candidate,second);db.commit();event_id=result["change_event_id"]
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    principal=Principal("reviewer",frozenset({"REVIEWER"}),frozenset({"evidence:review","evidence:write"}),frozenset({"sovereign_wealth"}),"oidc","change-correlation");main.app.dependency_overrides[authenticate_private_request]=lambda:principal
    try:
        with TestClient(main.app) as client:
            listing=client.get("/evidence-review/source-changes");assert listing.status_code==200 and listing.json()[0]["id"]==event_id
            response=client.post(f"/evidence-review/source-changes/{event_id}/actions",json={"action":"ESCALATE","rationale":"Governance body changed and requires specialist reassessment","expected_status":"HUMAN_REVIEW_REQUIRED"});assert response.status_code==200 and response.json()["resulting_state"]=="ESCALATED"
    finally:main.app.dependency_overrides.clear()
