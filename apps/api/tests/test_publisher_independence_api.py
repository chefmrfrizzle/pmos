import hashlib
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.db import Base,Entity,EvidencePassage,SourceDocument

def test_publisher_independence_api_is_scoped_and_maker_checker(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Example",canonical_name="example",universe="private_equity");db.add(entity);db.flush();text="The disclosure identifies Example Media Holdings as the controlling publisher group.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=entity.id,publisher="news.example",publisher_independence_group="example-media",source_rank="S2",source_type="publisher_disclosure",source_url="https://news.example/ownership",content_hash=digest);db.add(document);db.flush();passage=EvidencePassage(document_id=document.id,passage=text,passage_hash=digest);db.add(passage);db.commit();passage_id=passage.id
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    maker=Principal("maker",frozenset({"RESEARCHER"}),frozenset({"evidence:write","evidence:review"}),frozenset({"private_equity"}),"oidc","publisher-maker","tenant-a",frozenset({"counterparty research"}),"counterparty research")
    main.app.dependency_overrides[authenticate_private_request]=lambda:maker
    try:
        with TestClient(main.app) as client:
            proposal=client.post("/publisher-independence",json={"source_domain":"news.example","independence_group":"example-media","rationale":"Publisher disclosure supports this control grouping","evidence_passage_ids":[passage_id]});assert proposal.status_code==200;assessment_id=proposal.json()["id"]
            assert len(client.get("/publisher-independence").json())==1
            assert client.post(f"/publisher-independence/{assessment_id}/actions",json={"action":"APPROVE","rationale":"Maker cannot approve their own assessment","expected_status":"HUMAN_REVIEW_REQUIRED"}).status_code==403
        checker=Principal("checker",frozenset({"REVIEWER"}),frozenset({"evidence:approve","evidence:review"}),frozenset({"private_equity"}),"oidc","publisher-checker","tenant-a",frozenset({"counterparty research"}),"counterparty research");main.app.dependency_overrides[authenticate_private_request]=lambda:checker
        with TestClient(main.app) as client:
            approved=client.post(f"/publisher-independence/{assessment_id}/actions",json={"action":"APPROVE","rationale":"Independent review confirms the publisher control group","expected_status":"HUMAN_REVIEW_REQUIRED"});assert approved.status_code==200 and approved.json()["status"]=="APPROVED"
    finally:main.app.dependency_overrides.clear()
