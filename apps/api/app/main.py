from __future__ import annotations
from pathlib import Path
import json, os, re, sys, uuid
from typing import Optional
from contextlib import asynccontextmanager
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"packages/research"))
from fastapi import FastAPI, Query, Depends, HTTPException, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel,Field
from sqlalchemy import select
from .security import Principal,authenticate_private_request,authorize
from pmos_research.audit_ledger import append_ledger_event
from pmos_research.db import ClaimCheckRoutingCandidate,CheckResult,ControlAssuranceRun,DiligenceCase,DiligenceCheckEvidence,EvidencePassage,ExportRequest,JurisdictionReviewCase,LegalHold,PrivateEgressReviewCase,PrivateSaleCase,PrivateSaleGate,PublisherIndependenceAssessment,RelationshipAssertion,RelationshipMentionCandidate,RelationshipMentionReviewAssignment,RelationshipResearchCandidate,ResearchPassageCandidate,ResolutionDecision,ReviewQueueItem,SecurityReadinessRun,SourceChangeEvent,SourceDocument,UniverseCoverageRun,init_db, SessionLocal, Entity
from pmos_research.case_checks import CheckAdjudicationError,adjudicate_check,evidence_sufficiency,submit_check_evidence
from pmos_research.diligence import readiness
from pmos_research.dossier import build_dossier
from pmos_research.adjudication import AdjudicationInputError,StaleReviewError,adjudicate
from pmos_research.identity_review import build_review_packet
from pmos_research.identity_review_batch import IdentityReviewBatchError,build_identity_batch_packet,freeze_identity_batch
from pmos_research.identity_review_assignment import IdentityReviewAssignmentError,assign_identity_reviewer,assigned_identity_batch_items,close_identity_batch,revoke_identity_assignment
from pmos_research.passage_adjudication import PassageAdjudicationError,adjudicate_passage
from pmos_research.passage_review import build_passage_packet
from pmos_research.evidence_routing import EvidenceRoutingError,adjudicate_route
from pmos_research.evidence_route_review import build_route_packet
from pmos_research.change_review import ChangeReviewError,adjudicate_change,build_change_packet
from pmos_research.export_governance import ExportGovernanceError,adjudicate_export_request,request_dossier_export
from pmos_research.relationship_controls import adjudicate_relationship,propose_relationship
from pmos_research.relationship_review import build_relationship_packet
from pmos_research.relationship_research import RelationshipResearchError,adjudicate_relationship_candidate,adjudicate_relationship_mention,build_relationship_candidate_packet,build_relationship_mention_packet
from pmos_research.private_sale import PrivateSaleError,adjudicate_gate,open_private_sale,submit_gate_evidence
from pmos_research.private_sale_review import build_private_sale_packet
from pmos_research.jurisdiction_review import JurisdictionReviewError,adjudicate_jurisdiction,build_jurisdiction_packet
from pmos_research.evidence_review_batch import EvidenceReviewBatchError,build_batch_packet,freeze_review_batch
from pmos_research.evidence_review_assignment import EvidenceReviewAssignmentError,assign_reviewer,assigned_evidence_batch_items,close_batch,revoke_assignment
from pmos_research.publisher_independence import PublisherIndependenceError,adjudicate_publisher_independence,build_publisher_independence_packet,propose_publisher_independence
from pmos_research.relationship_mention_review import RelationshipMentionReviewError,assign_mention_reviewer,assigned_mention_batch_items,build_mention_review_batch_packet,close_mention_review_batch,freeze_mention_review_batch,revoke_mention_assignment
from pmos_research.retention import RetentionError,adjudicate_legal_hold,build_legal_hold_packet,propose_class_legal_hold
from pmos_research.private_egress_review import PrivateEgressReviewError,adjudicate_private_egress,build_private_egress_packet

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
    review_batch_id:int=Field(gt=0)

class IdentityBatchRequest(BaseModel):
    universe:str=Field(min_length=1,max_length=100)
    status:str=Field(default="PENDING",min_length=5,max_length=30)
    queue_type:Optional[str]=Field(default=None,max_length=50)
    resolution_state:Optional[str]=Field(default=None,max_length=40)
    min_priority:int=Field(default=0,ge=0,le=100)
    limit:int=Field(default=100,ge=1,le=100)

class IdentityAssignmentRequest(BaseModel):
    reviewer:str=Field(min_length=1,max_length=150)
    reviewer_role:str=Field(min_length=5,max_length=40)
    rationale:str=Field(min_length=10,max_length=2000)
    expires_hours:int=Field(default=24,ge=1,le=168)

class JurisdictionActionRequest(BaseModel):
    action:str=Field(min_length=6,max_length=30)
    rationale:str=Field(min_length=10,max_length=2000)
    source_claim_id:Optional[int]=Field(default=None,gt=0)
    expected_status:str=Field(min_length=5,max_length=40)

class RelationshipProposalRequest(BaseModel):
    from_entity_id:int=Field(gt=0)
    to_entity_id:int=Field(gt=0)
    relation_type:str=Field(min_length=3,max_length=80)
    evidence_passage_ids:list[int]=Field(min_length=1,max_length=25)
    jurisdiction:Optional[str]=Field(default=None,max_length=10)

class RelationshipActionRequest(BaseModel):
    action:str=Field(min_length=5,max_length=20)
    rationale:str=Field(min_length=10,max_length=2000)
    expected_status:Optional[str]=Field(default=None,max_length=40)

class RelationshipCandidateActionRequest(BaseModel):
    action:str=Field(min_length=5,max_length=30)
    rationale:str=Field(min_length=10,max_length=2000)
    expected_status:str=Field(min_length=5,max_length=40)

class RelationshipMentionActionRequest(BaseModel):
    action:str=Field(min_length=5,max_length=20)
    rationale:str=Field(min_length=10,max_length=2000)
    expected_status:str=Field(min_length=5,max_length=40)
    target_entity_id:Optional[int]=Field(default=None,gt=0)
    review_batch_id:int=Field(gt=0)

class RelationshipMentionBatchRequest(BaseModel):
    universe:str=Field(min_length=1,max_length=100)
    status:str=Field(default="ENTITY_RESOLUTION_REQUIRED",min_length=5,max_length=40)
    limit:int=Field(default=100,ge=1,le=100)

