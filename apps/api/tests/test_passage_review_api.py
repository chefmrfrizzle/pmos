import hashlib
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.db import Base,Entity,EvidencePassage,ResearchDocumentSnapshot,ResearchPassageCandidate,ResearchSourceCandidate,SourceDocument
from pmos_research.diligence import open_case
from pmos_research.evidence_review_batch import freeze_review_batch
from pmos_research.evidence_review_assignment import assign_reviewer

def test_passage_review_api_enforces_universe_scope_and_maker_checker(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Example Pension",canonical_name="example pension",universe="pension");db.add(entity);db.flush()
        open_case(db,entity.id,"pension","counterparty assessment","internal diligence","case-owner")
        source=ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example/governance",source_domain="official.example",document_type="GOVERNANCE",target_predicates_json='["governance"]',discovered_from_url="https://official.example",discovery_score=85,status="RETRIEVED_REVIEW_REQUIRED");db.add(source);db.flush()
        text="Governance is exercised by the Board of Trustees.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=entity.id,publisher="official.example",publisher_independence_group="official.example",source_rank="S1",source_type="official_website",source_url=source.source_url,content_hash=digest);db.add(document);db.flush()
        db.add(ResearchDocumentSnapshot(source_candidate_id=source.id,source_document_id=document.id,normalized_text=text,text_hash=digest));passage=EvidencePassage(document_id=document.id,section="candidate",passage=text,passage_hash=digest);db.add(passage);db.flush()
        candidate=ResearchPassageCandidate(source_candidate_id=source.id,evidence_passage_id=passage.id,predicate="governance",confidence=.75);db.add(candidate);db.flush();batch=freeze_review_batch(db,"assigner","pension");assign_reviewer(db,batch.id,"maker","RESEARCHER","assigner","Maker assigned for evidence proposal");assign_reviewer(db,batch.id,"checker","REVIEWER","assigner","Checker assigned for independent approval");db.commit();candidate_id=candidate.id;batch_id=batch.id
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    observer=Principal("observer",frozenset({"REVIEWER"}),frozenset({"evidence:review"}),frozenset({"pension"}),"oidc","observer-correlation","tenant-a",frozenset({"internal diligence"}),"internal diligence");main.app.dependency_overrides[authenticate_private_request]=lambda:observer
    with TestClient(main.app) as client:assert client.get("/evidence-review/passages",params={"review_batch_id":batch_id}).status_code==403
    maker=Principal("maker",frozenset({"RESEARCHER"}),frozenset({"evidence:review","evidence:write"}),frozenset({"pension"}),"oidc","maker-correlation","tenant-a",frozenset({"internal diligence"}),"internal diligence");main.app.dependency_overrides[authenticate_private_request]=lambda:maker
    try:
        with TestClient(main.app) as client:
            listing=client.get("/evidence-review/passages",params={"review_batch_id":batch_id});assert listing.status_code==200 and len(listing.json())==1
            assert listing.json()[0]["evidence_controls"]["support_eligible"] is True and listing.json()[0]["existing_assertions"]==[]
            assert len(client.get("/evidence-review/passages",params={"review_batch_id":batch_id,"predicate":"governance","min_confidence":.7,"evidence_state":"ELIGIBLE"}).json())==1
            assert client.get("/evidence-review/passages",params={"review_batch_id":batch_id,"evidence_state":"UNKNOWN"}).status_code==422
            response=client.post(f"/evidence-review/passages/{candidate_id}/actions",json={"action":"PROPOSE_SUPPORT","rationale":"The passage directly identifies the governance body","claim_value":"Board of Trustees","expected_status":"HUMAN_REVIEW_REQUIRED","review_batch_id":batch_id});assert response.status_code==200
        checker=Principal("checker",frozenset({"REVIEWER"}),frozenset({"evidence:approve"}),frozenset({"pension"}),"oidc","checker-correlation","tenant-a",frozenset({"internal diligence"}),"internal diligence");main.app.dependency_overrides[authenticate_private_request]=lambda:checker
        with TestClient(main.app) as client:
            response=client.post(f"/evidence-review/passages/{candidate_id}/actions",json={"action":"APPROVE_SUPPORT","rationale":"Independent review confirms the exact value and context","claim_value":"Board of Trustees","expected_status":"SUPPORT_PROPOSED","review_batch_id":batch_id});assert response.status_code==200 and response.json()["claim_id"]
            route_id=response.json()["routing_candidate_ids"][0]
        router=Principal("router",frozenset({"RESEARCHER"}),frozenset({"evidence:routing:review","evidence:routing:write"}),frozenset({"pension"}),"oidc","router-correlation","tenant-a",frozenset({"internal diligence"}),"internal diligence");main.app.dependency_overrides[authenticate_private_request]=lambda:router
        with TestClient(main.app) as client:
            listing=client.get("/evidence-review/routing");assert listing.status_code==200 and listing.json()[0]["id"]==route_id
            response=client.post(f"/evidence-review/routing/{route_id}/actions",json={"action":"ATTACH","rationale":"Attach the supported governance claim to its matching case check","expected_status":"PENDING_REVIEW"});assert response.status_code==200 and response.json()["check_status"]=="EVIDENCE_COLLECTED"
    finally:main.app.dependency_overrides.clear()
