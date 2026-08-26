import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.app.security import Principal,authenticate_private_request,authorize,rate_limiter
from pmos_research.db import Base,Claim,ClaimEvidence,Entity,EvidencePassage,SourceDocument
from pmos_research.diligence import open_case

def request(host="127.0.0.1"):
    value=Request({"type":"http","method":"GET","path":"/","headers":[],"client":(host,1234),"server":("test",80),"scheme":"http","query_string":b""})
    value.state.correlation_id="test-correlation";return value

def test_private_api_is_absent_by_default(monkeypatch):
    monkeypatch.delenv("PMOS_AUTH_MODE",raising=False)
    with pytest.raises(HTTPException) as error:authenticate_private_request(request(),None,None)
    assert error.value.status_code==404

def test_local_auth_is_loopback_only_and_requires_strong_token(monkeypatch):
    rate_limiter.reset()
    monkeypatch.setenv("PMOS_AUTH_MODE","local");monkeypatch.setenv("PMOS_DEV_API_TOKEN","a-secure-local-token-value")
    with pytest.raises(HTTPException) as error:authenticate_private_request(request("203.0.113.8"),None,"a-secure-local-token-value")
    assert error.value.status_code==403
    with pytest.raises(HTTPException) as error:authenticate_private_request(request(),None,"wrong")
    assert error.value.status_code==401
    principal=authenticate_private_request(request(),None,"a-secure-local-token-value")
    assert principal.roles==frozenset({"ADMIN"}) and principal.permissions==frozenset({"*"})

def test_authenticated_requests_are_rate_limited(monkeypatch):
    rate_limiter.reset();monkeypatch.setenv("PMOS_AUTH_MODE","local");monkeypatch.setenv("PMOS_DEV_API_TOKEN","a-secure-local-token-value");monkeypatch.setenv("PMOS_RATE_LIMIT_PER_MINUTE","10")
    for _ in range(10):authenticate_private_request(request(),None,"a-secure-local-token-value")
    with pytest.raises(HTTPException) as error:authenticate_private_request(request(),None,"a-secure-local-token-value")
    assert error.value.status_code==429 and error.value.headers["Retry-After"]=="60"
    rate_limiter.reset()

def test_api_rejects_untrusted_hosts_large_bodies_and_sets_security_headers(monkeypatch):
    import apps.api.app.main as main
    monkeypatch.setattr(main,"init_db",lambda:None)
    with TestClient(main.app) as client:
        response=client.get("/health");assert response.status_code==200
        assert response.headers["x-content-type-options"]=="nosniff" and response.headers["cache-control"]=="no-store"
        safe=client.get("/health",headers={"x-request-id":"case-review_123"});assert safe.headers["x-request-id"]=="case-review_123"
        unsafe=client.get("/health",headers={"x-request-id":"bad ledger value"});assert unsafe.headers["x-request-id"]!="bad ledger value" and len(unsafe.headers["x-request-id"])==36
        assert client.get("/health",headers={"host":"attacker.example"}).status_code==400
        assert client.post("/missing",content=b"x"*1_048_577).status_code==413

def _oidc_token(monkeypatch,overrides=None):
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048);public=private.public_key()
    class Key: key=public
    class Client:
        def __init__(self,*args,**kwargs):pass
        def get_signing_key_from_jwt(self,token):return Key()
    monkeypatch.setattr(jwt,"PyJWKClient",Client)
    monkeypatch.setenv("PMOS_AUTH_MODE","oidc");monkeypatch.setenv("PMOS_OIDC_ISSUER","https://identity.example/")
    monkeypatch.setenv("PMOS_OIDC_JWKS_URL","https://identity.example/.well-known/jwks.json");monkeypatch.setenv("PMOS_OIDC_AUDIENCE","pmos-private-api")
    monkeypatch.setenv("PMOS_TENANT_ID","tenant-a")
    now=int(time.time());claims={"iss":"https://identity.example/","sub":"user-1","aud":"pmos-private-api","iat":now,"exp":now+300,"auth_time":now,"jti":"test-token-instance-0001","amr":["webauthn"],"scope":"entities:read claims:read","https://pmos.example/roles":["researcher"],"https://pmos.example/universes":["venture_capital"],"https://pmos.example/tenant":"tenant-a","https://pmos.example/purposes":["counterparty research"]}
    claims.update(overrides or {})
    return jwt.encode(claims,private,algorithm="RS256",headers={"kid":"test"})