class PublisherIndependenceProposalRequest(BaseModel):
    source_domain:str=Field(min_length=4,max_length=300)
    independence_group:str=Field(min_length=1,max_length=300)
    rationale:str=Field(min_length=10,max_length=2000)
    evidence_passage_ids:list[int]=Field(min_length=1,max_length=25)

class PublisherIndependenceActionRequest(BaseModel):
    action:str=Field(min_length=5,max_length=20)
    rationale:str=Field(min_length=10,max_length=2000)
    expected_status:str=Field(min_length=5,max_length=40)

class PrivateSaleCreateRequest(BaseModel):
    asset_entity_id:int=Field(gt=0)
    seller_entity_id:Optional[int]=Field(default=None,gt=0)
    purpose:str=Field(min_length=3,max_length=500)
    permitted_use:str=Field(min_length=3,max_length=500)
    jurisdiction:Optional[str]=Field(default=None,max_length=10)

class PrivateSaleEvidenceRequest(BaseModel):
    claim_ids:list[int]=Field(min_length=1,max_length=50)

class PrivateSaleGateActionRequest(BaseModel):
    action:str=Field(min_length=6,max_length=30)
    rationale:str=Field(min_length=10,max_length=2000)
    expected_status:Optional[str]=Field(default=None,max_length=40)

class PassageActionRequest(BaseModel):
    action:str=Field(min_length=5,max_length=40)
    rationale:str=Field(min_length=10,max_length=2000)
    claim_value:Optional[str]=Field(default=None,max_length=1000)
    expected_status:str=Field(min_length=5,max_length=40)
    review_batch_id:int=Field(gt=0)

class EvidenceBatchRequest(BaseModel):
    universe:str=Field(min_length=1,max_length=100)
    status:str=Field(default="HUMAN_REVIEW_REQUIRED",min_length=5,max_length=40)
    predicate:Optional[str]=Field(default=None,max_length=120)
    min_confidence:float=Field(default=0,ge=0,le=1)
    limit:int=Field(default=50,ge=1,le=100)

class EvidenceAssignmentRequest(BaseModel):
    reviewer:str=Field(min_length=1,max_length=150)
    reviewer_role:str=Field(min_length=5,max_length=40)
    rationale:str=Field(min_length=10,max_length=2000)
    expires_hours:int=Field(default=24,ge=1,le=168)

class EvidenceLifecycleRequest(BaseModel):
    rationale:str=Field(min_length=10,max_length=2000)

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

class LegalHoldProposalRequest(BaseModel):
    data_class:str=Field(min_length=3,max_length=80)
    reason:str=Field(min_length=10,max_length=2000)

class LegalHoldActionRequest(BaseModel):
    action:str=Field(min_length=6,max_length=10)
    rationale:str=Field(min_length=10,max_length=2000)
    expected_status:str=Field(min_length=6,max_length=30)

