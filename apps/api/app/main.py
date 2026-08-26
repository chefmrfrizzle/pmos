from __future__ import annotations
from pathlib import Path
import sys, uuid
from typing import Optional
from contextlib import asynccontextmanager
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"packages/research"))
from fastapi import FastAPI, Query, Depends, HTTPException, Request
from .security import Principal,authenticate_private_request,authorize
from pmos_research.audit_ledger import append_ledger_event
from pmos_research.db import init_db, SessionLocal, Entity

@asynccontextmanager
async def lifespan(app):
    init_db();yield

app=FastAPI(title="PMOS Private API",version="0.2.0",lifespan=lifespan)

@app.middleware("http")
async def correlation_id(request:Request,call_next):
    request.state.correlation_id=request.headers.get("x-request-id") or str(uuid.uuid4())
    response=await call_next(request);response.headers["X-Request-ID"]=request.state.correlation_id;return response

def audit_access(session,principal:Principal,action:str,payload:dict):
    append_ledger_event(session,"API_ACCESS",principal.subject,principal.subject,",".join(sorted(principal.roles)),action,payload,principal.correlation_id)

@app.get("/health")
def health(): return {"ok":True,"service":"pmos-api"}

@app.get("/entities")
def entities(universe:Optional[str]=None, q:Optional[str]=None, limit:int=Query(100,ge=1,le=500),principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"entities:read",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"},universe)
    with SessionLocal() as s:
        query=s.query(Entity)
        if universe: query=query.filter(Entity.universe==universe)
        elif "*" not in principal.universes:query=query.filter(Entity.universe.in_(principal.universes))
        if q: query=query.filter(Entity.name.ilike(f"%{q}%"))
        rows=query.order_by(Entity.strategic_priority.desc(),Entity.name).limit(limit).all()
        audit_access(s,principal,"ENTITIES_LISTED",{"universe":universe,"query_present":bool(q),"limit":limit,"result_count":len(rows)});s.commit()
        return [{"id":e.id,"name":e.name,"universe":e.universe,"country":e.country,"city":e.city,"official_url":e.official_url,"verification_status":e.verification_status,"evidence_confidence":e.evidence_confidence,"strategic_priority":e.strategic_priority,"useful_wedge":e.useful_wedge} for e in rows]

@app.get("/entities/{entity_id}")
def entity(entity_id:int,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        e=s.get(Entity,entity_id)
        if not e:raise HTTPException(status_code=404,detail="not found")
        authorize(principal,"entities:read",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"},e.universe)
        audit_access(s,principal,"ENTITY_VIEWED",{"entity_id":entity_id});s.commit()
        return {c.name:getattr(e,c.name) for c in e.__table__.columns}

@app.get("/entities/{entity_id}/claims")
def claims(entity_id:int,principal:Principal=Depends(authenticate_private_request)):
    from pmos_research.db import Claim
    with SessionLocal() as s:
        entity=s.get(Entity,entity_id)
        if not entity:raise HTTPException(status_code=404,detail="not found")
        authorize(principal,"claims:read",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"},entity.universe)
        rows=s.query(Claim).filter(Claim.entity_id==entity_id).order_by(Claim.confidence.desc()).limit(500).all()
        audit_access(s,principal,"CLAIMS_VIEWED",{"entity_id":entity_id,"result_count":len(rows)});s.commit()
        return [{"field":x.field,"value":x.value,"source_url":x.source_url,"confidence":x.confidence,"verification_status":x.verification_status,"observed_at":x.observed_at} for x in rows]
