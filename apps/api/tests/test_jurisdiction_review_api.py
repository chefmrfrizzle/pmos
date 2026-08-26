from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.db import Base,Claim,Entity,JurisdictionReviewCase

def test_jurisdiction_correction_is_evidence_bound_scoped_and_maker_checker(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Example Fund",canonical_name="example fund",universe="pensions",country="0")
        db.add(entity);db.flush();claim=Claim(entity_id=entity.id,field="country",value="CA",source_url="https://example.test/about",source_type="official",confidence=.95,verification_status="SUPPORTED",evidence_hash="a"*64)
        db.add(claim);db.flush();case=JurisdictionReviewCase(entity_id=entity.id,original_country="0");db.add(case);db.commit();case_id=case.id;claim_id=claim.id
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    maker=Principal("maker",frozenset({"RESEARCHER"}),frozenset({"identity:review","identity:write"}),frozenset({"pensions"}),"oidc","maker-correlation","tenant-a",frozenset({"identity adjudication"}),"identity adjudication")
    main.app.dependency_overrides[authenticate_private_request]=lambda:maker
    try:
        with TestClient(main.app) as client:
            listed=client.get("/jurisdiction-review");assert listed.status_code==200 and listed.json()[0]["original_country"]=="0"
            proposal=client.post(f"/jurisdiction-review/{case_id}/actions",json={"action":"PROPOSE_CORRECTION","rationale":"Official evidence supports this jurisdiction correction","source_claim_id":claim_id,"expected_status":"HUMAN_REVIEW_REQUIRED"});assert proposal.status_code==200 and proposal.json()["status"]=="PROPOSED"
            assert client.post(f"/jurisdiction-review/{case_id}/actions",json={"action":"APPROVE_CORRECTION","rationale":"Maker must not approve the same jurisdiction correction","expected_status":"PROPOSED"}).status_code==403
        checker=Principal("checker",frozenset({"REVIEWER"}),frozenset({"identity:approve"}),frozenset({"pensions"}),"oidc","checker-correlation","tenant-a",frozenset({"identity adjudication"}),"identity adjudication")
        main.app.dependency_overrides[authenticate_private_request]=lambda:checker
        with TestClient(main.app) as client:
            approved=client.post(f"/jurisdiction-review/{case_id}/actions",json={"action":"APPROVE_CORRECTION","rationale":"Independent review confirms the official country evidence","expected_status":"PROPOSED"});assert approved.status_code==200 and approved.json()["status"]=="APPROVED"
        with factory() as db:assert db.get(Entity,entity.id).country=="CA"
    finally:main.app.dependency_overrides.clear()
