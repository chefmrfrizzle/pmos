import hashlib
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.db import Base,Entity,EvidencePassage,ResearchDocumentSnapshot,ResearchPassageCandidate,ResearchSourceCandidate,SourceDocument

def test_evidence_batch_api_is_universe_scoped_and_hash_verified(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Example",canonical_name="example",universe="pensions");db.add(entity);db.flush();source=ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example/about",source_domain="official.example",document_type="LEGAL_IDENTITY",target_predicates_json='["legal_identity"]',discovered_from_url="https://official.example",status="RETRIEVED_REVIEW_REQUIRED");db.add(source);db.flush();text="The legal name is Example Pension Fund.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=entity.id,publisher="official.example",publisher_independence_group="official.example",source_rank="S1",source_type="official_website",source_url=source.source_url,content_hash=digest);db.add(document);db.flush();db.add(ResearchDocumentSnapshot(source_candidate_id=source.id,source_document_id=document.id,normalized_text=text,text_hash=digest));passage=EvidencePassage(document_id=document.id,passage=text,passage_hash=digest);db.add(passage);db.flush();db.add(ResearchPassageCandidate(source_candidate_id=source.id,evidence_passage_id=passage.id,predicate="legal_identity",confidence=.9));db.commit()
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None);principal=Principal("reviewer",frozenset({"REVIEWER"}),frozenset({"evidence:review"}),frozenset({"pensions"}),"oidc","correlation","tenant-a",frozenset({"internal diligence"}),"internal diligence");main.app.dependency_overrides[authenticate_private_request]=lambda:principal
    try:
        with TestClient(main.app) as client:
            denied=client.post("/evidence-review/batches",json={"universe":"private_equity"});assert denied.status_code==403
            created=client.post("/evidence-review/batches",json={"universe":"pensions","predicate":"legal_identity","min_confidence":.8});assert created.status_code==200 and created.json()["manifest_valid"] is True and created.json()["item_count"]==1
            detail=client.get(f"/evidence-review/batches/{created.json()['id']}");assert detail.status_code==200 and detail.json()["manifest_hash"]==created.json()["manifest_hash"]
    finally:main.app.dependency_overrides.clear()

def test_review_authority_can_be_assigned_revoked_and_closed(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Example",canonical_name="example",universe="pensions");db.add(entity);db.flush();source=ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example/about",source_domain="official.example",document_type="LEGAL_IDENTITY",target_predicates_json='["legal_identity"]',discovered_from_url="https://official.example",status="RETRIEVED_REVIEW_REQUIRED");db.add(source);db.flush();text="The legal name is Example Pension Fund.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=entity.id,publisher="official.example",publisher_independence_group="official.example",source_rank="S1",source_type="official_website",source_url=source.source_url,content_hash=digest);db.add(document);db.flush();db.add(ResearchDocumentSnapshot(source_candidate_id=source.id,source_document_id=document.id,normalized_text=text,text_hash=digest));passage=EvidencePassage(document_id=document.id,passage=text,passage_hash=digest);db.add(passage);db.flush();db.add(ResearchPassageCandidate(source_candidate_id=source.id,evidence_passage_id=passage.id,predicate="legal_identity",confidence=.9));db.commit()
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None);admin=Principal("admin",frozenset({"ADMIN"}),frozenset({"evidence:review","evidence:assign"}),frozenset({"pensions"}),"oidc","correlation","tenant-a",frozenset({"internal diligence"}),"internal diligence");main.app.dependency_overrides[authenticate_private_request]=lambda:admin
    try:
        with TestClient(main.app) as client:
            batch=client.post("/evidence-review/batches",json={"universe":"pensions"}).json();assigned=client.post(f"/evidence-review/batches/{batch['id']}/assignments",json={"reviewer":"maker","reviewer_role":"RESEARCHER","rationale":"Assign maker for bounded evidence review","expires_hours":4});assert assigned.status_code==200 and assigned.json()["status"]=="ACTIVE"
            revoked=client.post(f"/evidence-review/assignments/{assigned.json()['id']}/revoke",json={"rationale":"Reviewer access withdrawn before decision"});assert revoked.status_code==200 and revoked.json()["status"]=="REVOKED"
            closed=client.post(f"/evidence-review/batches/{batch['id']}/close",json={"rationale":"Review session concluded and batch retired"});assert closed.status_code==200 and closed.json()["status"]=="CLOSED"
            assert client.post(f"/evidence-review/batches/{batch['id']}/assignments",json={"reviewer":"other","reviewer_role":"REVIEWER","rationale":"This assignment must be rejected"}).status_code==422
    finally:main.app.dependency_overrides.clear()
