import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.db import Base,UniverseCoverageRun

def test_universe_coverage_api_requires_admin_and_all_universe_scope(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False);report={"classification":"PMOS PRIVATE AGGREGATE COVERAGE — NO ENTITY NAMES","status":"INCOMPLETE","totals":{"registered":1}}
    import hashlib
    canonical=json.dumps(report,sort_keys=True,separators=(",",":"));digest=hashlib.sha256(canonical.encode()).hexdigest()
    with factory() as db:db.add(UniverseCoverageRun(status="INCOMPLETE",report_hash=digest,report_json=canonical,actor="test"));db.commit()
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    limited=Principal("admin",frozenset({"ADMIN"}),frozenset({"coverage:read"}),frozenset({"venture_capital"}),"oidc","coverage-limited","tenant-a",frozenset({"control assurance"}),"control assurance");main.app.dependency_overrides[authenticate_private_request]=lambda:limited
    try:
        with TestClient(main.app) as client:assert client.get("/universe-coverage").status_code==403
        full=Principal("admin",frozenset({"ADMIN"}),frozenset({"coverage:read"}),frozenset({"*"}),"oidc","coverage-full","tenant-a",frozenset({"control assurance"}),"control assurance");main.app.dependency_overrides[authenticate_private_request]=lambda:full
        with TestClient(main.app) as client:response=client.get("/universe-coverage");assert response.status_code==200 and response.json()["status"]=="INCOMPLETE"
    finally:main.app.dependency_overrides.clear()
