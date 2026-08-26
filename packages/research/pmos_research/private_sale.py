from __future__ import annotations

import hashlib,json
from datetime import datetime,timezone
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import Claim,ClaimEvidence,Entity,EvidencePassage,PrivateSaleCase,PrivateSaleGate,PrivateSaleGateEvent,PrivateSaleGateEvidence,SourceDocument
from .publisher_independence import evaluate_document_independence

QUALIFYING_CLAIMS={"SUPPORTED","CORROBORATED","SPECIALIST_VERIFIED"}
GATES=(
    ("seller_identity","legal_identity",True,False),("authority_to_sell","authority_to_transact",True,False),
    ("provenance","provenance",True,False),("attribution","attribution",True,False),
    ("restitution","restitution_review",True,True),("cultural_property","cultural_property_review",True,True),
    ("export","export_review",True,True),("sanctions","sanctions",True,False),("condition","condition",False,False),
)
S0_ONLY={"authority_to_sell","export","sanctions"};TWO_SOURCE={"provenance","attribution","restitution","cultural_property"}
FRESHNESS={"seller_identity":365,"authority_to_sell":30,"provenance":365,"attribution":365,"restitution":90,"cultural_property":90,"export":30,"sanctions":1,"condition":90}

class PrivateSaleError(ValueError):pass

def _utc(value):return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def open_private_sale(session,asset_entity_id:int,seller_entity_id:int|None,purpose:str,permitted_use:str,owner:str,jurisdiction:str|None=None)->PrivateSaleCase:
    asset=session.get(Entity,asset_entity_id);seller=session.get(Entity,seller_entity_id) if seller_entity_id else None
    if not asset:raise PrivateSaleError("asset entity does not exist")
    if seller_entity_id and not seller:raise PrivateSaleError("seller entity does not exist")
    if len(purpose.strip())<3 or len(permitted_use.strip())<3 or not owner.strip():raise PrivateSaleError("purpose, permitted use, and owner are required")
    case=PrivateSaleCase(asset_entity_id=asset.id,seller_entity_id=seller.id if seller else None,purpose=purpose.strip(),permitted_use=permitted_use.strip(),jurisdiction=jurisdiction,owner=owner.strip());session.add(case);session.flush()
    for code,fact,critical,counsel in GATES:session.add(PrivateSaleGate(case_id=case.id,gate_code=code,fact_class=fact,critical=critical,counsel_required=counsel))
    append_ledger_event(session,"PRIVATE_SALE_CASE",case.id,owner,"CASE_OWNER","CASE_OPENED",{"asset_entity_id":asset.id,"seller_entity_id":seller.id if seller else None,"jurisdiction":jurisdiction,"gate_codes":[x[0] for x in GATES]});session.flush();return case

def _claim_documents(session,claim:Claim):
    return session.execute(select(ClaimEvidence,EvidencePassage,SourceDocument).join(EvidencePassage,ClaimEvidence.passage_id==EvidencePassage.id).join(SourceDocument,EvidencePassage.document_id==SourceDocument.id).where(ClaimEvidence.claim_id==claim.id,ClaimEvidence.supports.is_(True))).all()

def _valid_claim(session,claim:Claim)->bool:
    if claim.verification_status not in QUALIFYING_CLAIMS:return False
    for _,passage,document in _claim_documents(session,claim):
        if claim.entity_id==document.entity_id and claim.evidence_hash==document.content_hash and hashlib.sha256(passage.passage.encode()).hexdigest()==passage.passage_hash:return True
    return False

