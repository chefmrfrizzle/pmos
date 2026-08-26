from __future__ import annotations
from pathlib import Path
import json, os, sys, uuid
from typing import Optional
from contextlib import asynccontextmanager
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"packages/research"))
from fastapi import FastAPI, Query, Depends, HTTPException, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel,Field
from sqlalchemy import select
from .security import Principal,authenticate_private_request,authorize
from pmos_research.audit_ledger import append_ledger_event
from pmos_research.db import ClaimCheckRoutingCandidate,CheckResult,ControlAssuranceRun,DiligenceCase,DiligenceCheckEvidence,ExportRequest,ResearchPassageCandidate,ReviewQueueItem,SourceChangeEvent,init_db, SessionLocal, Entity
from pmos_research.case_checks import CheckAdjudicationError,adjudicate_check,evidence_sufficiency,submit_check_evidence
from pmos_research.diligence import readiness
from pmos_research.dossier import build_dossier
from pmos_research.adjudication import AdjudicationInputError,StaleReviewError,adjudicate
from pmos_research.identity_review import build_review_packet
from pmos_research.passage_adjudication import PassageAdjudicationError,adjudicate_passage
from pmos_research.passage_review import build_passage_packet
from pmos_research.evidence_routing import EvidenceRoutingError,adjudicate_route
from pmos_research.evidence_route_review import build_route_packet
from pmos_research.change_review import ChangeReviewError,adjudicate_change,build_change_packet
from pmos_research.export_governance import ExportGovernanceError,adjudicate_export_request,request_dossier_export

class CheckEvidenceRequest(BaseModel):
    claim_ids:list[int]=Field(min_length=1,max_length=50)
    rationale:str=Field(min_length=10,max_length=2000)

class CheckActionRequest(BaseModel):
    action:str=Field(min_length=3,max_length=40)
    rationale:str=Field(min_length=10,max_length=2000)
    expected_status:Optional[str]=Field(default=None,max_length=40)

class IdentityActionRequest(BaseModel):
    action:str=Field(min_length=5,max_length=40)
    rationale:str=Field(min_length=10,max_length=2000)
    evidence_ids:list[int]=Field(default_factory=list,max_length=25)
    expected_version:str=Field(min_length=10,max_length=80)

class PassageActionRequest(BaseModel):
    action:str=Field(min_length=5,max_length=40)
    rationale:str=Field(min_length=10,max_length=2000)
    claim_value:Optional[str]=Field(default=None,max_length=1000)
    expected_status:str=Field(min_length=5,max_length=40)

class RoutingActionRequest(BaseModel):
    action:str=Field(min_length=5,max_length=20)
    rationale:str=Field(min_length=10,max_length=2000)
    expected_status:str=Field(min_length=5,max_length=40)

class ChangeActionRequest(BaseModel):
    action:str=Field(min_length=5,max_length=20)
    rationale:str=Field(min_length=10,max_length=2000)
    expected_status:str=Field(min_length=5,max_length=40)

class ExportRequestCreate(BaseModel):
    case_id:int=Field(gt=0)
    purpose:str=Field(min_length=3,max_length=500)
    expires_hours:int=Field(default=24,ge=1,le=72)

class ExportActionRequest(BaseModel):
    action:str=Field(min_length=6,max_length=10)
    rationale:str=Field(min_length=10,max_length=2000)
    expected_status:str=Field(min_length=5,max_length=30)

@asynccontextmanager
async def lifespan(app):
    init_db();yield

class BodySizeLimitMiddleware:
    def __init__(self,app,max_bytes:int=1_048_576):self.app=app;self.max_bytes=max_bytes
    async def __call__(self,scope,receive,send):
        if scope["type"]!="http":return await self.app(scope,receive,send)
        headers=dict(scope.get("headers",[]));declared=headers.get(b"content-length")
        if declared:
            try:too_large=int(declared)>self.max_bytes
            except ValueError:too_large=True
            if too_large:return await self._reject(send)
        consumed=0
        async def limited_receive():
            nonlocal consumed
            message=await receive()
            if message["type"]=="http.request":
                consumed+=len(message.get("body",b""))
                if consumed>self.max_bytes:raise _BodyTooLarge
            return message
        try:return await self.app(scope,limited_receive,send)
        except _BodyTooLarge:return await self._reject(send)
    async def _reject(self,send):
        body=b'{"detail":"request body too large"}'
        await send({"type":"http.response.start","status":413,"headers":[(b"content-type",b"application/json"),(b"content-length",str(len(body)).encode())]})
        await send({"type":"http.response.body","body":body})

