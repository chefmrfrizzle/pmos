import hashlib
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.db import Base,Entity,EvidencePassage,SourceDocument
from pmos_research.relationship_research import discover_relationship_candidates

def test_relationship_candidate_api_is_scoped_and_never_auto_verifies(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        source=Entity(name="Alpha Capital",canonical_name="alpha capital",universe="venture_capital");target=Entity(name="Beta Ventures",canonical_name="beta ventures",universe="venture_capital");db.add_all([source,target]);db.flush();text="Alpha Capital entered a strategic partnership with Beta Ventures.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=source.id,publisher="alpha.example",publisher_independence_group="alpha.example",source_rank="S1",source_type="official_website",source_url="https://alpha.example/news",content_hash=digest);db.add(document);db.flush();db.add(EvidencePassage(document_id=document.id,passage=text,passage_hash=digest));db.flush();discover_relationship_candidates(db);db.commit()
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None);principal=Principal("maker",frozenset({"RESEARCHER"}),frozenset({"relationships:review","relationships:write"}),frozenset({"venture_capital"}),"oidc","correlation","tenant-a",frozenset({"relationship review"}),"relationship review");main.app.dependency_overrides[authenticate_private_request]=lambda:principal
    try:
        with TestClient(main.app) as client:
            rows=client.get("/relationship-candidates");assert rows.status_code==200 and len(rows.json())==1;candidate=rows.json()[0];assert candidate["status"]=="HUMAN_REVIEW_REQUIRED"
            result=client.post(f"/relationship-candidates/{candidate['id']}/actions",json={"action":"PROPOSE_ASSERTION","rationale":"Exact passage supports specialist relationship review","expected_status":"HUMAN_REVIEW_REQUIRED"});assert result.status_code==200 and result.json()["status"]=="ASSERTION_PROPOSED" and result.json()["resulting_assertion_id"]
    finally:main.app.dependency_overrides.clear()

def test_relationship_mention_api_requires_registered_scoped_target(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        source=Entity(name="Alpha Capital",canonical_name="alpha capital",universe="venture_capital");db.add(source);db.flush();text="Alpha Capital partnered with Gamma Partners.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=source.id,publisher="alpha.example",publisher_independence_group="alpha.example",source_rank="S1",source_type="official_website",source_url="https://alpha.example/news",content_hash=digest);db.add(document);db.flush();db.add(EvidencePassage(document_id=document.id,passage=text,passage_hash=digest));db.flush();discover_relationship_candidates(db);target=Entity(name="Gamma Partners",canonical_name="gamma partners",universe="private_equity");db.add(target);db.commit();target_id=target.id
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None);admin=Principal("admin",frozenset({"ADMIN"}),frozenset({"identity:review","identity:assign","relationships:review"}),frozenset({"venture_capital","private_equity"}),"oidc","admin-correlation","tenant-a",frozenset({"relationship review"}),"relationship review");main.app.dependency_overrides[authenticate_private_request]=lambda:admin
    try:
        with TestClient(main.app) as client:
            batch=client.post("/relationship-mentions/batches",json={"universe":"venture_capital","status":"ENTITY_RESOLUTION_REQUIRED","limit":10}).json();maker_batch_id=batch["id"];assigned=client.post(f"/relationship-mentions/batches/{maker_batch_id}/assignments",json={"reviewer":"resolver","reviewer_role":"RESEARCHER","rationale":"Maker assigned to frozen mention batch","expires_hours":24});assert assigned.status_code==200
            assert client.get("/relationship-mentions",params={"review_batch_id":maker_batch_id}).status_code==403
        principal=Principal("resolver",frozenset({"RESEARCHER"}),frozenset({"relationships:review","identity:write"}),frozenset({"venture_capital","private_equity"}),"oidc","correlation","tenant-a",frozenset({"relationship review"}),"relationship review");main.app.dependency_overrides[authenticate_private_request]=lambda:principal
        with TestClient(main.app) as client:
            rows=client.get("/relationship-mentions",params={"review_batch_id":maker_batch_id});assert rows.status_code==200 and len(rows.json())==1;mention=rows.json()[0];assert mention["mention_text"]=="Gamma Partners"
            proposed=client.post(f"/relationship-mentions/{mention['id']}/actions",json={"action":"PROPOSE_TARGET","rationale":"Official identity review proposes the exact named mention","expected_status":"ENTITY_RESOLUTION_REQUIRED","target_entity_id":target_id,"review_batch_id":maker_batch_id});assert proposed.status_code==200 and proposed.json()["status"]=="TARGET_PROPOSED" and proposed.json()["resulting_candidate_id"] is None
        main.app.dependency_overrides[authenticate_private_request]=lambda:admin
        with TestClient(main.app) as client:
            checker_batch=client.post("/relationship-mentions/batches",json={"universe":"venture_capital","status":"TARGET_PROPOSED","limit":10}).json();checker_batch_id=checker_batch["id"];assigned=client.post(f"/relationship-mentions/batches/{checker_batch_id}/assignments",json={"reviewer":"identity-checker","reviewer_role":"REVIEWER","rationale":"Checker assigned to proposed-target batch","expires_hours":24});assert assigned.status_code==200
        checker=Principal("identity-checker",frozenset({"REVIEWER"}),frozenset({"identity:approve","relationships:review"}),frozenset({"venture_capital","private_equity"}),"oidc","correlation-2","tenant-a",frozenset({"relationship review"}),"relationship review");main.app.dependency_overrides[authenticate_private_request]=lambda:checker
        with TestClient(main.app) as client:
            linked=client.post(f"/relationship-mentions/{mention['id']}/actions",json={"action":"APPROVE_TARGET","rationale":"Independent identity review confirms the registered target","expected_status":"TARGET_PROPOSED","review_batch_id":checker_batch_id});assert linked.status_code==200 and linked.json()["status"]=="TARGET_LINKED" and linked.json()["resulting_candidate_id"]
    finally:main.app.dependency_overrides.clear()
