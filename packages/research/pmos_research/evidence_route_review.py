from __future__ import annotations

from .db import ResearchPassageCandidate
from .evidence_routing import route_scope

def build_route_packet(session,route_id:int)->dict:
    route,claim,check,case,entity=route_scope(session,route_id);passage_candidate=session.get(ResearchPassageCandidate,route.passage_candidate_id) if route.passage_candidate_id else None
    return {"classification":"PRIVATE—AUTHORIZED DILIGENCE REVIEW ONLY","id":route.id,"status":route.status,"reason":route.reason,"universe":entity.universe,"entity":{"id":entity.id,"name":entity.name,"entity_type":entity.entity_type,"country":entity.country},"case":{"id":case.id,"purpose":case.purpose,"risk_tier":case.risk_tier,"status":case.status},"check":{"id":check.id,"code":check.check_code,"fact_class":check.fact_class,"status":check.status,"mandatory":check.mandatory},"claim":{"id":claim.id,"field":claim.field,"value":claim.value,"verification_status":claim.verification_status,"confidence":claim.confidence,"source_url":claim.source_url,"evidence_hash":claim.evidence_hash},"passage_candidate_id":passage_candidate.id if passage_candidate else None}
