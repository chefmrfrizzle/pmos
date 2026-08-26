from __future__ import annotations

import ipaddress
import os
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from fastapi import Header, HTTPException, Request

ALLOWED_ROLES={"RESEARCHER","REVIEWER","COUNSEL","ADMIN","EXPORTER"}

class FixedWindowRateLimiter:
    """Small per-process guardrail; production must also rate-limit at the gateway."""
    def __init__(self):
        self._windows:dict[str,tuple[int,int]]={};self._lock=threading.Lock()

    def check(self,key:str)->None:
        try:configured=int(os.getenv("PMOS_RATE_LIMIT_PER_MINUTE","120"))
        except ValueError:configured=120
        limit=max(10,min(configured,1000));window=int(time.monotonic()//60)
        with self._lock:
            if len(self._windows)>10_000:self._windows={k:v for k,v in self._windows.items() if v[0]>=window-1}
            current,count=self._windows.get(key,(window,0))
            if current!=window:current,count=window,0
            if count>=limit:raise HTTPException(status_code=429,detail="request rate limit exceeded",headers={"Retry-After":"60"})
            self._windows[key]=(current,count+1)

    def reset(self)->None:
        with self._lock:self._windows.clear()

rate_limiter=FixedWindowRateLimiter()

@dataclass(frozen=True)
class Principal:
    subject:str
    roles:frozenset[str]
    permissions:frozenset[str]
    universes:frozenset[str]
    auth_mode:str
    correlation_id:str
    tenant_id:str
    purposes:frozenset[str]
    active_purpose:str

def _claim_set(value)->frozenset[str]:
    if isinstance(value,str):return frozenset(x for x in value.replace(","," ").split() if x)
    if isinstance(value,(list,tuple,set)):return frozenset(str(x) for x in value if str(x))
    return frozenset()

def _local_principal(request:Request,token:str|None,purpose:str|None)->Principal:
    try:peer=ipaddress.ip_address(request.client.host if request.client else "")
    except ValueError:raise HTTPException(status_code=403,detail="loopback access required")
    if not peer.is_loopback:raise HTTPException(status_code=403,detail="loopback access required")
    expected=os.getenv("PMOS_DEV_API_TOKEN","")
    if len(expected)<24:raise HTTPException(status_code=503,detail="local private API token is not configured")
    if not token or not secrets.compare_digest(token,expected):raise HTTPException(status_code=401,detail="authentication required")
    tenant=os.getenv("PMOS_TENANT_ID","local-private").strip()
    return Principal("local-development",frozenset({"ADMIN"}),frozenset({"*"}),frozenset({"*"}),"local",request.state.correlation_id,tenant,frozenset({"*"}),(purpose or "*").strip())

def _oidc_principal(request:Request,authorization:str|None,purpose:str|None)->Principal:
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
    tenant_claim=os.getenv("PMOS_OIDC_TENANT_CLAIM","https://pmos.example/tenant")
    purposes_claim=os.getenv("PMOS_OIDC_PURPOSES_CLAIM","https://pmos.example/purposes")
    roles=frozenset(x.upper() for x in _claim_set(claims.get(roles_claim))) & ALLOWED_ROLES
    permissions=_claim_set(claims.get("permissions")) | _claim_set(claims.get("scope"))
    universes=_claim_set(claims.get(universes_claim))
    configured_tenant=os.getenv("PMOS_TENANT_ID","").strip();token_tenant=str(claims.get(tenant_claim,"")).strip()
    purposes=_claim_set(claims.get(purposes_claim));active_purpose=(purpose or "").strip()
    amr={x.casefold() for x in _claim_set(claims.get("amr"))};required_acr=os.getenv("PMOS_REQUIRED_ACR","")
    mfa_ok=bool(amr & {"mfa","otp","webauthn","hwk"}) or bool(required_acr and secrets.compare_digest(str(claims.get("acr","")),required_acr))
    if not mfa_ok:raise HTTPException(status_code=403,detail="multi-factor authentication required")
    if not roles:raise HTTPException(status_code=403,detail="no authorized PMOS role")
    if not configured_tenant or not token_tenant or not secrets.compare_digest(configured_tenant,token_tenant):raise HTTPException(status_code=403,detail="tenant scope is not authorized")
    normalized_purpose=" ".join(active_purpose.casefold().split());normalized_allowed={" ".join(x.casefold().split()) for x in purposes}
    if len(active_purpose)<3 or len(active_purpose)>500 or ("*" not in purposes and normalized_purpose not in normalized_allowed):raise HTTPException(status_code=403,detail="declared purpose is not authorized")
    return Principal(str(claims["sub"]),roles,permissions,universes,"oidc",request.state.correlation_id,token_tenant,purposes,active_purpose)

def authenticate_private_request(request:Request,authorization:Optional[str]=Header(default=None),x_pmos_token:Optional[str]=Header(default=None),x_pmos_purpose:Optional[str]=Header(default=None))->Principal:
    purpose=x_pmos_purpose if isinstance(x_pmos_purpose,str) else None
    mode=os.getenv("PMOS_AUTH_MODE","disabled").casefold()
    if mode=="disabled":raise HTTPException(status_code=404,detail="private API disabled")
    if mode=="local":principal=_local_principal(request,x_pmos_token,purpose)
    elif mode=="oidc":principal=_oidc_principal(request,authorization,purpose)
    else:raise HTTPException(status_code=503,detail="unsupported authentication mode")
    peer=request.client.host if request.client else "unknown"
    rate_limiter.check(f"{principal.auth_mode}:{principal.subject}:{peer}")
    return principal

def authorize(principal:Principal,permission:str,roles:set[str],universe:str|None=None,required_purpose:str|None=None)->None:
    if not principal.roles.intersection(roles):raise HTTPException(status_code=403,detail="role is not authorized")
    if "*" not in principal.permissions and permission not in principal.permissions:raise HTTPException(status_code=403,detail="permission is not authorized")
    if universe is not None and "*" not in principal.universes and universe not in principal.universes:raise HTTPException(status_code=403,detail="object scope is not authorized")
    if required_purpose is not None and principal.active_purpose!="*" and " ".join(principal.active_purpose.casefold().split())!=" ".join(required_purpose.casefold().split()):raise HTTPException(status_code=403,detail="case permitted use does not match the active purpose")
