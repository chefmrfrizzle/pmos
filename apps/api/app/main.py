from __future__ import annotations
from pathlib import Path
import sys, uuid
from typing import Optional
from contextlib import asynccontextmanager
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"packages/research"))
from fastapi import FastAPI, Query, Depends, HTTPException, Request
from pydantic import BaseModel,Field
from sqlalchemy import select
from .security import Principal,authenticate_private_request,authorize
from pmos_research.audit_ledger import append_ledger_event
from pmos_research.db import CheckResult,DiligenceCase,DiligenceCheckEvidence,init_db, SessionLocal, Entity
from pmos_research.case_checks import CheckAdjudicationError,adjudicate_check,evidence_sufficiency,submit_check_evidence
from pmos_research.diligence import readiness

class CheckEvidenceRequest(BaseModel):
    claim_ids:list[int]=Field(min_length=1,max_length=50)
    rationale:str=Field(min_length=10,max_length=2000)

class CheckActionRequest(BaseModel):
    action:str=Field(min_length=3,max_length=40)
    rationale:str=Field(min_length=10,max_length=2000)
    expected_status:Optional[str]=Field(default=None,max_length=40)

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

def _case_scope(session,case_id:int,principal:Principal,permission:str,roles:set[str]):
    case=session.get(DiligenceCase,case_id)
    if not case:raise HTTPException(status_code=404,detail="not found")
    entity=session.get(Entity,case.entity_id)
    if not entity:raise HTTPException(status_code=404,detail="not found")
    authorize(principal,permission,roles,entity.universe);return case,entity

@app.get("/diligence-cases/{case_id}")
def diligence_case(case_id:int,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        case,entity=_case_scope(s,case_id,principal,"checks:read",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"})
        checks=s.query(CheckResult).filter(CheckResult.case_id==case.id).order_by(CheckResult.id).all();evidence={x.id:sorted(s.scalars(select(DiligenceCheckEvidence.claim_id).where(DiligenceCheckEvidence.check_id==x.id)).all()) for x in checks}
        audit_access(s,principal,"DILIGENCE_CASE_VIEWED",{"case_id":case.id});s.commit()
        return {"id":case.id,"entity_id":case.entity_id,"status":case.status,"risk_tier":case.risk_tier,"as_of":case.as_of,"readiness":readiness(s,case.id),"checks":[{"id":x.id,"code":x.check_code,"status":x.status,"mandatory":x.mandatory,"exception_reason":x.exception_reason,"claim_ids":evidence[x.id],"sufficiency":evidence_sufficiency(s,x.id)} for x in checks]}

@app.post("/diligence-cases/{case_id}/checks/{check_id}/evidence")
def attach_check_evidence(case_id:int,check_id:int,body:CheckEvidenceRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        case,entity=_case_scope(s,case_id,principal,"checks:write",{"RESEARCHER","REVIEWER","ADMIN"});check=s.get(CheckResult,check_id)
        if not check or check.case_id!=case.id:raise HTTPException(status_code=404,detail="not found")
        try:submit_check_evidence(s,check.id,body.claim_ids,principal.subject,body.rationale)
        except CheckAdjudicationError as exc:raise HTTPException(status_code=409,detail=str(exc))
        audit_access(s,principal,"CHECK_EVIDENCE_ATTACHED",{"case_id":case.id,"check_id":check.id,"claim_count":len(set(body.claim_ids))});s.commit()
        return {"check_id":check.id,"status":check.status,"sufficiency":evidence_sufficiency(s,check.id)}

@app.post("/diligence-cases/{case_id}/checks/{check_id}/actions")
def act_on_check(case_id:int,check_id:int,body:CheckActionRequest,principal:Principal=Depends(authenticate_private_request)):
    action=body.action.upper();approval=action in {"APPROVE","APPROVE_EXCEPTION"};permission="checks:approve" if approval else "checks:write";roles={"REVIEWER","COUNSEL","ADMIN"} if approval else {"RESEARCHER","REVIEWER","ADMIN"}
    with SessionLocal() as s:
        case,entity=_case_scope(s,case_id,principal,permission,roles);check=s.get(CheckResult,check_id)
        if not check or check.case_id!=case.id:raise HTTPException(status_code=404,detail="not found")
        try:adjudicate_check(s,check.id,action,principal.subject,body.rationale,body.expected_status)
        except CheckAdjudicationError as exc:raise HTTPException(status_code=409,detail=str(exc))
        audit_access(s,principal,"CHECK_ACTION",{"case_id":case.id,"check_id":check.id,"action":action,"resulting_status":check.status});s.commit()
        return {"check_id":check.id,"status":check.status,"readiness":readiness(s,case.id)}