class PrivateEgressActionRequest(BaseModel):
    action:str=Field(min_length=16,max_length=40)
    rationale:str=Field(min_length=20,max_length=4000)
    expected_status:str=Field(min_length=4,max_length=40)

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
    supplied=request.headers.get("x-request-id","");request.state.correlation_id=supplied if re.fullmatch(r"[A-Za-z0-9._:-]{1,100}",supplied) else str(uuid.uuid4())
    response=await call_next(request)
    response.headers.update({"X-Request-ID":request.state.correlation_id,"Cache-Control":"no-store","X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"no-referrer","Permissions-Policy":"camera=(), microphone=(), geolocation=(), payment=()","Content-Security-Policy":"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"})
    return response

def audit_access(session,principal:Principal,action:str,payload:dict):
    append_ledger_event(session,"API_ACCESS",principal.subject,principal.subject,",".join(sorted(principal.roles)),action,{**payload,"tenant_id":principal.tenant_id,"purpose":principal.active_purpose,"token_id_hash":principal.token_id_hash},principal.correlation_id)

@app.get("/universe-coverage")
def universe_coverage_latest(principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"coverage:read",{"ADMIN"})
    if "*" not in principal.universes:raise HTTPException(status_code=403,detail="aggregate coverage requires all-universe scope")
    with SessionLocal() as s:
        run=s.scalar(select(UniverseCoverageRun).order_by(UniverseCoverageRun.id.desc()))
        if not run:raise HTTPException(status_code=404,detail="no coverage assessment is available")
        report=json.loads(run.report_json);audit_access(s,principal,"UNIVERSE_COVERAGE_READ",{"coverage_run_id":run.id,"report_hash":run.report_hash,"status":run.status});s.commit();return report

@app.get("/security-readiness")
def security_readiness_latest(principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"security:read",{"ADMIN"})
    if "*" not in principal.universes:raise HTTPException(status_code=403,detail="security readiness requires all-universe scope")
    with SessionLocal() as s:
        run=s.scalar(select(SecurityReadinessRun).order_by(SecurityReadinessRun.id.desc()))
        if not run:raise HTTPException(status_code=404,detail="no security readiness assessment is available")
        report=json.loads(run.report_json);audit_access(s,principal,"SECURITY_READINESS_READ",{"readiness_run_id":run.id,"report_hash":run.report_hash,"status":run.status});s.commit();return report

@app.post("/retention/legal-holds")
def legal_hold_proposal(body:LegalHoldProposalRequest,principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"retention:write",{"COUNSEL","ADMIN"})
    with SessionLocal() as s:
        try:hold=propose_class_legal_hold(s,body.data_class,principal.subject,body.reason)
        except RetentionError as exc:raise HTTPException(status_code=422,detail=str(exc))
        packet=build_legal_hold_packet(s,hold.id);audit_access(s,principal,"LEGAL_HOLD_PROPOSED",{"hold_id":hold.id,"scope_type":hold.scope_type,"scope_reference_hash":hold.scope_reference_hash});s.commit();return packet

@app.get("/retention/legal-holds")
def legal_hold_queue(status:str="PROPOSED",limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"retention:review",{"COUNSEL","ADMIN"})
    with SessionLocal() as s:
        rows=[build_legal_hold_packet(s,x.id) for x in s.scalars(select(LegalHold).where(LegalHold.status==status.upper()).order_by(LegalHold.id).limit(limit))];audit_access(s,principal,"LEGAL_HOLDS_LISTED",{"status":status.upper(),"limit":limit,"result_count":len(rows)});s.commit();return rows

@app.post("/retention/legal-holds/{hold_id}/actions")
def legal_hold_action(hold_id:int,body:LegalHoldActionRequest,principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"retention:approve",{"COUNSEL","ADMIN"})
    with SessionLocal() as s:
        try:hold=adjudicate_legal_hold(s,hold_id,body.action,principal.subject,body.rationale,body.expected_status)
        except RetentionError as exc:raise HTTPException(status_code=422,detail=str(exc))
        packet=build_legal_hold_packet(s,hold.id);audit_access(s,principal,"LEGAL_HOLD_ACTION",{"hold_id":hold.id,"action":body.action.upper(),"resulting_state":hold.status,"scope_reference_hash":hold.scope_reference_hash});s.commit();return packet

@app.get("/security/private-egress-reviews")
def private_egress_review_queue(status:str="OPEN",limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"security:review",{"ADMIN","COUNSEL"})
    with SessionLocal() as s:
        rows=[build_private_egress_packet(s,x.id) for x in s.scalars(select(PrivateEgressReviewCase).where(PrivateEgressReviewCase.status==status.upper()).order_by(PrivateEgressReviewCase.id).limit(limit))];audit_access(s,principal,"PRIVATE_EGRESS_REVIEWS_LISTED",{"status":status.upper(),"limit":limit,"result_count":len(rows)});s.commit();return rows

@app.post("/security/private-egress-reviews/{case_id}/actions")
def private_egress_review_action(case_id:int,body:PrivateEgressActionRequest,principal:Principal=Depends(authenticate_private_request)):
    approval=body.action.upper().startswith("APPROVE_");authorize(principal,"security:approve" if approval else "security:write",{"ADMIN","COUNSEL"})
    with SessionLocal() as s:
        try:case=adjudicate_private_egress(s,case_id,body.action,principal.subject,"COUNSEL" if "COUNSEL" in principal.roles else "ADMIN",body.rationale,body.expected_status)
        except PrivateEgressReviewError as exc:raise HTTPException(status_code=422,detail=str(exc))
        packet=build_private_egress_packet(s,case.id);audit_access(s,principal,"PRIVATE_EGRESS_REVIEW_ACTION",{"case_id":case.id,"action":body.action.upper(),"resulting_state":case.status,"evidence_package_hash":packet["evidence"]["evidence_package_hash"]});s.commit();return packet

@app.get("/identity-review")
def identity_review_queue(review_batch_id:int=Query(gt=0),resolution_state:Optional[str]=None,min_priority:int=Query(0,ge=0,le=100),limit:int=Query(50,ge=1,le=100),include_excerpt:bool=False,principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"identity:review",{"RESEARCHER","REVIEWER","ADMIN"})
    normalized_state=resolution_state.upper() if resolution_state else None
    if normalized_state and normalized_state not in {"PROBABLE_MATCH","POSSIBLE_MATCH","CONFLICT","REQUIRES_REVIEW"}:raise HTTPException(status_code=422,detail="unsupported resolution state")
    with SessionLocal() as s:
        reviewer_role=next((x for x in ("REVIEWER","RESEARCHER") if x in principal.roles),"UNKNOWN")
        try:batch_items=assigned_identity_batch_items(s,review_batch_id,principal.subject,reviewer_role)
        except IdentityReviewAssignmentError as exc:raise HTTPException(status_code=403,detail=str(exc))
        batch_packet=build_identity_batch_packet(s,review_batch_id);authorize(principal,"identity:review",{"RESEARCHER","REVIEWER","ADMIN"},batch_packet["criteria"]["universe"]);rows=[]
        for batch_item in batch_items:
            item=s.get(ReviewQueueItem,batch_item.queue_item_id);decision=s.get(ResolutionDecision,item.resolution_decision_id)
            if item.priority<min_priority or (normalized_state and decision.state!=normalized_state):continue
            packet=build_review_packet(s,item.id,include_excerpt=include_excerpt)
            if "*" in principal.universes or packet["universe"] in principal.universes:rows.append(packet)
            if len(rows)>=limit:break
        audit_access(s,principal,"IDENTITY_REVIEW_LISTED",{"review_batch_id":review_batch_id,"resolution_state":normalized_state,"min_priority":min_priority,"limit":limit,"result_count":len(rows),"include_excerpt":include_excerpt});s.commit();return rows

@app.post("/identity-review/batches")
def identity_review_batch_create(body:IdentityBatchRequest,principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"identity:review",{"REVIEWER","ADMIN"},body.universe)
    with SessionLocal() as s:
        try:batch=freeze_identity_batch(s,principal.subject,body.universe,body.status,body.queue_type,body.resolution_state,body.min_priority,body.limit)
        except IdentityReviewBatchError as exc:raise HTTPException(status_code=422,detail=str(exc))
        packet=build_identity_batch_packet(s,batch.id);audit_access(s,principal,"IDENTITY_REVIEW_BATCH_FROZEN",{"batch_id":batch.id,"universe":body.universe,"manifest_hash":batch.manifest_hash,"item_count":batch.item_count});s.commit();return packet

@app.get("/identity-review/batches/{batch_id}")
def identity_review_batch_detail(batch_id:int,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        try:packet=build_identity_batch_packet(s,batch_id)
        except IdentityReviewBatchError as exc:raise HTTPException(status_code=404,detail=str(exc))
        authorize(principal,"identity:review",{"RESEARCHER","REVIEWER","ADMIN"},packet["criteria"]["universe"]);audit_access(s,principal,"IDENTITY_REVIEW_BATCH_READ",{"batch_id":batch_id,"manifest_hash":packet["manifest_hash"],"manifest_valid":packet["manifest_valid"]});s.commit();return packet

@app.post("/identity-review/batches/{batch_id}/assignments")
def identity_review_assignment_create(batch_id:int,body:IdentityAssignmentRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        packet=build_identity_batch_packet(s,batch_id);authorize(principal,"identity:assign",{"ADMIN"},packet["criteria"]["universe"])
        try:assignment=assign_identity_reviewer(s,batch_id,body.reviewer,body.reviewer_role,principal.subject,body.rationale,body.expires_hours)
        except IdentityReviewAssignmentError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"IDENTITY_REVIEW_ASSIGNED",{"batch_id":batch_id,"assignment_id":assignment.id,"reviewer":assignment.reviewer,"reviewer_role":assignment.reviewer_role,"expires_at":assignment.expires_at.isoformat()});s.commit();return {"id":assignment.id,"batch_id":batch_id,"reviewer":assignment.reviewer,"reviewer_role":assignment.reviewer_role,"status":assignment.status,"expires_at":assignment.expires_at.isoformat()}

@app.post("/identity-review/assignments/{assignment_id}/revoke")
def identity_review_assignment_revoke(assignment_id:int,body:EvidenceLifecycleRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        from pmos_research.db import IdentityReviewAssignment
        assignment=s.get(IdentityReviewAssignment,assignment_id)
        if not assignment:raise HTTPException(status_code=404,detail="unknown identity review assignment")
        packet=build_identity_batch_packet(s,assignment.batch_id);authorize(principal,"identity:assign",{"ADMIN"},packet["criteria"]["universe"])
        try:assignment=revoke_identity_assignment(s,assignment_id,principal.subject,body.rationale)
        except IdentityReviewAssignmentError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"IDENTITY_REVIEW_ASSIGNMENT_REVOKED",{"assignment_id":assignment.id,"batch_id":assignment.batch_id});s.commit();return {"id":assignment.id,"status":assignment.status}

@app.post("/identity-review/batches/{batch_id}/close")
def identity_review_batch_close(batch_id:int,body:EvidenceLifecycleRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        packet=build_identity_batch_packet(s,batch_id);authorize(principal,"identity:assign",{"ADMIN"},packet["criteria"]["universe"])
        try:batch=close_identity_batch(s,batch_id,principal.subject,body.rationale)
        except IdentityReviewAssignmentError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"IDENTITY_REVIEW_BATCH_CLOSED",{"batch_id":batch.id});s.commit();return {"id":batch.id,"status":batch.status}

@app.post("/identity-review/{item_id}/actions")
def identity_review_action(item_id:int,body:IdentityActionRequest,principal:Principal=Depends(authenticate_private_request)):
    approval=body.action.upper()=="APPROVE_MATCH";permission="identity:approve" if approval else "identity:write";roles={"REVIEWER","ADMIN"} if approval else {"RESEARCHER","REVIEWER","ADMIN"}
    with SessionLocal() as s:
        packet=build_review_packet(s,item_id)
        authorize(principal,permission,roles,packet["universe"])
        reviewer_role=next((x for x in ("REVIEWER","RESEARCHER") if x in principal.roles),"UNKNOWN")
        try:result=adjudicate(s,item_id,body.action,principal.subject,reviewer_role,body.rationale,body.evidence_ids,body.expected_version,body.review_batch_id)
        except StaleReviewError as exc:raise HTTPException(status_code=409,detail=str(exc))
        except AdjudicationInputError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"IDENTITY_REVIEW_ACTION",{"item_id":item_id,"review_batch_id":body.review_batch_id,"action":body.action.upper(),"resulting_state":result["resulting_state"],"evidence_count":len(set(body.evidence_ids))});s.commit();return result

@app.get("/jurisdiction-review")
def jurisdiction_review_queue(status:str="HUMAN_REVIEW_REQUIRED",limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"identity:review",{"RESEARCHER","REVIEWER","ADMIN"})
    with SessionLocal() as s:
        cases=s.scalars(select(JurisdictionReviewCase).where(JurisdictionReviewCase.status==status.upper()).order_by(JurisdictionReviewCase.id).limit(limit*5)).all();rows=[]
        for case in cases:
            packet=build_jurisdiction_packet(s,case.id)
            if "*" in principal.universes or packet["entity"]["universe"] in principal.universes:rows.append(packet)
            if len(rows)>=limit:break
        audit_access(s,principal,"JURISDICTION_REVIEW_LISTED",{"status":status.upper(),"limit":limit,"result_count":len(rows)});s.commit();return rows

@app.post("/jurisdiction-review/{case_id}/actions")
def jurisdiction_review_action(case_id:int,body:JurisdictionActionRequest,principal:Principal=Depends(authenticate_private_request)):
    approval=body.action.upper()=="APPROVE_CORRECTION";permission="identity:approve" if approval else "identity:write";roles={"REVIEWER","ADMIN"} if approval else {"RESEARCHER","REVIEWER","ADMIN"}
    with SessionLocal() as s:
        packet=build_jurisdiction_packet(s,case_id);authorize(principal,permission,roles,packet["entity"]["universe"])
        try:case=adjudicate_jurisdiction(s,case_id,body.action,principal.subject,body.rationale,body.source_claim_id,body.expected_status)
        except JurisdictionReviewError as exc:raise HTTPException(status_code=422,detail=str(exc))
        result=build_jurisdiction_packet(s,case.id);audit_access(s,principal,"JURISDICTION_REVIEW_ACTION",{"case_id":case.id,"action":body.action.upper(),"resulting_state":case.status,"source_claim_id":case.source_claim_id});s.commit();return result

@app.post("/relationship-review")
def relationship_proposal(body:RelationshipProposalRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        source=s.get(Entity,body.from_entity_id);target=s.get(Entity,body.to_entity_id)
        if not source or not target:raise HTTPException(status_code=404,detail="relationship entity not found")
        authorize(principal,"relationships:write",{"RESEARCHER","REVIEWER","ADMIN"},source.universe);authorize(principal,"relationships:write",{"RESEARCHER","REVIEWER","ADMIN"},target.universe)
        try:assertion=propose_relationship(s,source.id,target.id,body.relation_type,principal.subject,body.evidence_passage_ids,body.jurisdiction)
        except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc))
        packet=build_relationship_packet(s,assertion.id);audit_access(s,principal,"RELATIONSHIP_PROPOSED",{"assertion_id":assertion.id,"relation_type":assertion.relation_type,"evidence_count":len(set(body.evidence_passage_ids))});s.commit();return packet

@app.post("/publisher-independence")
def publisher_independence_proposal(body:PublisherIndependenceProposalRequest,principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"evidence:write",{"RESEARCHER","REVIEWER","ADMIN"})
    with SessionLocal() as s:
        passages=s.scalars(select(EvidencePassage).where(EvidencePassage.id.in_(set(body.evidence_passage_ids)))).all();documents={x.id:s.get(SourceDocument,x.document_id) for x in passages}
        for document in documents.values():
            entity=s.get(Entity,document.entity_id) if document and document.entity_id else None
            if entity:authorize(principal,"evidence:write",{"RESEARCHER","REVIEWER","ADMIN"},entity.universe)
        try:assessment=propose_publisher_independence(s,body.source_domain,body.independence_group,principal.subject,body.rationale,body.evidence_passage_ids)
        except PublisherIndependenceError as exc:raise HTTPException(status_code=422,detail=str(exc))
        packet=build_publisher_independence_packet(s,assessment.id);audit_access(s,principal,"PUBLISHER_INDEPENDENCE_PROPOSED",{"assessment_id":assessment.id,"source_domain":assessment.source_domain,"evidence_count":len(set(body.evidence_passage_ids))});s.commit();return packet

@app.get("/publisher-independence")
def publisher_independence_queue(status:str="HUMAN_REVIEW_REQUIRED",limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"evidence:review",{"RESEARCHER","REVIEWER","ADMIN"})
    with SessionLocal() as s:
        rows=[]
        for assessment in s.scalars(select(PublisherIndependenceAssessment).where(PublisherIndependenceAssessment.status==status.upper()).order_by(PublisherIndependenceAssessment.id).limit(limit*10)):
            packet=build_publisher_independence_packet(s,assessment.id);universes=set()
            for item in packet["evidence"]:
                document=s.get(SourceDocument,item["document_id"]);entity=s.get(Entity,document.entity_id) if document and document.entity_id else None
                if entity:universes.add(entity.universe)
            if "*" not in principal.universes and not universes.issubset(principal.universes):continue
            rows.append(packet)
            if len(rows)>=limit:break
        audit_access(s,principal,"PUBLISHER_INDEPENDENCE_LISTED",{"status":status.upper(),"limit":limit,"result_count":len(rows)});s.commit();return rows

@app.post("/publisher-independence/{assessment_id}/actions")
def publisher_independence_action(assessment_id:int,body:PublisherIndependenceActionRequest,principal:Principal=Depends(authenticate_private_request)):
    approval=body.action.upper()=="APPROVE";permission="evidence:approve" if approval else "evidence:write";roles={"REVIEWER","ADMIN"} if approval else {"RESEARCHER","REVIEWER","ADMIN"}
    with SessionLocal() as s:
        packet=build_publisher_independence_packet(s,assessment_id)
        for item in packet["evidence"]:
            document=s.get(SourceDocument,item["document_id"]);entity=s.get(Entity,document.entity_id) if document and document.entity_id else None
            if entity:authorize(principal,permission,roles,entity.universe)
        authorize(principal,permission,roles)
        try:assessment=adjudicate_publisher_independence(s,assessment_id,body.action,principal.subject,body.rationale,body.expected_status)
        except PublisherIndependenceError as exc:raise HTTPException(status_code=422,detail=str(exc))
        result=build_publisher_independence_packet(s,assessment.id);audit_access(s,principal,"PUBLISHER_INDEPENDENCE_ACTION",{"assessment_id":assessment.id,"action":body.action.upper(),"resulting_state":assessment.status});s.commit();return result

@app.get("/relationship-candidates")
def relationship_candidate_queue(status:str="HUMAN_REVIEW_REQUIRED",limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"relationships:review",{"RESEARCHER","REVIEWER","ADMIN"})
    with SessionLocal() as s:
        rows=[]
        for candidate in s.scalars(select(RelationshipResearchCandidate).where(RelationshipResearchCandidate.status==status.upper()).order_by(RelationshipResearchCandidate.confidence.desc(),RelationshipResearchCandidate.id).limit(limit*10)):
            packet=build_relationship_candidate_packet(s,candidate.id);universes={packet["source_entity"]["universe"],packet["target_entity"]["universe"]}
            if "*" not in principal.universes and not universes.issubset(principal.universes):continue
            rows.append(packet)
            if len(rows)>=limit:break
        audit_access(s,principal,"RELATIONSHIP_CANDIDATES_LISTED",{"status":status.upper(),"limit":limit,"result_count":len(rows)});s.commit();return rows

@app.get("/relationship-mentions")
def relationship_mention_queue(review_batch_id:int=Query(gt=0),limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"relationships:review",{"RESEARCHER","REVIEWER","ADMIN"})
    with SessionLocal() as s:
        reviewer_role=next((x for x in ("REVIEWER","RESEARCHER") if x in principal.roles),"UNKNOWN")
        try:batch_items=assigned_mention_batch_items(s,review_batch_id,principal.subject,reviewer_role)
        except RelationshipMentionReviewError as exc:raise HTTPException(status_code=403,detail=str(exc))
        batch_packet=build_mention_review_batch_packet(s,review_batch_id);authorize(principal,"relationships:review",{"RESEARCHER","REVIEWER","ADMIN"},batch_packet["criteria"]["universe"]);rows=[]
        for item in batch_items[:limit]:
            mention=s.get(RelationshipMentionCandidate,item.mention_candidate_id)
            packet=build_relationship_mention_packet(s,mention.id)
            if "*" in principal.universes or packet["source_entity"]["universe"] in principal.universes:rows.append(packet)
        audit_access(s,principal,"RELATIONSHIP_MENTIONS_LISTED",{"review_batch_id":review_batch_id,"limit":limit,"result_count":len(rows)});s.commit();return rows

@app.post("/relationship-mentions/batches")
def relationship_mention_batch_create(body:RelationshipMentionBatchRequest,principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"identity:review",{"REVIEWER","ADMIN"},body.universe)
    with SessionLocal() as s:
        try:batch=freeze_mention_review_batch(s,principal.subject,body.universe,body.status,body.limit)
        except RelationshipMentionReviewError as exc:raise HTTPException(status_code=422,detail=str(exc))
        packet=build_mention_review_batch_packet(s,batch.id);audit_access(s,principal,"RELATIONSHIP_MENTION_BATCH_FROZEN",{"batch_id":batch.id,"universe":body.universe,"manifest_hash":batch.manifest_hash,"item_count":batch.item_count});s.commit();return packet

@app.get("/relationship-mentions/batches/{batch_id}")
def relationship_mention_batch_detail(batch_id:int,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        try:packet=build_mention_review_batch_packet(s,batch_id)
        except RelationshipMentionReviewError as exc:raise HTTPException(status_code=404,detail=str(exc))
        authorize(principal,"identity:review",{"RESEARCHER","REVIEWER","ADMIN"},packet["criteria"]["universe"]);audit_access(s,principal,"RELATIONSHIP_MENTION_BATCH_READ",{"batch_id":batch_id,"manifest_hash":packet["manifest_hash"],"manifest_valid":packet["manifest_valid"]});s.commit();return packet

@app.post("/relationship-mentions/batches/{batch_id}/assignments")
def relationship_mention_assignment_create(batch_id:int,body:IdentityAssignmentRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        packet=build_mention_review_batch_packet(s,batch_id);authorize(principal,"identity:assign",{"ADMIN"},packet["criteria"]["universe"])
        try:assignment=assign_mention_reviewer(s,batch_id,body.reviewer,body.reviewer_role,principal.subject,body.rationale,body.expires_hours)
        except RelationshipMentionReviewError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"RELATIONSHIP_MENTION_ASSIGNED",{"batch_id":batch_id,"assignment_id":assignment.id,"reviewer":assignment.reviewer,"reviewer_role":assignment.reviewer_role,"expires_at":assignment.expires_at.isoformat()});s.commit();return {"id":assignment.id,"batch_id":batch_id,"reviewer":assignment.reviewer,"reviewer_role":assignment.reviewer_role,"status":assignment.status,"expires_at":assignment.expires_at.isoformat()}

@app.post("/relationship-mentions/assignments/{assignment_id}/revoke")
def relationship_mention_assignment_revoke(assignment_id:int,body:EvidenceLifecycleRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        assignment=s.get(RelationshipMentionReviewAssignment,assignment_id)
        if not assignment:raise HTTPException(status_code=404,detail="unknown mention review assignment")
        packet=build_mention_review_batch_packet(s,assignment.batch_id);authorize(principal,"identity:assign",{"ADMIN"},packet["criteria"]["universe"])
        try:assignment=revoke_mention_assignment(s,assignment_id,principal.subject,body.rationale)
        except RelationshipMentionReviewError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"RELATIONSHIP_MENTION_ASSIGNMENT_REVOKED",{"assignment_id":assignment.id,"batch_id":assignment.batch_id});s.commit();return {"id":assignment.id,"status":assignment.status}

@app.post("/relationship-mentions/batches/{batch_id}/close")
def relationship_mention_batch_close(batch_id:int,body:EvidenceLifecycleRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        packet=build_mention_review_batch_packet(s,batch_id);authorize(principal,"identity:assign",{"ADMIN"},packet["criteria"]["universe"])
        try:batch=close_mention_review_batch(s,batch_id,principal.subject,body.rationale)
        except RelationshipMentionReviewError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"RELATIONSHIP_MENTION_BATCH_CLOSED",{"batch_id":batch.id});s.commit();return {"id":batch.id,"status":batch.status}

@app.post("/relationship-mentions/{mention_id}/actions")
def relationship_mention_action(mention_id:int,body:RelationshipMentionActionRequest,principal:Principal=Depends(authenticate_private_request)):
    approval=body.action.upper() in {"APPROVE_TARGET","REJECT_TARGET"};permission="identity:approve" if approval else "identity:write";roles={"REVIEWER","ADMIN"} if approval else {"RESEARCHER","REVIEWER","ADMIN"}
    with SessionLocal() as s:
        packet=build_relationship_mention_packet(s,mention_id);authorize(principal,permission,roles,packet["source_entity"]["universe"])
        if body.target_entity_id:
            target=s.get(Entity,body.target_entity_id)
            if not target:raise HTTPException(status_code=404,detail="target entity not found")
            authorize(principal,permission,roles,target.universe)
        elif packet.get("resolution") and packet["resolution"].get("target_entity"):authorize(principal,permission,roles,packet["resolution"]["target_entity"]["universe"])
        reviewer_role=next((x for x in ("REVIEWER","RESEARCHER") if x in principal.roles),"UNKNOWN")
        try:mention=adjudicate_relationship_mention(s,mention_id,body.action,principal.subject,body.rationale,body.expected_status,body.target_entity_id,body.review_batch_id,reviewer_role)
        except RelationshipResearchError as exc:raise HTTPException(status_code=422,detail=str(exc))
        result=build_relationship_mention_packet(s,mention.id);audit_access(s,principal,"RELATIONSHIP_MENTION_ACTION",{"mention_id":mention.id,"review_batch_id":body.review_batch_id,"action":body.action.upper(),"resulting_state":mention.status,"resolved_entity_id":mention.resolved_entity_id,"resulting_candidate_id":mention.resulting_candidate_id});s.commit();return result

@app.post("/relationship-candidates/{candidate_id}/actions")
def relationship_candidate_action(candidate_id:int,body:RelationshipCandidateActionRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        packet=build_relationship_candidate_packet(s,candidate_id);authorize(principal,"relationships:write",{"RESEARCHER","REVIEWER","ADMIN"},packet["source_entity"]["universe"]);authorize(principal,"relationships:write",{"RESEARCHER","REVIEWER","ADMIN"},packet["target_entity"]["universe"])
        try:candidate=adjudicate_relationship_candidate(s,candidate_id,body.action,principal.subject,body.rationale,body.expected_status)
        except RelationshipResearchError as exc:raise HTTPException(status_code=422,detail=str(exc))
        result=build_relationship_candidate_packet(s,candidate.id);audit_access(s,principal,"RELATIONSHIP_CANDIDATE_ACTION",{"candidate_id":candidate.id,"action":body.action.upper(),"resulting_state":candidate.status,"resulting_assertion_id":candidate.resulting_assertion_id});s.commit();return result

@app.get("/relationship-review")
def relationship_review_queue(status:str="HUMAN_REVIEW_REQUIRED",relation_type:Optional[str]=None,sensitive:Optional[bool]=None,min_confidence:float=Query(0,ge=0,le=1),limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"relationships:review",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"})
    with SessionLocal() as s:
        query=s.query(RelationshipAssertion).filter(RelationshipAssertion.status==status.upper())
        if relation_type:query=query.filter(RelationshipAssertion.relation_type==relation_type.upper())
        if sensitive is not None:query=query.filter(RelationshipAssertion.sensitive.is_(sensitive))
        rows=[]
        for assertion in query.order_by(RelationshipAssertion.created_at,RelationshipAssertion.id).limit(limit*10):
            packet=build_relationship_packet(s,assertion.id);universes={packet["source_entity"]["universe"],packet["target_entity"]["universe"]}
            if "*" not in principal.universes and not universes.issubset(principal.universes):continue
            if packet["evidence_controls"]["evidence_confidence"]<min_confidence:continue
            rows.append(packet)
            if len(rows)>=limit:break
        audit_access(s,principal,"RELATIONSHIP_REVIEW_LISTED",{"status":status.upper(),"relation_type":relation_type.upper() if relation_type else None,"sensitive":sensitive,"min_confidence":min_confidence,"limit":limit,"result_count":len(rows)});s.commit();return rows

@app.post("/relationship-review/{assertion_id}/actions")
def relationship_review_action(assertion_id:int,body:RelationshipActionRequest,principal:Principal=Depends(authenticate_private_request)):
    approval=body.action.upper()=="APPROVE";permission="relationships:approve" if approval else "relationships:write";roles={"REVIEWER","COUNSEL","ADMIN"} if approval else {"RESEARCHER","REVIEWER","COUNSEL","ADMIN"}
    with SessionLocal() as s:
        packet=build_relationship_packet(s,assertion_id);authorize(principal,permission,roles,packet["source_entity"]["universe"]);authorize(principal,permission,roles,packet["target_entity"]["universe"])
        try:assertion=adjudicate_relationship(s,assertion_id,body.action,principal.subject,body.rationale,body.expected_status)
        except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc))
        result=build_relationship_packet(s,assertion.id);audit_access(s,principal,"RELATIONSHIP_REVIEW_ACTION",{"assertion_id":assertion.id,"action":body.action.upper(),"resulting_state":assertion.status});s.commit();return result

@app.post("/private-sales")
def private_sale_create(body:PrivateSaleCreateRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        asset=s.get(Entity,body.asset_entity_id);seller=s.get(Entity,body.seller_entity_id) if body.seller_entity_id else None
        if not asset or (body.seller_entity_id and not seller):raise HTTPException(status_code=404,detail="private-sale entity not found")
        authorize(principal,"private_sales:write",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"},asset.universe,body.permitted_use)
        if seller:authorize(principal,"private_sales:write",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"},seller.universe,body.permitted_use)
        try:case=open_private_sale(s,asset.id,seller.id if seller else None,body.purpose,body.permitted_use,principal.subject,body.jurisdiction)
        except PrivateSaleError as exc:raise HTTPException(status_code=422,detail=str(exc))
        packet=build_private_sale_packet(s,case.id);audit_access(s,principal,"PRIVATE_SALE_OPENED",{"case_id":case.id,"asset_entity_id":asset.id,"seller_entity_id":seller.id if seller else None});s.commit();return packet

@app.get("/private-sales/{case_id}")
def private_sale_detail(case_id:int,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        packet=build_private_sale_packet(s,case_id);authorize(principal,"private_sales:read",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"},packet["asset"]["universe"],packet["permitted_use"])
        if packet["seller"]:authorize(principal,"private_sales:read",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"},packet["seller"]["universe"],packet["permitted_use"])
        audit_access(s,principal,"PRIVATE_SALE_READ",{"case_id":case_id});s.commit();return packet

@app.post("/private-sales/{case_id}/gates/{gate_id}/evidence")
def private_sale_gate_evidence(case_id:int,gate_id:int,body:PrivateSaleEvidenceRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        packet=build_private_sale_packet(s,case_id);gate=s.get(PrivateSaleGate,gate_id)
        if not gate or gate.case_id!=case_id:raise HTTPException(status_code=404,detail="private-sale gate not found")
        authorize(principal,"private_sales:write",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"},packet["asset"]["universe"],packet["permitted_use"])
        if packet["seller"]:authorize(principal,"private_sales:write",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"},packet["seller"]["universe"],packet["permitted_use"])
        try:submit_gate_evidence(s,gate.id,body.claim_ids,principal.subject)
        except PrivateSaleError as exc:raise HTTPException(status_code=422,detail=str(exc))
        result=build_private_sale_packet(s,case_id);audit_access(s,principal,"PRIVATE_SALE_GATE_EVIDENCE",{"case_id":case_id,"gate_id":gate_id,"claim_count":len(set(body.claim_ids))});s.commit();return result

@app.post("/private-sales/{case_id}/gates/{gate_id}/actions")
def private_sale_gate_action(case_id:int,gate_id:int,body:PrivateSaleGateActionRequest,principal:Principal=Depends(authenticate_private_request)):
    approval=body.action.upper() in {"APPROVE","APPROVE_EXCEPTION"};permission="private_sales:approve" if approval else "private_sales:write";roles={"REVIEWER","COUNSEL","ADMIN"} if approval else {"RESEARCHER","REVIEWER","COUNSEL","ADMIN"}
    with SessionLocal() as s:
        packet=build_private_sale_packet(s,case_id);gate=s.get(PrivateSaleGate,gate_id)
        if not gate or gate.case_id!=case_id:raise HTTPException(status_code=404,detail="private-sale gate not found")
        authorize(principal,permission,roles,packet["asset"]["universe"],packet["permitted_use"])
        if packet["seller"]:authorize(principal,permission,roles,packet["seller"]["universe"],packet["permitted_use"])
        actor_role=next((x for x in ("ADMIN","COUNSEL","REVIEWER","RESEARCHER") if x in principal.roles),"UNKNOWN")
        try:adjudicate_gate(s,gate.id,body.action,principal.subject,actor_role,body.rationale,body.expected_status)
        except PrivateSaleError as exc:raise HTTPException(status_code=422,detail=str(exc))
        result=build_private_sale_packet(s,case_id);audit_access(s,principal,"PRIVATE_SALE_GATE_ACTION",{"case_id":case_id,"gate_id":gate_id,"action":body.action.upper(),"resulting_state":gate.status});s.commit();return result

@app.get("/evidence-review/passages")
def passage_review_queue(review_batch_id:int=Query(gt=0),predicate:Optional[str]=None,min_confidence:float=Query(0,ge=0,le=1),evidence_state:Optional[str]=None,limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"evidence:review",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"})
    normalized_state=evidence_state.upper() if evidence_state else None
    if normalized_state and normalized_state not in {"ELIGIBLE","BLOCKED","STALE","CONFLICT"}:raise HTTPException(status_code=422,detail="unsupported evidence state")
    with SessionLocal() as s:
        reviewer_role=next((x for x in ("COUNSEL","REVIEWER","RESEARCHER") if x in principal.roles),"UNKNOWN")
        try:batch_items=assigned_evidence_batch_items(s,review_batch_id,principal.subject,reviewer_role)
        except EvidenceReviewAssignmentError as exc:raise HTTPException(status_code=403,detail=str(exc))
        batch_packet=build_batch_packet(s,review_batch_id);authorize(principal,"evidence:review",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"},batch_packet["criteria"]["universe"]);rows=[]
        for batch_item in batch_items:
            candidate=s.get(ResearchPassageCandidate,batch_item.passage_candidate_id)
            if candidate.confidence<min_confidence or (predicate and candidate.predicate!=predicate.casefold()):continue
            packet=build_passage_packet(s,candidate.id)
            controls=packet["evidence_controls"]
            state_matches=not normalized_state or (normalized_state=="ELIGIBLE" and controls["support_eligible"]) or (normalized_state=="BLOCKED" and not controls["evidence_eligible"]) or (normalized_state=="STALE" and controls["freshness"]["state"]=="STALE") or (normalized_state=="CONFLICT" and controls["material_open_conflict"])
            if not state_matches:continue
            if "*" in principal.universes or packet["universe"] in principal.universes:rows.append(packet)
            if len(rows)>=limit:break
        audit_access(s,principal,"PASSAGE_REVIEW_LISTED",{"review_batch_id":review_batch_id,"predicate":predicate.casefold() if predicate else None,"min_confidence":min_confidence,"evidence_state":normalized_state,"limit":limit,"result_count":len(rows)});s.commit();return rows

@app.post("/evidence-review/batches")
def evidence_review_batch_create(body:EvidenceBatchRequest,principal:Principal=Depends(authenticate_private_request)):
    authorize(principal,"evidence:review",{"REVIEWER","COUNSEL","ADMIN"},body.universe)
    with SessionLocal() as s:
        try:batch=freeze_review_batch(s,principal.subject,body.universe,body.status,body.predicate,body.min_confidence,body.limit)
        except EvidenceReviewBatchError as exc:raise HTTPException(status_code=422,detail=str(exc))
        packet=build_batch_packet(s,batch.id);audit_access(s,principal,"EVIDENCE_REVIEW_BATCH_FROZEN",{"batch_id":batch.id,"universe":body.universe,"manifest_hash":batch.manifest_hash,"item_count":batch.item_count});s.commit();return packet

@app.get("/evidence-review/batches/{batch_id}")
def evidence_review_batch_detail(batch_id:int,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        try:packet=build_batch_packet(s,batch_id)
        except EvidenceReviewBatchError as exc:raise HTTPException(status_code=404,detail=str(exc))
        authorize(principal,"evidence:review",{"RESEARCHER","REVIEWER","COUNSEL","ADMIN"},packet["criteria"]["universe"]);audit_access(s,principal,"EVIDENCE_REVIEW_BATCH_READ",{"batch_id":batch_id,"manifest_hash":packet["manifest_hash"],"manifest_valid":packet["manifest_valid"]});s.commit();return packet

@app.post("/evidence-review/batches/{batch_id}/assignments")
def evidence_review_assignment_create(batch_id:int,body:EvidenceAssignmentRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        packet=build_batch_packet(s,batch_id);authorize(principal,"evidence:assign",{"ADMIN"},packet["criteria"]["universe"])
        try:assignment=assign_reviewer(s,batch_id,body.reviewer,body.reviewer_role,principal.subject,body.rationale,body.expires_hours)
        except EvidenceReviewAssignmentError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"EVIDENCE_REVIEW_ASSIGNED",{"batch_id":batch_id,"assignment_id":assignment.id,"reviewer":assignment.reviewer,"reviewer_role":assignment.reviewer_role,"expires_at":assignment.expires_at.isoformat()});s.commit();return {"id":assignment.id,"batch_id":batch_id,"reviewer":assignment.reviewer,"reviewer_role":assignment.reviewer_role,"status":assignment.status,"expires_at":assignment.expires_at.isoformat()}

@app.post("/evidence-review/assignments/{assignment_id}/revoke")
def evidence_review_assignment_revoke(assignment_id:int,body:EvidenceLifecycleRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        from pmos_research.db import EvidenceReviewAssignment
        assignment=s.get(EvidenceReviewAssignment,assignment_id)
        if not assignment:raise HTTPException(status_code=404,detail="unknown evidence review assignment")
        packet=build_batch_packet(s,assignment.batch_id);authorize(principal,"evidence:assign",{"ADMIN"},packet["criteria"]["universe"])
        try:assignment=revoke_assignment(s,assignment_id,principal.subject,body.rationale)
        except EvidenceReviewAssignmentError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"EVIDENCE_REVIEW_ASSIGNMENT_REVOKED",{"assignment_id":assignment.id,"batch_id":assignment.batch_id});s.commit();return {"id":assignment.id,"status":assignment.status}

@app.post("/evidence-review/batches/{batch_id}/close")
def evidence_review_batch_close(batch_id:int,body:EvidenceLifecycleRequest,principal:Principal=Depends(authenticate_private_request)):
    with SessionLocal() as s:
        packet=build_batch_packet(s,batch_id);authorize(principal,"evidence:assign",{"ADMIN"},packet["criteria"]["universe"])
        try:batch=close_batch(s,batch_id,principal.subject,body.rationale)
        except EvidenceReviewAssignmentError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"EVIDENCE_REVIEW_BATCH_CLOSED",{"batch_id":batch.id});s.commit();return {"id":batch.id,"status":batch.status}

@app.post("/evidence-review/passages/{candidate_id}/actions")
def passage_review_action(candidate_id:int,body:PassageActionRequest,principal:Principal=Depends(authenticate_private_request)):
    approval=body.action.upper()=="APPROVE_SUPPORT";permission="evidence:approve" if approval else "evidence:write";roles={"REVIEWER","COUNSEL","ADMIN"} if approval else {"RESEARCHER","REVIEWER","COUNSEL","ADMIN"}
    with SessionLocal() as s:
        packet=build_passage_packet(s,candidate_id);authorize(principal,permission,roles,packet["universe"])
        reviewer_role=next((x for x in ("COUNSEL","REVIEWER","RESEARCHER") if x in principal.roles),"UNKNOWN")
        try:result=adjudicate_passage(s,candidate_id,body.action,principal.subject,reviewer_role,body.rationale,body.claim_value,body.expected_status,body.review_batch_id)
        except PassageAdjudicationError as exc:raise HTTPException(status_code=422,detail=str(exc))
        audit_access(s,principal,"PASSAGE_REVIEW_ACTION",{"candidate_id":candidate_id,"review_batch_id":body.review_batch_id,"action":body.action.upper(),"resulting_state":result["resulting_state"],"claim_created":bool(result["claim_id"])});s.commit();return result

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
