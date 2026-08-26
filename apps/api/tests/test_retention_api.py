from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.db import Base

def test_legal_hold_api_requires_real_maker_checker_and_independent_release(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False);monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    maker=Principal("hold-maker",frozenset({"COUNSEL"}),frozenset({"retention:write","retention:review","retention:approve"}),frozenset({"*"}),"oidc","hold-maker-correlation","tenant-a",frozenset({"legal hold administration"}),"legal hold administration");main.app.dependency_overrides[authenticate_private_request]=lambda:maker
    try:
        with TestClient(main.app) as client:
            proposal=client.post("/retention/legal-holds",json={"data_class":"RAW_IMPORT","reason":"Preserve source rows for pending legal review"});assert proposal.status_code==200 and proposal.json()["status"]=="PROPOSED";hold_id=proposal.json()["id"]
            assert len(client.get("/retention/legal-holds").json())==1
            same=client.post(f"/retention/legal-holds/{hold_id}/actions",json={"action":"APPROVE","rationale":"Maker cannot approve the same hold","expected_status":"PROPOSED"});assert same.status_code==422
        approver=Principal("hold-approver",frozenset({"COUNSEL"}),frozenset({"retention:approve","retention:review"}),frozenset({"*"}),"oidc","hold-approver-correlation","tenant-a",frozenset({"legal hold administration"}),"legal hold administration");main.app.dependency_overrides[authenticate_private_request]=lambda:approver
        with TestClient(main.app) as client:
            active=client.post(f"/retention/legal-holds/{hold_id}/actions",json={"action":"APPROVE","rationale":"Independent counsel approves the preservation hold","expected_status":"PROPOSED"});assert active.status_code==200 and active.json()["status"]=="ACTIVE"
            same=client.post(f"/retention/legal-holds/{hold_id}/actions",json={"action":"RELEASE","rationale":"Approver cannot release their own hold","expected_status":"ACTIVE"});assert same.status_code==422
        releaser=Principal("hold-releaser",frozenset({"COUNSEL"}),frozenset({"retention:approve"}),frozenset({"*"}),"oidc","hold-releaser-correlation","tenant-a",frozenset({"legal hold administration"}),"legal hold administration");main.app.dependency_overrides[authenticate_private_request]=lambda:releaser
        with TestClient(main.app) as client:
            released=client.post(f"/retention/legal-holds/{hold_id}/actions",json={"action":"RELEASE","rationale":"Independent counsel confirms the matter is closed","expected_status":"ACTIVE"});assert released.status_code==200 and released.json()["status"]=="RELEASED"
    finally:main.app.dependency_overrides.clear()
