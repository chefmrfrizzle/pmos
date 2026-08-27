from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.db import Base,CorroborationJob,Entity,PrivateEgressReviewCase

def test_private_egress_api_enforces_permissions_and_maker_checker(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False);monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    with factory() as db:entity=Entity(name="Private",canonical_name="private",universe="imported_private");db.add(entity);db.flush();job=CorroborationJob(entity_id=entity.id,source_url="https://example.test/about",source_domain="example.test",status="SUPPORTED",attempts=1,checkpoint_json="{}");db.add(job);db.flush();case=PrivateEgressReviewCase(corroboration_job_id=job.id,prior_status="SUPPORTED",attempts_observed=1,status="OPEN",reason="Legacy attempt requires review");db.add(case);db.commit();case_id=case.id
    maker=Principal("security-maker",frozenset({"ADMIN"}),frozenset({"security:review","security:write"}),frozenset({"*"}),"oidc","maker-correlation","tenant-a",frozenset({"security review"}),"security review");main.app.dependency_overrides[authenticate_private_request]=lambda:maker
    try:
        with TestClient(main.app) as client:
            listed=client.get("/security/private-egress-reviews");assert listed.status_code==200 and len(listed.json())==1 and "https://" not in str(listed.json())
            proposed=client.post(f"/security/private-egress-reviews/{case_id}/actions",json={"action":"PROPOSE_NO_MATERIAL_DISCLOSURE","rationale":"Request metadata contains no query or credential values","expected_status":"OPEN"});assert proposed.status_code==200
            denied=client.post(f"/security/private-egress-reviews/{case_id}/actions",json={"action":"APPROVE_NO_MATERIAL_DISCLOSURE","rationale":"Maker cannot approve their own assessment package","expected_status":"NO_MATERIAL_DISCLOSURE_PROPOSED"});assert denied.status_code==403
        checker=Principal("security-checker",frozenset({"COUNSEL"}),frozenset({"security:approve"}),frozenset({"*"}),"oidc","checker-correlation","tenant-a",frozenset({"security review"}),"security review");main.app.dependency_overrides[authenticate_private_request]=lambda:checker
        with TestClient(main.app) as client:approved=client.post(f"/security/private-egress-reviews/{case_id}/actions",json={"action":"APPROVE_NO_MATERIAL_DISCLOSURE","rationale":"Independent counsel reviewed the unchanged metadata package","expected_status":"NO_MATERIAL_DISCLOSURE_PROPOSED"});assert approved.status_code==200 and approved.json()["status"]=="RESOLVED_NO_MATERIAL_DISCLOSURE"
    finally:main.app.dependency_overrides.clear()