def test_oidc_validates_signature_issuer_audience_mfa_roles_and_scope(monkeypatch):
    token=_oidc_token(monkeypatch)
    principal=authenticate_private_request(request(),"Bearer "+token,None,"counterparty research")
    assert principal.subject=="user-1" and principal.roles==frozenset({"RESEARCHER"}) and principal.tenant_id=="tenant-a" and principal.active_purpose=="counterparty research"
    authorize(principal,"entities:read",{"RESEARCHER"},"venture_capital")
    with pytest.raises(HTTPException):authorize(principal,"entities:read",{"RESEARCHER"},"private_equity")
    with pytest.raises(HTTPException):authorize(principal,"entities:write",{"RESEARCHER"},"venture_capital")
    with pytest.raises(HTTPException):authorize(principal,"entities:read",{"RESEARCHER"},"venture_capital","different purpose")

def test_oidc_rejects_cross_tenant_missing_or_unauthorized_purpose(monkeypatch):
    rate_limiter.reset();token=_oidc_token(monkeypatch)
    with pytest.raises(HTTPException) as error:authenticate_private_request(request(),"Bearer "+token,None,None)
    assert error.value.status_code==403
    with pytest.raises(HTTPException) as error:authenticate_private_request(request(),"Bearer "+token,None,"external marketing")
    assert error.value.status_code==403
    token=_oidc_token(monkeypatch,{"https://pmos.example/tenant":"tenant-b"})
    with pytest.raises(HTTPException) as error:authenticate_private_request(request(),"Bearer "+token,None,"counterparty research")
    assert error.value.status_code==403

def test_oidc_rejects_tokens_without_mfa_or_authorized_role(monkeypatch):
    token=_oidc_token(monkeypatch,{"amr":["pwd"]})
    with pytest.raises(HTTPException) as error:authenticate_private_request(request(),"Bearer "+token,None,"counterparty research")
    assert error.value.status_code==403

def test_oidc_rejects_long_lived_stale_and_revoked_token_instances(monkeypatch):
    import hashlib
    now=int(time.time())
    with pytest.raises(HTTPException):authenticate_private_request(request(),"Bearer "+_oidc_token(monkeypatch,{"exp":now+7200}),None,"counterparty research")
    with pytest.raises(HTTPException):authenticate_private_request(request(),"Bearer "+_oidc_token(monkeypatch,{"iat":now-1000,"exp":now+100}),None,"counterparty research")
    with pytest.raises(HTTPException):authenticate_private_request(request(),"Bearer "+_oidc_token(monkeypatch,{"auth_time":now-90000}),None,"counterparty research")
    monkeypatch.setenv("PMOS_REVOKED_JTI_HASHES",hashlib.sha256(b"test-token-instance-0001").hexdigest())
    with pytest.raises(HTTPException):authenticate_private_request(request(),"Bearer "+_oidc_token(monkeypatch),None,"counterparty research")