def submit_gate_evidence(session,gate_id:int,claim_ids,actor:str)->PrivateSaleGate:
    gate=session.get(PrivateSaleGate,gate_id);case=session.get(PrivateSaleCase,gate.case_id) if gate else None
    if not gate or not case:raise PrivateSaleError("unknown private-sale gate")
    if gate.status not in {"NOT_STARTED","EVIDENCE_COLLECTED"}:raise PrivateSaleError("gate is not accepting evidence")
    ids=sorted(set(int(x) for x in claim_ids));claims=session.scalars(select(Claim).where(Claim.id.in_(ids))).all() if ids else []
    if not claims or len(claims)!=len(ids):raise PrivateSaleError("all claim IDs must exist")
    expected_entity=case.seller_entity_id if gate.gate_code in {"seller_identity","authority_to_sell","sanctions"} else case.asset_entity_id
    if not expected_entity:raise PrivateSaleError("seller-scoped gate requires a seller entity")
    if any(x.entity_id!=expected_entity or x.field!=gate.fact_class or not _valid_claim(session,x) for x in claims):raise PrivateSaleError("claims must match the gate entity/fact class and contain valid exact evidence")
    existing=set(session.scalars(select(PrivateSaleGateEvidence.claim_id).where(PrivateSaleGateEvidence.gate_id==gate.id)).all())
    for claim_id in ids:
        if claim_id not in existing:session.add(PrivateSaleGateEvidence(gate_id=gate.id,claim_id=claim_id,added_by=actor))
    prior=gate.status;gate.status="EVIDENCE_COLLECTED";append_ledger_event(session,"PRIVATE_SALE_GATE",gate.id,actor,"RESEARCHER","EVIDENCE_ATTACHED",{"prior_state":prior,"resulting_state":gate.status,"claim_ids":ids});session.flush();return gate

def gate_sufficiency(session,gate_id:int)->dict:
    gate=session.get(PrivateSaleGate,gate_id)
    if not gate:raise PrivateSaleError("unknown private-sale gate")
    claims=session.scalars(select(Claim).join(PrivateSaleGateEvidence,PrivateSaleGateEvidence.claim_id==Claim.id).where(PrivateSaleGateEvidence.gate_id==gate.id).order_by(Claim.id)).all();documents=[];stale=0;now=datetime.now(timezone.utc);package_parts=[]
    for claim in claims:
        observed=_utc(claim.last_seen or claim.retrieved_at or claim.observed_at);stale+=max(0,(now-observed).days)>FRESHNESS[gate.gate_code]
        for _,passage,document in _claim_documents(session,claim):
            if hashlib.sha256(passage.passage.encode()).hexdigest()==passage.passage_hash and claim.evidence_hash==document.content_hash:documents.append(document);package_parts.append(f"{claim.id}:{claim.value}:{document.id}:{document.content_hash}:{passage.id}:{passage.passage_hash}")
    source_controls=evaluate_document_independence(session,documents,frozenset({"S0","S1","S2"}));ranks=set(source_controls["source_ranks"]);groups=set(source_controls["approved_independence_groups"])
    values={" ".join(x.value.casefold().split()) for x in claims}
    if gate.gate_code in S0_ONLY:sufficient="S0" in ranks
    elif gate.gate_code in TWO_SOURCE:sufficient="S0" in ranks or (len(groups)>=2 and bool(ranks & {"S1","S2"}))
    else:sufficient=bool(ranks & {"S0","S1","S2"})
    return {"sufficient":bool(claims) and len(values)==1 and stale==0 and sufficient,"claim_count":len(claims),"distinct_value_count":len(values),"source_ranks":sorted(ranks),"independence_groups":sorted(groups),"independence_group_count":len(groups),"unreviewed_publisher_count":source_controls["unreviewed_publisher_count"],"duplicate_content_count":source_controls["duplicate_content_count"],"source_factors":source_controls["factors"],"stale_claim_count":stale,"freshness_threshold_days":FRESHNESS[gate.gate_code],"evidence_package_hash":hashlib.sha256("|".join(sorted(package_parts)).encode()).hexdigest()}

