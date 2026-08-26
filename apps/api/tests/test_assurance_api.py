from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.control_assurance import persist_assurance_run,run_control_assurance
from pmos_research.db import Base

def test_latest_assurance_is_private_role_controlled_and_aggregate_only(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:run=persist_assurance_run(db,run_control_assurance(db));db.commit();run_id=run.id
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    reviewer=Principal("reviewer",frozenset({"REVIEWER"}),frozenset({"assurance:read"}),frozenset({"*"}),"oidc","assurance-correlation");main.app.dependency_overrides[authenticate_private_request]=lambda:reviewer
    try:
        with TestClient(main.app) as client:
            response=client.get("/assurance/latest");assert response.status_code==200
            assert response.json()["run_id"]==run_id and response.json()["status"]=="PASS" and response.json()["exception_count"]==0
    finally:main.app.dependency_overrides.clear()
