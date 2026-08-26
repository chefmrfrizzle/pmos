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

from apps.api.app.security import Principal,authenticate_private_request,authorize
from pmos_research.db import Base,Entity

def request(host="127.0.0.1"):
    value=Request({"type":"http","method":"GET","path":"/","headers":[],"client":(host,1234),"server":("test",80),"scheme":"http","query_string":b""})
    value.state.correlation_id="test-correlation";return value

def test_private_api_is_absent_by_default(monkeypatch):
    monkeypatch.delenv("PMOS_AUTH_MODE",raising=False)
    with pytest.raises(HTTPException) as error:authenticate_private_request(request(),None,None)
    assert error.value.status_code==404

def test_local_auth_is_loopback_only_and_requires_strong_token(monkeypatch):
    monkeypatch.setenv("PMOS_AUTH_MODE","local");monkeypatch.setenv("PMOS_DEV_API_TOKEN","a-secure-local-token-value")
    with pytest.raises(HTTPException) as error:authenticate_private_request(request("203.0.113.8"),None,"a-secure-local-token-value")
    assert error.value.status_code==403
    with pytest.raises(HTTPException) as error:authenticate_private_request(request(),None,"wrong")
    assert error.value.status_code==401
    principal=authenticate_private_request(request(),None,"a-secure-local-token-value")
    assert principal.roles==frozenset({"ADMIN"}) and principal.permissions==frozenset({"*"})

def _oidc_token(monkeypatch,overrides=None):
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048);public=private.public_key()
    class Key: key=public
    class Client:
        def __init__(self,*args,**kwargs):pass
        def get_signing_key_from_jwt(self,token):return Key()
    monkeypatch.setattr(jwt,"PyJWKClient",Client)
    monkeypatch.setenv("PMOS_AUTH_MODE","oidc");monkeypatch.setenv("PMOS_OIDC_ISSUER","https://identity.example/")
    monkeypatch.setenv("PMOS_OIDC_JWKS_URL","https://identity.example/.well-known/jwks.json");monkeypatch.setenv("PMOS_OIDC_AUDIENCE","pmos-private-api")
    now=int(time.time());claims={"iss":"https://identity.example/","sub":"user-1","aud":"pmos-private-api","iat":now,"exp":now+300,"amr":["webauthn"],"scope":"entities:read claims:read","https://pmos.example/roles":["researcher"],"https://pmos.example/universes":["venture_capital"]}
    claims.update(overrides or {})
    return jwt.encode(claims,private,algorithm="RS256",headers={"kid":"test"})

def test_oidc_validates_signature_issuer_audience_mfa_roles_and_scope(monkeypatch):
    token=_oidc_token(monkeypatch)
    principal=authenticate_private_request(request(),"Bearer "+token,None)
    assert principal.subject=="user-1" and principal.roles==frozenset({"RESEARCHER"})
    authorize(principal,"entities:read",{"RESEARCHER"},"venture_capital")
    with pytest.raises(HTTPException):authorize(principal,"entities:read",{"RESEARCHER"},"private_equity")
    with pytest.raises(HTTPException):authorize(principal,"entities:write",{"RESEARCHER"},"venture_capital")

def test_oidc_rejects_tokens_without_mfa_or_authorized_role(monkeypatch):
    token=_oidc_token(monkeypatch,{"amr":["pwd"]})
    with pytest.raises(HTTPException) as error:authenticate_private_request(request(),"Bearer "+token,None)
    assert error.value.status_code==403

def test_api_enforces_object_scope_and_permissions(monkeypatch):
    import apps.api.app.main as main
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        vc=Entity(name="VC Example",canonical_name="vc example",universe="venture_capital")
        pe=Entity(name="PE Example",canonical_name="pe example",universe="private_equity")
        db.add_all([vc,pe]);db.commit();vc_id=vc.id;pe_id=pe.id
    monkeypatch.setattr(main,"SessionLocal",factory);monkeypatch.setattr(main,"init_db",lambda:None)
    principal=Principal("user-1",frozenset({"RESEARCHER"}),frozenset({"entities:read"}),frozenset({"venture_capital"}),"oidc","test-correlation")
    main.app.dependency_overrides[authenticate_private_request]=lambda:principal
    try:
        with TestClient(main.app) as client:
            response=client.get("/entities");assert response.status_code==200 and [x["id"] for x in response.json()]==[vc_id]
            assert client.get(f"/entities/{vc_id}").status_code==200
            assert client.get(f"/entities/{pe_id}").status_code==403
            assert client.get(f"/entities/{vc_id}/claims").status_code==403
    finally:main.app.dependency_overrides.clear()
    token=_oidc_token(monkeypatch,{"https://pmos.example/roles":["unknown" ]})
    with pytest.raises(HTTPException) as error:authenticate_private_request(request(),"Bearer "+token,None)
    assert error.value.status_code==403