def adjudicate_gate(session,gate_id:int,action:str,actor:str,actor_role:str,rationale:str,expected_status:str|None=None)->PrivateSaleGate:
    gate=session.get(PrivateSaleGate,gate_id)
    if not gate:raise PrivateSaleError("unknown private-sale gate")
    if expected_status is not None and gate.status!=expected_status:raise PrivateSaleError("gate changed; reload before deciding")
    if len(rationale.strip())<10:raise PrivateSaleError("substantive rationale is required")
    action=action.upper();transitions={"EVIDENCE_COLLECTED":{"PROPOSE_PASS":"REVIEW_PROPOSED","PROPOSE_EXCEPTION":"EXCEPTION_PROPOSED","MARK_BLOCKED":"BLOCKED"},"REVIEW_PROPOSED":{"APPROVE":"PASS","REJECT":"EVIDENCE_COLLECTED"},"EXCEPTION_PROPOSED":{"APPROVE_EXCEPTION":"PASS_WITH_EXCEPTION","REJECT":"EVIDENCE_COLLECTED"}}
    if action not in transitions.get(gate.status,{}):raise PrivateSaleError(f"invalid transition {gate.status} -> {action}")
    sufficiency=gate_sufficiency(session,gate.id)
    if action=="PROPOSE_PASS" and not sufficiency["sufficient"]:raise PrivateSaleError("gate evidence is insufficient")
    events=session.scalars(select(PrivateSaleGateEvent).where(PrivateSaleGateEvent.gate_id==gate.id).order_by(PrivateSaleGateEvent.id)).all()
    if action in {"APPROVE","APPROVE_EXCEPTION"}:
        proposal_action="PROPOSE_PASS" if action=="APPROVE" else "PROPOSE_EXCEPTION";proposal=next((x for x in reversed(events) if x.action==proposal_action),None)
        if not proposal or proposal.actor==actor:raise PrivateSaleError("independent maker-checker approval is required")
        if proposal.evidence_package_hash!=sufficiency["evidence_package_hash"]:raise PrivateSaleError("gate evidence package changed after proposal")
        if gate.counsel_required and actor_role.upper() not in {"COUNSEL","ADMIN"}:raise PrivateSaleError("counsel approval is required for this gate")
        if action=="APPROVE" and not sufficiency["sufficient"]:raise PrivateSaleError("gate evidence became insufficient")
    prior=gate.status;result=transitions[prior][action];gate.status=result;gate.completed_at=datetime.now(timezone.utc) if result in {"PASS","PASS_WITH_EXCEPTION","BLOCKED"} else None;gate.exception_reason=rationale.strip() if result=="PASS_WITH_EXCEPTION" else None
    session.add(PrivateSaleGateEvent(gate_id=gate.id,action=action,prior_state=prior,resulting_state=result,actor=actor,actor_role=actor_role.upper(),rationale=rationale.strip(),evidence_package_hash=sufficiency["evidence_package_hash"]));append_ledger_event(session,"PRIVATE_SALE_GATE",gate.id,actor,actor_role.upper(),action,{"prior_state":prior,"resulting_state":result,"sufficiency":sufficiency,"rationale":rationale.strip()});session.flush();return gate

def private_sale_readiness(session,case_id:int)->dict:
    case=session.get(PrivateSaleCase,case_id)
    if not case:raise PrivateSaleError("unknown private-sale case")
    gates=session.scalars(select(PrivateSaleGate).where(PrivateSaleGate.case_id==case.id).order_by(PrivateSaleGate.id)).all();missing=[x.gate_code for x in gates if x.status not in {"PASS","PASS_WITH_EXCEPTION"}];blocked=[x.gate_code for x in gates if x.status=="BLOCKED"];exceptions=[x.gate_code for x in gates if x.status=="PASS_WITH_EXCEPTION"];critical_missing=[x.gate_code for x in gates if x.critical and x.status!="PASS"]
    state="RED" if blocked or critical_missing else "AMBER" if missing or exceptions else "GREEN"
    return {"state":state,"missing_gates":missing,"blocked_gates":blocked,"exceptions":exceptions,"critical_not_clear":critical_missing}
