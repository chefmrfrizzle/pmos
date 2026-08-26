from __future__ import annotations

from sqlalchemy import select

from .db import Entity,PrivateSaleCase,PrivateSaleGate,PrivateSaleGateEvent,PrivateSaleGateEvidence
from .private_sale import gate_sufficiency,private_sale_readiness

def build_private_sale_packet(session,case_id:int)->dict:
    case=session.get(PrivateSaleCase,case_id)
    if not case:raise ValueError("unknown private-sale case")
    asset=session.get(Entity,case.asset_entity_id);seller=session.get(Entity,case.seller_entity_id) if case.seller_entity_id else None
    gates=[]
    for gate in session.scalars(select(PrivateSaleGate).where(PrivateSaleGate.case_id==case.id).order_by(PrivateSaleGate.id)):
        claim_ids=list(session.scalars(select(PrivateSaleGateEvidence.claim_id).where(PrivateSaleGateEvidence.gate_id==gate.id).order_by(PrivateSaleGateEvidence.id)))
        history=[{"action":x.action,"prior_state":x.prior_state,"resulting_state":x.resulting_state,"actor":x.actor,"actor_role":x.actor_role,"rationale":x.rationale,"evidence_package_hash":x.evidence_package_hash,"occurred_at":x.occurred_at.isoformat()} for x in session.scalars(select(PrivateSaleGateEvent).where(PrivateSaleGateEvent.gate_id==gate.id).order_by(PrivateSaleGateEvent.id))]
        gates.append({"id":gate.id,"code":gate.gate_code,"fact_class":gate.fact_class,"critical":gate.critical,"counsel_required":gate.counsel_required,"status":gate.status,"exception_reason":gate.exception_reason,"claim_ids":claim_ids,"sufficiency":gate_sufficiency(session,gate.id),"history":history})
    identity=lambda x:{"id":x.id,"name":x.name,"universe":x.universe,"entity_type":x.entity_type,"country":x.country} if x else None
    return {"classification":"PRIVATE—AUTHORIZED PRIVATE SALE REVIEW ONLY","id":case.id,"status":case.status,"purpose":case.purpose,"permitted_use":case.permitted_use,"jurisdiction":case.jurisdiction,"owner":case.owner,"asset":identity(asset),"seller":identity(seller),"readiness":private_sale_readiness(session,case.id),"gates":gates}
