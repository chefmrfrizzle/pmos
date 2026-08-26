from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.db import Base,Entity,EvidencePassage,ResearchPassageCandidate,ResearchSourceCandidate,SourceDocument
from pmos_research.diligence import open_case

def test_passage_review_api_enforces_universe_scope_and_maker_checker(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Example Pension",canonical_name="example pension",universe="pension");db.add(entity);db.flush()
        open_case(db,entity.id,"pension","counterparty assessment","internal diligence","case-owner")
        source=ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example/governance",source_domain="official.example",document_type="GOVERNANCE",target_predicates_json='["governance"]',discovered_from_url="https://official.example",discovery_score=85,status="RETRIEVED_REVIEW_REQUIRED");db.add(source);db.flush()
        document=SourceDocument(entity_id=entity.id,publisher="official.example",publisher_independence_group="official.example",source_rank="S1",source_type="official_website",source_url=source.source_url,content_hash="a"*64);db.add(document);db.flush()
        passage=EvidencePassage(document_id=document.id,section="candidate",passage="Governance is exercised by the Board of Trustees.",passage_hash="b"*64);db.add(passage);db.flush()
        candidate=ResearchPassageCandidate(source_candidate_id=source.id,evidence_passage_id=passage.id,predicate="governance",confidence=.75);db.add(candidate);db.commit();candidate_id=candidate.id
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    maker=Principal("maker",frozenset({"RESEARCHER"}),frozenset({"evidence:review","evidence:write"}),frozenset({"pension"}),"oidc","maker-correlation","tenant-a",frozenset({"internal diligence"}),"internal diligence");main.app.dependency_overrides[authenticate_private_request]=lambda:maker
    try:
        with TestClient(main.app) as client:
            listing=client.get("/evidence-review/passages");assert listing.status_code==200 and len(listing.json())==1
            response=client.post(f"/evidence-review/passages/{candidate_id}/actions",json={"action":"PROPOSE_SUPPORT","rationale":"The passage directly identifies the governance body","claim_value":"Board of Trustees","expected_status":"HUMAN_REVIEW_REQUIRED"});assert response.status_code==200
        checker=Principal("checker",frozenset({"REVIEWER"}),frozenset({"evidence:approve"}),frozenset({"pension"}),"oidc","checker-correlation","tenant-a",frozenset({"internal diligence"}),"internal diligence");main.app.dependency_overrides[authenticate_private_request]=lambda:checker
        with TestClient(main.app) as client:
            response=client.post(f"/evidence-review/passages/{candidate_id}/actions",json={"action":"APPROVE_SUPPORT","rationale":"Independent review confirms the exact value and context","claim_value":"Board of Trustees","expected_status":"SUPPORT_PROPOSED"});assert response.status_code==200 and response.json()["claim_id"]
            route_id=response.json()["routing_candidate_ids"][0]
        router=Principal("router",frozenset({"RESEARCHER"}),frozenset({"evidence:routing:review","evidence:routing:write"}),frozenset({"pension"}),"oidc","router-correlation","tenant-a",frozenset({"internal diligence"}),"internal diligence");main.app.dependency_overrides[authenticate_private_request]=lambda:router
        with TestClient(main.app) as client:
            listing=client.get("/evidence-review/routing");assert listing.status_code==200 and listing.json()[0]["id"]==route_id
            response=client.post(f"/evidence-review/routing/{route_id}/actions",json={"action":"ATTACH","rationale":"Attach the supported governance claim to its matching case check","expected_status":"PENDING_REVIEW"});assert response.status_code==200 and response.json()["check_status"]=="EVIDENCE_COLLECTED"
    finally:main.app.dependency_overrides.clear()
