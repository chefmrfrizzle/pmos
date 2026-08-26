import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.db import Base,Entity,EvidencePassage,SourceDocument

def test_relationship_review_requires_exact_scoped_evidence_and_independent_approval(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        source=Entity(name="Allocator",canonical_name="allocator",universe="sovereign_wealth");target=Entity(name="Manager",canonical_name="manager",universe="private_equity");unrelated=Entity(name="Other",canonical_name="other",universe="venture_capital");db.add_all([source,target,unrelated]);db.flush()
        text="The statutory filing states that Allocator owns Manager.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=source.id,publisher="registry.example",publisher_independence_group="registry.example",source_rank="S0",source_type="registry",source_url="https://registry.example/filing",content_hash=digest);wrong_document=SourceDocument(entity_id=unrelated.id,publisher="other.example",publisher_independence_group="other.example",source_rank="S0",source_type="registry",source_url="https://other.example/filing",content_hash="f"*64);db.add_all([document,wrong_document]);db.flush()
        passage=EvidencePassage(document_id=document.id,section="ownership",passage=text,passage_hash=digest);wrong=EvidencePassage(document_id=wrong_document.id,section="other",passage="Unrelated evidence.",passage_hash=hashlib.sha256(b"Unrelated evidence.").hexdigest());db.add_all([passage,wrong]);db.commit();source_id=source.id;target_id=target.id;passage_id=passage.id;wrong_id=wrong.id
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    universes=frozenset({"sovereign_wealth","private_equity"});maker=Principal("maker",frozenset({"RESEARCHER"}),frozenset({"relationships:write","relationships:review"}),universes,"oidc","relationship-maker","tenant-a",frozenset({"counterparty research"}),"counterparty research")
    main.app.dependency_overrides[authenticate_private_request]=lambda:maker
    try:
        with TestClient(main.app) as client:
            body={"from_entity_id":source_id,"to_entity_id":target_id,"relation_type":"OWNS","evidence_passage_ids":[wrong_id],"jurisdiction":"GB"};assert client.post("/relationship-review",json=body).status_code==422
            body["evidence_passage_ids"]=[passage_id];proposal=client.post("/relationship-review",json=body);assert proposal.status_code==200;packet=proposal.json();assert packet["evidence_controls"]["verification_eligible"] is True and packet["evidence_controls"]["evidence_confidence"]==1
            assertion_id=packet["id"];assert len(client.get("/relationship-review",params={"relation_type":"OWNS","sensitive":True,"min_confidence":.9}).json())==1
            assert client.post(f"/relationship-review/{assertion_id}/actions",json={"action":"APPROVE","rationale":"Maker cannot approve their own relationship assertion","expected_status":"HUMAN_REVIEW_REQUIRED"}).status_code==403
        checker=Principal("checker",frozenset({"REVIEWER"}),frozenset({"relationships:approve","relationships:review"}),universes,"oidc","relationship-checker","tenant-a",frozenset({"counterparty research"}),"counterparty research");main.app.dependency_overrides[authenticate_private_request]=lambda:checker
        with TestClient(main.app) as client:
            approved=client.post(f"/relationship-review/{assertion_id}/actions",json={"action":"APPROVE","rationale":"Independent review confirms the dispositive filing and exact passage","expected_status":"HUMAN_REVIEW_REQUIRED"});assert approved.status_code==200 and approved.json()["status"]=="SPECIALIST_VERIFIED"
    finally:main.app.dependency_overrides.clear()
