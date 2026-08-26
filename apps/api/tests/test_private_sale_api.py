import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request
from pmos_research.db import Base,Claim,ClaimEvidence,Entity,EvidencePassage,SourceDocument

def test_private_sale_api_binds_purpose_scope_evidence_and_maker_checker(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        asset=Entity(name="Artwork A",canonical_name="artwork a",universe="asset",entity_type="ASSET");seller=Entity(name="Seller",canonical_name="seller",universe="private_client");db.add_all([asset,seller]);db.flush();text="The instrument confirms Seller has authority to sell.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=seller.id,publisher="registry.example",publisher_independence_group="registry.example",source_rank="S0",source_type="registry",source_url="https://registry.example/authority",content_hash=digest);db.add(document);db.flush();passage=EvidencePassage(document_id=document.id,section="authority",passage=text,passage_hash=digest);db.add(passage);db.flush();claim=Claim(entity_id=seller.id,field="authority_to_transact",value="Seller has authority to sell",source_url=document.source_url,source_type=document.source_type,confidence=1,verification_status="SUPPORTED",extractor="test",evidence_hash=digest);db.add(claim);db.flush();db.add(ClaimEvidence(claim_id=claim.id,passage_id=passage.id,directness=1,supports=True));db.commit();asset_id=asset.id;seller_id=seller.id;claim_id=claim.id
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None);universes=frozenset({"asset","private_client"})
    maker=Principal("maker",frozenset({"RESEARCHER"}),frozenset({"private_sales:write","private_sales:read"}),universes,"oidc","sale-maker","tenant-a",frozenset({"transaction diligence"}),"transaction diligence");main.app.dependency_overrides[authenticate_private_request]=lambda:maker
    try:
        with TestClient(main.app) as client:
            opened=client.post("/private-sales",json={"asset_entity_id":asset_id,"seller_entity_id":seller_id,"purpose":"private sale assessment","permitted_use":"transaction diligence","jurisdiction":"GB"});assert opened.status_code==200;packet=opened.json();case_id=packet["id"];gate=next(x for x in packet["gates"] if x["code"]=="authority_to_sell")
            attached=client.post(f"/private-sales/{case_id}/gates/{gate['id']}/evidence",json={"claim_ids":[claim_id]});assert attached.status_code==200
            proposed=client.post(f"/private-sales/{case_id}/gates/{gate['id']}/actions",json={"action":"PROPOSE_PASS","rationale":"Dispositive authority evidence is attached","expected_status":"EVIDENCE_COLLECTED"});assert proposed.status_code==200
        checker=Principal("checker",frozenset({"REVIEWER"}),frozenset({"private_sales:approve","private_sales:read"}),universes,"oidc","sale-checker","tenant-a",frozenset({"transaction diligence"}),"transaction diligence");main.app.dependency_overrides[authenticate_private_request]=lambda:checker
        with TestClient(main.app) as client:
            approved=client.post(f"/private-sales/{case_id}/gates/{gate['id']}/actions",json={"action":"APPROVE","rationale":"Independent review confirms seller authority","expected_status":"REVIEW_PROPOSED"});assert approved.status_code==200 and next(x for x in approved.json()["gates"] if x["id"]==gate["id"])["status"]=="PASS"
        wrong=Principal("checker",frozenset({"REVIEWER"}),frozenset({"private_sales:read"}),universes,"oidc","sale-wrong","tenant-a",frozenset({"marketing"}),"marketing");main.app.dependency_overrides[authenticate_private_request]=lambda:wrong
        with TestClient(main.app) as client:assert client.get(f"/private-sales/{case_id}").status_code==403
    finally:main.app.dependency_overrides.clear()
