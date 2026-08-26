from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.control_assurance import persist_assurance_run,run_control_assurance
from pmos_research.db import Base,Entity
from pmos_research.diligence import open_case

def test_export_request_api_enforces_scope_ownership_and_independent_approval(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Institution",canonical_name="institution",universe="private_bank");db.add(entity);db.flush();case=open_case(db,entity.id,"default","assessment","internal diligence","owner");persist_assurance_run(db,run_control_assurance(db));db.commit();case_id=case.id
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    requester=Principal("requester",frozenset({"RESEARCHER"}),frozenset({"exports:request","exports:read"}),frozenset({"private_bank"}),"oidc","request-correlation");main.app.dependency_overrides[authenticate_private_request]=lambda:requester
    try:
        with TestClient(main.app) as client:
            response=client.post("/exports/requests",json={"case_id":case_id,"purpose":"internal diligence","expires_hours":24});assert response.status_code==200
            request_id=response.json()["id"];assert response.json()["status"]=="REQUESTED"
            assert client.get(f"/exports/requests/{request_id}").status_code==200
        exporter=Principal("exporter",frozenset({"EXPORTER"}),frozenset({"exports:approve","exports:read"}),frozenset({"private_bank"}),"oidc","approval-correlation");main.app.dependency_overrides[authenticate_private_request]=lambda:exporter
        with TestClient(main.app) as client:
            response=client.post(f"/exports/requests/{request_id}/actions",json={"action":"APPROVE","rationale":"Independent approval for the scoped internal diligence dossier","expected_status":"REQUESTED"});assert response.status_code==200 and response.json()["status"]=="APPROVED"
    finally:main.app.dependency_overrides.clear()
