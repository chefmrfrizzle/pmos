import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.db import Base,SecurityReadinessRun

def test_security_readiness_requires_admin_and_all_universe_scope(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False);report={"classification":"PMOS PRIVATE AGGREGATE SECURITY READINESS — NO RECORD VALUES","status":"NOT_PRODUCTION_READY","controls":[],"summary":{}}
    with factory() as db:db.add(SecurityReadinessRun(status=report["status"],report_hash="a"*64,report_json=json.dumps(report),actor="worker"));db.commit()
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    scoped=Principal("admin",frozenset({"ADMIN"}),frozenset({"security:read"}),frozenset({"pensions"}),"oidc","correlation","tenant-a",frozenset({"security review"}),"security review");main.app.dependency_overrides[authenticate_private_request]=lambda:scoped
    try:
        with TestClient(main.app) as client:assert client.get("/security-readiness").status_code==403
        global_admin=Principal("admin",frozenset({"ADMIN"}),frozenset({"security:read"}),frozenset({"*"}),"oidc","correlation","tenant-a",frozenset({"security review"}),"security review");main.app.dependency_overrides[authenticate_private_request]=lambda:global_admin
        with TestClient(main.app) as client:
            response=client.get("/security-readiness");assert response.status_code==200 and response.json()["status"]=="NOT_PRODUCTION_READY"
    finally:main.app.dependency_overrides.clear()