def test_api_enforces_object_scope_and_permissions(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        vc=Entity(name="VC Example",canonical_name="vc example",universe="venture_capital")
        pe=Entity(name="PE Example",canonical_name="pe example",universe="private_equity")
        db.add_all([vc,pe]);db.commit();vc_id=vc.id;pe_id=pe.id
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    principal=Principal("user-1",frozenset({"RESEARCHER"}),frozenset({"entities:read"}),frozenset({"venture_capital"}),"oidc","test-correlation","tenant-a",frozenset({"counterparty research"}),"counterparty research")
    main.app.dependency_overrides[authenticate_private_request]=lambda:principal
    try:
        with TestClient(main.app) as client:
            response=client.get("/entities");assert response.status_code==200 and [x["id"] for x in response.json()]==[vc_id]
            assert client.get(f"/entities/{vc_id}").status_code==200
            assert client.get(f"/entities/{pe_id}").status_code==403
            assert client.get(f"/entities/{vc_id}/claims").status_code==403
    finally:main.app.dependency_overrides.clear()
    token=_oidc_token(monkeypatch,{"https://pmos.example/roles":["unknown" ]})
    with pytest.raises(HTTPException) as error:authenticate_private_request(request(),"Bearer "+token,None,"counterparty research")
    assert error.value.status_code==403

def test_authenticated_case_check_workflow_enforces_maker_checker(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Registry Example",canonical_name="registry example",universe="venture_capital");db.add(entity);db.flush();case=open_case(db,entity.id,"default","assessment","internal","owner")
        check=next(x for x in db.query(main.CheckResult).filter_by(case_id=case.id).all() if x.check_code=="legal_identity")
        document=SourceDocument(entity_id=entity.id,publisher="registry",publisher_independence_group="registry",source_rank="S0",source_type="registry",source_url="https://registry.example/record",content_hash="1"*64);db.add(document);db.flush()
        passage=EvidencePassage(document_id=document.id,section="record",passage="legal identity",passage_hash="2"*64);db.add(passage);db.flush()
        claim=Claim(entity_id=entity.id,field="legal_name",value=entity.name,source_url=document.source_url,source_type="registry",confidence=1,verification_status="SUPPORTED",extractor="test",evidence_hash=document.content_hash);db.add(claim);db.flush();db.add(ClaimEvidence(claim_id=claim.id,passage_id=passage.id,directness=1,supports=True));db.commit();case_id=case.id;check_id=check.id;claim_id=claim.id
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    maker=Principal("maker",frozenset({"RESEARCHER"}),frozenset({"checks:read","checks:write","dossiers:read"}),frozenset({"venture_capital"}),"oidc","maker-request","tenant-a",frozenset({"internal"}),"internal")
    wrong_purpose=Principal("maker",frozenset({"RESEARCHER"}),frozenset({"checks:read","dossiers:read"}),frozenset({"venture_capital"}),"oidc","wrong-purpose","tenant-a",frozenset({"external marketing"}),"external marketing")
    main.app.dependency_overrides[authenticate_private_request]=lambda:wrong_purpose
    with TestClient(main.app) as client:assert client.get(f"/diligence-cases/{case_id}/dossier").status_code==403
    main.app.dependency_overrides[authenticate_private_request]=lambda:maker
    try:
        with TestClient(main.app) as client:
            assert client.get(f"/diligence-cases/{case_id}").status_code==200
            dossier=client.get(f"/diligence-cases/{case_id}/dossier");assert dossier.status_code==200
            assert dossier.json()["classification"]=="PRIVATE—AUTHORIZED USE ONLY" and dossier.json()["evidence_coverage"]["exact_passage_linked"]==1
            response=client.post(f"/diligence-cases/{case_id}/checks/{check_id}/evidence",json={"claim_ids":[claim_id],"rationale":"Attach dispositive registry evidence"});assert response.status_code==200
            response=client.post(f"/diligence-cases/{case_id}/checks/{check_id}/actions",json={"action":"PROPOSE_COMPLETE","rationale":"Registry evidence directly establishes identity","expected_status":"EVIDENCE_COLLECTED"});assert response.status_code==200
            assert client.post(f"/diligence-cases/{case_id}/checks/{check_id}/actions",json={"action":"APPROVE","rationale":"Attempt unauthorized approval","expected_status":"REVIEW_PROPOSED"}).status_code==403
        checker=Principal("checker",frozenset({"REVIEWER"}),frozenset({"checks:read","checks:approve"}),frozenset({"venture_capital"}),"oidc","checker-request","tenant-a",frozenset({"internal"}),"internal")
        main.app.dependency_overrides[authenticate_private_request]=lambda:checker
        with TestClient(main.app) as client:
            response=client.post(f"/diligence-cases/{case_id}/checks/{check_id}/actions",json={"action":"APPROVE","rationale":"Independent reviewer confirms source and scope","expected_status":"REVIEW_PROPOSED"});assert response.status_code==200 and response.json()["status"]=="SPECIALIST_VERIFIED"
    finally:main.app.dependency_overrides.clear()