class _BodyTooLarge(Exception):pass

def _request_limit()->int:
    try:value=int(os.getenv("PMOS_MAX_REQUEST_BYTES","1048576"))
    except ValueError:value=1_048_576
    return max(16_384,min(value,4_194_304))

app=FastAPI(title="PMOS Private API",version="0.3.0",lifespan=lifespan)
allowed_hosts=[x.strip() for x in os.getenv("PMOS_ALLOWED_HOSTS","localhost,127.0.0.1,[::1],testserver").split(",") if x.strip()]
app.add_middleware(TrustedHostMiddleware,allowed_hosts=allowed_hosts)
app.add_middleware(BodySizeLimitMiddleware,max_bytes=_request_limit())

@app.middleware("http")
async def correlation_id(request:Request,call_next):
    request.state.correlation_id=request.headers.get("x-request-id") or str(uuid.uuid4())
    response=await call_next(request)
    response.headers.update({"X-Request-ID":request.state.correlation_id,"Cache-Control":"no-store","X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"no-referrer","Permissions-Policy":"camera=(), microphone=(), geolocation=(), payment=()","Content-Security-Policy":"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"})
    return response

def audit_access(session,principal:Principal,action:str,payload:dict):
    append_ledger_event(session,"API_ACCESS",principal.subject,principal.subject,",".join(sorted(principal.roles)),action,{**payload,"tenant_id":principal.tenant_id,"purpose":principal.active_purpose},principal.correlation_id)

@app.get("/identity-review")
def identity_review_queue(status:str="PENDING",queue_type:Optional[str]=None,limit:int=Query(50,ge=1,le=100),include_excerpt:bool=False,principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"identity:review",{"RESEARCHER","REVIEWER","ADMIN"})
    with SessionLocal() as s:
        query=s.query(ReviewQueueItem).filter(ReviewQueueItem.status==status.upper())
        if queue_type:query=query.filter(ReviewQueueItem.queue_type==queue_type.upper())
        items=query.order_by(ReviewQueueItem.priority.desc(),ReviewQueueItem.id).limit(limit*5).all();rows=[]
        for item in items:
            packet=build_review_packet(s,item.id,include_excerpt=include_excerpt)
            if "*" in principal.universes or packet["universe"] in principal.universes:rows.append(packet)
            if len(rows)>=limit:break
        audit_access(s,principal,"IDENTITY_REVIEW_LISTED",{"status":status.upper(),"queue_type":queue_type,"limit":limit,"result_count":len(rows),"include_excerpt":include_excerpt});s.commit();return rows

@app.post("/identity-review/{item_id}/actions")
def identity_review_action(item_id:int,body:IdentityActionRequest,principal:Principal=Depends(authenticate_private_request)):
    approval=body.action.upper()=="APPROVE_MATCH";permission="identity:approve" if approval else "identity:write";roles={"REVIEWER","ADMIN"} if approval else {"RESEARCHER","REVIEWER","ADMIN"}
    with SessionLocal() as s:
        packet=build_review_packet(s,item_id)
        authorize(principal,permission,roles,packet["universe"])
        try:result=adjudicate(s,item_id,body.action,principal.subject,body.rationale,body.evidence_ids,body.expected_version)
        except StaleReviewError as exc:raise HTTPException(status_code=409,detail=str(exc))
        except AdjudicationInputError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"IDENTITY_REVIEW_ACTION",{"item_id":item_id,"action":body.action.upper(),"resulting_state":result["resulting_state"],"evidence_count":len(set(body.evidence_ids))});s.commit();return result

@app.get("/evidence-review/passages")
def passage_review_queue(status:str="HUMAN_REVIEW_REQUIRED",limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"evidence:review",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"})
    with SessionLocal() as s:
        candidates=s.query(ResearchPassageCandidate).filter(ResearchPassageCandidate.status==status.upper()).order_by(ResearchPassageCandidate.confidence.desc(),ResearchPassageCandidate.id).limit(limit*5).all();rows=[]
        for candidate in candidates:
            packet=build_passage_packet(s,candidate.id)
            if "*" in principal.universes or packet["universe"] in principal.universes:rows.append(packet)
            if len(rows)>=limit:break
        audit_access(s,principal,"PASSAGE_REVIEW_LISTED",{"status":status.upper(),"limit":limit,"result_count":len(rows)});s.commit();return rows

@app.post("/evidence-review/passages/{candidate_id}/actions")
def passage_review_action(candidate_id:int,body:PassageActionRequest,principal:Principal=Depends(authenticate_private_request)):
    approval=body.action.upper()=="APPROVE_SUPPORT";permission="evidence:approve" if approval else "evidence:write";roles={"REVIEWER","COUNSEL","ADMIN"} if approval else {"RESEARCHER","REVIEWER","COUNSEL","ADMIN"}
    with SessionLocal() as s:
        packet=build_passage_packet(s,candidate_id);authorize(principal,permission,roles,packet["universe"])
        try:result=adjudicate_passage(s,candidate_id,body.action,principal.subject,body.rationale,body.claim_value,body.expected_status)
        except PassageAdjudicationError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"PASSAGE_REVIEW_ACTION",{"candidate_id":candidate_id,"action":body.action.upper(),"resulting_state":result["resulting_state"],"claim_created":bool(result["claim_id"])});s.commit();return result

@app.get("/evidence-review/routing")
def evidence_routing_queue(status:str="PENDING_REVIEW",limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"evidence:routing:review",{"RESEARCHER","REVIEWER","ADMIN"})
    with SessionLocal() as s:
        routes=s.query(ClaimCheckRoutingCandidate).filter(ClaimCheckRoutingCandidate.status==status.upper()).order_by(ClaimCheckRoutingCandidate.id).limit(limit*5).all();rows=[]
        for route in routes:
            packet=build_route_packet(s,route.id)
            if "*" in principal.universes or packet["universe"] in principal.universes:rows.append(packet)
            if len(rows)>=limit:break
        audit_access(s,principal,"EVIDENCE_ROUTING_LISTED",{"status":status.upper(),"limit":limit,"result_count":len(rows)});s.commit();return rows

@app.post("/evidence-review/routing/{route_id}/actions")
def evidence_routing_action(route_id:int,body:RoutingActionRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        packet=build_route_packet(s,route_id);authorize(principal,"evidence:routing:write",{"RESEARCHER","REVIEWER","ADMIN"},packet["universe"])
        try:result=adjudicate_route(s,route_id,body.action,principal.subject,body.rationale,body.expected_status)
        except EvidenceRoutingError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"EVIDENCE_ROUTING_ACTION",{"route_id":route_id,"action":body.action.upper(),"resulting_state":result["resulting_state"],"check_id":result["check_id"]});s.commit();return result

@app.get("/evidence-review/source-changes")
def source_change_queue(status:str="HUMAN_REVIEW_REQUIRED",limit:int=Query(25,ge=1,le=50),principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"evidence:review",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"})
    with SessionLocal() as s:
        events=s.query(SourceChangeEvent).filter(SourceChangeEvent.status==status.upper()).order_by(SourceChangeEvent.detected_at.desc(),SourceChangeEvent.id.desc()).limit(limit*5).all();rows=[]
        for event in events:
            packet=build_change_packet(s,event.id)
            if "*" in principal.universes or packet["universe"] in principal.universes:rows.append(packet)
            if len(rows)>=limit:break
        audit_access(s,principal,"SOURCE_CHANGE_LISTED",{"status":status.upper(),"limit":limit,"result_count":len(rows)});s.commit();return rows

@app.post("/evidence-review/source-changes/{event_id}/actions")
def source_change_action(event_id:int,body:ChangeActionRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        packet=build_change_packet(s,event_id);authorize(principal,"evidence:write",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"},packet["universe"])
        try:result=adjudicate_change(s,event_id,body.action,principal.subject,body.rationale,body.expected_status)
        except ChangeReviewError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"SOURCE_CHANGE_ACTION",{"event_id":event_id,"action":body.action.upper(),"resulting_state":result["resulting_state"]});s.commit();return result

def _export_packet(session,request_id:int):
    request=session.get(ExportRequest,request_id)
    if not request:raise HTTPException(status_code=404,detail="not found")
    case=session.get(DiligenceCase,request.case_id);entity=session.get(Entity,case.entity_id) if case else None
    if not case or not entity:raise HTTPException(status_code=409,detail="export request scope is invalid")
    return request,case,entity,{"id":request.id,"case_id":request.case_id,"scope":request.scope,"format":request.format,"purpose":request.purpose,"requester":request.requester,"status":request.status,"expires_at":request.expires_at,"approved_by":request.approved_by,"artifact_name":request.artifact_name,"artifact_sha256":request.artifact_sha256,"universe":entity.universe}

@app.post("/exports/requests")
def create_export_request(body:ExportRequestCreate,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        case,entity=_case_scope(s,body.case_id,principal,"exports:request",{"RESEARCHER","REVIEWER","ADMIN"})
        try:request=request_dossier_export(s,case.id,body.purpose,principal.subject,body.expires_hours)
        except ExportGovernanceError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"EXPORT_REQUEST_CREATED",{"request_id":request.id,"case_id":case.id,"expires_at":request.expires_at.isoformat()});s.commit();return _export_packet(s,request.id)[3]

@app.get("/exports/requests/{request_id}")
def get_export_request(request_id:int,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        request,case,entity,packet=_export_packet(s,request_id);authorize(principal,"exports:read",{"RESEARCHER","REVIEWER","EXPORTER","ADMIN"},entity.universe)
        if principal.subject!=request.requester and not principal.roles.intersection({"EXPORTER","ADMIN"}):raise HTTPException(status_code=403,detail="request ownership is required")
        audit_access(s,principal,"EXPORT_REQUEST_VIEWED",{"request_id":request.id,"status":request.status});s.commit();return packet

@app.post("/exports/requests/{request_id}/actions")
def decide_export_request(request_id:int,body:ExportActionRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        request,case,entity,packet=_export_packet(s,request_id);authorize(principal,"exports:approve",{"EXPORTER","ADMIN"},entity.universe)
        try:request=adjudicate_export_request(s,request.id,body.action,principal.subject,body.rationale,body.expected_status)
        except ExportGovernanceError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"EXPORT_REQUEST_DECIDED",{"request_id":request.id,"action":body.action.upper(),"resulting_state":request.status});s.commit();return _export_packet(s,request.id)[3]

@app.get("/health")
def health(): return {"ok":True,"service":"pmos-api"}

@app.get("/assurance/latest")
def latest_assurance(principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"assurance:read",{"REVIEWER","COUNSEL","ADMIN"})
    with SessionLocal() as s:
        run=s.query(ControlAssuranceRun).order_by(ControlAssuranceRun.created_at.desc(),ControlAssuranceRun.id.desc()).first()
        if not run:raise HTTPException(status_code=404,detail="no assurance run is available")
        result=json.loads(run.report_json);result["run_id"]=run.id;result["report_hash"]=run.report_hash
        audit_access(s,principal,"ASSURANCE_VIEWED",{"run_id":run.id,"status":run.status,"exception_count":run.exception_count});s.commit();return result

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
    authorize(principal,permission,roles,entity.universe,case.permitted_use);return case,entity

@app.get("/diligence-cases/{case_id}")
def diligence_case(case_id:int,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        case,entity=_case_scope(s,case_id,principal,"checks:read",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"})
        checks=s.query(CheckResult).filter(CheckResult.case_id==case.id).order_by(CheckResult.id).all();evidence={x.id:sorted(s.scalars(select(DiligenceCheckEvidence.claim_id).where(DiligenceCheckEvidence.check_id==x.id)).all()) for x in checks}
        audit_access(s,principal,"DILIGENCE_CASE_VIEWED",{"case_id":case.id});s.commit()
        return {"id":case.id,"entity_id":case.entity_id,"status":case.status,"risk_tier":case.risk_tier,"as_of":case.as_of,"readiness":readiness(s,case.id),"checks":[{"id":x.id,"code":x.check_code,"status":x.status,"mandatory":x.mandatory,"exception_reason":x.exception_reason,"claim_ids":evidence[x.id],"sufficiency":evidence_sufficiency(s,x.id)} for x in checks]}

@app.get("/diligence-cases/{case_id}/dossier")
def diligence_dossier(case_id:int,include_passages:bool=True,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        case,entity=_case_scope(s,case_id,principal,"dossiers:read",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"})
        result=build_dossier(s,case.id,include_passages=include_passages)
        audit_access(s,principal,"DILIGENCE_DOSSIER_VIEWED",{"case_id":case.id,"include_passages":include_passages,"claim_count":len(result["claims"])});s.commit()
        return result

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
