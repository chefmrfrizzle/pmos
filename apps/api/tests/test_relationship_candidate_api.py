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
