from __future__ import annotations

import ipaddress
import os
import secrets
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from fastapi import Header, HTTPException, Request

ALLOWED_ROLES={"RESEARCHER","REVIEWER","COUNSEL","ADMIN","EXPORTER"}

@dataclass(frozen=True)
class Principal:
    subject:str
    roles:frozenset[str]
    permissions:frozenset[str]
    universes:frozenset[str]
    auth_mode:str
    correlation_id:str

def _claim_set(value)->frozenset[str]:
    if isinstance(value,str):return frozenset(x for x in value.replace(","," ").split() if x)
    if isinstance(value,(list,tuple,set)):return frozenset(str(x) for x in value if str(x))
    return frozenset()

def _local_principal(request:Request,token:str|None)->Principal:
    try:peer=ipaddress.ip_address(request.client.host if request.client else "")
    except ValueError:raise HTTPException(status_code=403,detail="loopback access required")
    if not peer.is_loopback:raise HTTPException(status_code=403,detail="loopback access required")
    expected=os.getenv("PMOS_DEV_API_TOKEN","")
    if len(expected)<24:raise HTTPException(status_code=503,detail="local private API token is not configured")
    if not token or not secrets.compare_digest(token,expected):raise HTTPException(status_code=401,detail="authentication required")
    return Principal("local-development",frozenset({"ADMIN"}),frozenset({"*"}),frozenset({"*"}),"local",request.state.correlation_id)

def _oidc_principal(request:Request,authorization:str|None)->Principal:
    if not authorization or not authorization.startswith("Bearer "):raise HTTPException(status_code=401,detail="bearer access token required")
    token=authorization[7:].strip()
    if not token or len(token)>16384:raise HTTPException(status_code=401,detail="invalid access token")
    issuer=os.getenv("PMOS_OIDC_ISSUER","").rstrip("/")+"/";audience=os.getenv("PMOS_OIDC_AUDIENCE","");jwks_url=os.getenv("PMOS_OIDC_JWKS_URL","")
    parsed=urlparse(jwks_url);issuer_host=urlparse(issuer).hostname
    if parsed.scheme!="https" or not parsed.hostname or parsed.hostname!=issuer_host or not audience:raise HTTPException(status_code=503,detail="OIDC configuration is incomplete")
    try:
        import jwt
        key=jwt.PyJWKClient(jwks_url,cache_keys=True,cache_jwk_set=True,lifespan=300,timeout=5).get_signing_key_from_jwt(token)
        claims=jwt.decode(token,key.key,algorithms=["RS256"],audience=audience,issuer=issuer,leeway=30,options={"require":["exp","iat","sub","aud","iss"]})
    except Exception:raise HTTPException(status_code=401,detail="invalid access token")
    roles_claim=os.getenv("PMOS_OIDC_ROLES_CLAIM","https://pmos.example/roles")
    universes_claim=os.getenv("PMOS_OIDC_UNIVERSES_CLAIM","https://pmos.example/universes")
    roles=frozenset(x.upper() for x in _claim_set(claims.get(roles_claim))) & ALLOWED_ROLES
    permissions=_claim_set(claims.get("permissions")) | _claim_set(claims.get("scope"))
    universes=_claim_set(claims.get(universes_claim))
    amr={x.casefold() for x in _claim_set(claims.get("amr"))};required_acr=os.getenv("PMOS_REQUIRED_ACR","")
    mfa_ok=bool(amr & {"mfa","otp","webauthn","hwk"}) or bool(required_acr and secrets.compare_digest(str(claims.get("acr","")),required_acr))
    if not mfa_ok:raise HTTPException(status_code=403,detail="multi-factor authentication required")
    if not roles:raise HTTPException(status_code=403,detail="no authorized PMOS role")
    return Principal(str(claims["sub"]),roles,permissions,universes,"oidc",request.state.correlation_id)

def authenticate_private_request(request:Request,authorization:Optional[str]=Header(default=None),x_pmos_token:Optional[str]=Header(default=None))->Principal:
    mode=os.getenv("PMOS_AUTH_MODE","disabled").casefold()
    if mode=="disabled":raise HTTPException(status_code=404,detail="private API disabled")
    if mode=="local":return _local_principal(request,x_pmos_token)
    if mode=="oidc":return _oidc_principal(request,authorization)
    raise HTTPException(status_code=503,detail="unsupported authentication mode")

def authorize(principal:Principal,permission:str,roles:set[str],universe:str|None=None)->None:
    if not principal.roles.intersection(roles):raise HTTPException(status_code=403,detail="role is not authorized")
    if "*" not in principal.permissions and permission not in principal.permissions:raise HTTPException(status_code=403,detail="permission is not authorized")
    if universe is not None and "*" not in principal.universes and universe not in principal.universes:raise HTTPException(status_code=403,detail="object scope is not authorized")
