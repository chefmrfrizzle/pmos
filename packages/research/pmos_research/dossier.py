from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from typing import Any

from sqlalchemy import select

from .case_checks import evidence_sufficiency
from .db import (
    Claim, ClaimCheckRoutingCandidate, ClaimEvidence, CheckResult, ConflictCase, ConflictMember,
    DiligenceCase, DiligenceCheckEvidence, Entity, EvidencePassage,
    LegalIdentifier, RegistryIdentifierCandidate, ReviewSignoff, SourceDocument,
    ResearchPassageCandidate, ResearchSourceCandidate,
    SourceChangeEvent,
)
from .diligence import FRESHNESS_DAYS, readiness

MATERIAL_SINGLE_VALUE_FIELDS={
    "official_identity":"legal_identity",
    "legal_name":"legal_identity",
    "legal_status":"legal_status",
    "regulatory_status":"regulatory_status",
    "ownership_control":"ownership_control",
    "authority_to_transact":"authority_to_transact",
    "fund_manager":"fund_manager",
    "fund_domicile":"fund_domicile",
}
TERMINAL_CLAIM_STATES={"REJECTED"}

def _utc(value:datetime)->datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def _freshness(claim:Claim,as_of:datetime)->dict[str,Any]:
    fact=MATERIAL_SINGLE_VALUE_FIELDS.get(claim.field,claim.field)
    threshold=FRESHNESS_DAYS.get(fact,180)
    observed=_utc(claim.last_seen or claim.retrieved_at or claim.observed_at)
    age=max(0,(as_of-observed).days)
    return {"state":"CURRENT" if age<=threshold else "STALE","age_days":age,"threshold_days":threshold,"observed_at":observed.isoformat()}

def _claim_evidence(session,claim_id:int,include_passages:bool)->list[dict[str,Any]]:
    rows=session.execute(
        select(ClaimEvidence,EvidencePassage,SourceDocument)
        .join(EvidencePassage,ClaimEvidence.passage_id==EvidencePassage.id)
        .join(SourceDocument,EvidencePassage.document_id==SourceDocument.id)
        .where(ClaimEvidence.claim_id==claim_id)
        .order_by(SourceDocument.source_rank,SourceDocument.id,EvidencePassage.id)
    ).all()
    return [{
        "source_document_id":document.id,"source_rank":document.source_rank,
        "publisher":document.publisher,"independence_group":document.publisher_independence_group,
        "source_type":document.source_type,"source_url":document.source_url,
        "retrieved_at":_utc(document.retrieved_at).isoformat(),"content_hash":document.content_hash,
        "passage_id":passage.id,"page":passage.page,"section":passage.section,
        "passage_hash":passage.passage_hash,"directness":link.directness,"supports":link.supports,
        **({"passage":passage.passage} if include_passages else {}),
    } for link,passage,document in rows]

def _potential_conflicts(claims:list[Claim])->list[dict[str,Any]]:
    grouped=defaultdict(list)
    for claim in claims:
        if claim.field in MATERIAL_SINGLE_VALUE_FIELDS and claim.verification_status.upper() not in TERMINAL_CLAIM_STATES:
            grouped[claim.field].append(claim)
    results=[]
    for field,items in sorted(grouped.items()):
        values=defaultdict(list)
        for item in items:values[" ".join(item.value.casefold().split())].append(item.id)
        if len(values)>1:
            results.append({"predicate":MATERIAL_SINGLE_VALUE_FIELDS[field],"state":"HUMAN_REVIEW_REQUIRED","claim_ids":sorted(x.id for x in items),"distinct_value_count":len(values),"reason":"material single-value claims disagree; temporal or semantic review required"})
    return results

def build_dossier(session,case_id:int,include_passages:bool=True)->dict[str,Any]:
    case=session.get(DiligenceCase,case_id)
    if not case:raise ValueError("unknown diligence case")
    entity=session.get(Entity,case.entity_id)
    if not entity:raise ValueError("unknown case entity")
    as_of=datetime.now(timezone.utc)
    claims=session.scalars(select(Claim).where(Claim.entity_id==entity.id).order_by(Claim.field,Claim.id)).all()
    claim_rows=[]
    for claim in claims:
        evidence=_claim_evidence(session,claim.id,include_passages)
        claim_rows.append({
            "id":claim.id,"field":claim.field,"value":claim.value,"verification_status":claim.verification_status,
            "confidence":claim.confidence,"extractor":claim.extractor,"evidence_hash":claim.evidence_hash,
            "freshness":_freshness(claim,as_of),"evidence":evidence,
            "evidence_state":"EXACT_PASSAGE_LINKED" if evidence else "UNLINKED",
        })
    checks=session.scalars(select(CheckResult).where(CheckResult.case_id==case.id).order_by(CheckResult.id)).all()
    check_rows=[]
    for check in checks:
        linked=sorted(session.scalars(select(DiligenceCheckEvidence.claim_id).where(DiligenceCheckEvidence.check_id==check.id)).all())
        check_rows.append({"id":check.id,"code":check.check_code,"fact_class":check.fact_class,"mandatory":check.mandatory,"status":check.status,"claim_ids":linked,"sufficiency":evidence_sufficiency(session,check.id),"exception_reason":check.exception_reason})
    conflicts=session.scalars(select(ConflictCase).where(ConflictCase.entity_id==entity.id).order_by(ConflictCase.id)).all()
    conflict_rows=[]
    for conflict in conflicts:
        members=sorted(session.scalars(select(ConflictMember.claim_id).where(ConflictMember.conflict_id==conflict.id)).all())
        conflict_rows.append({"id":conflict.id,"predicate":conflict.predicate,"materiality":conflict.materiality,"status":conflict.status,"claim_ids":members,"selected_claim_id":conflict.selected_claim_id,"rationale":conflict.rationale})
    identifiers=session.scalars(select(LegalIdentifier).where(LegalIdentifier.entity_id==entity.id).order_by(LegalIdentifier.identifier_type,LegalIdentifier.id)).all()
    candidates=session.scalars(select(RegistryIdentifierCandidate).where(RegistryIdentifierCandidate.entity_id==entity.id).order_by(RegistryIdentifierCandidate.id)).all()
    signoffs=session.scalars(select(ReviewSignoff).where(ReviewSignoff.case_id==case.id).order_by(ReviewSignoff.id)).all()
    source_candidates=session.scalars(select(ResearchSourceCandidate).where(ResearchSourceCandidate.entity_id==entity.id).order_by(ResearchSourceCandidate.discovery_score.desc(),ResearchSourceCandidate.id)).all()
    source_ids=[x.id for x in source_candidates]
    passage_candidates=session.scalars(select(ResearchPassageCandidate).where(ResearchPassageCandidate.source_candidate_id.in_(source_ids)).order_by(ResearchPassageCandidate.id)).all() if source_ids else []
    passage_rows=[]
    for candidate in passage_candidates:
        passage=session.get(EvidencePassage,candidate.evidence_passage_id)
        source=next(x for x in source_candidates if x.id==candidate.source_candidate_id)
        passage_rows.append({"id":candidate.id,"source_candidate_id":source.id,"predicate":candidate.predicate,"confidence":candidate.confidence,"status":candidate.status,"passage_hash":passage.passage_hash,**({"passage":passage.passage} if include_passages else {})})
    check_ids=[x.id for x in checks]
    routes=session.scalars(select(ClaimCheckRoutingCandidate).where(ClaimCheckRoutingCandidate.check_id.in_(check_ids)).order_by(ClaimCheckRoutingCandidate.id)).all() if check_ids else []
    changes=session.scalars(select(SourceChangeEvent).where(SourceChangeEvent.source_candidate_id.in_(source_ids)).order_by(SourceChangeEvent.detected_at.desc(),SourceChangeEvent.id.desc())).all() if source_ids else []
    linked_count=sum(1 for row in claim_rows if row["evidence_state"]=="EXACT_PASSAGE_LINKED")
    return {
        "classification":"PRIVATE—AUTHORIZED USE ONLY","generated_at":as_of.isoformat(),
        "case":{"id":case.id,"purpose":case.purpose,"permitted_use":case.permitted_use,"risk_tier":case.risk_tier,"status":case.status,"as_of":_utc(case.as_of).isoformat()},
        "entity":{"id":entity.id,"name":entity.name,"universe":entity.universe,"entity_type":entity.entity_type,"country":entity.country,"city":entity.city,"official_url":entity.official_url,"verification_status":entity.verification_status},
        "readiness":readiness(session,case.id),"checks":check_rows,"claims":claim_rows,
        "evidence_coverage":{"claim_count":len(claim_rows),"exact_passage_linked":linked_count,"unlinked":len(claim_rows)-linked_count},
        "recorded_conflicts":conflict_rows,"potential_conflicts":_potential_conflicts(claims),
        "legal_identifiers":[{"type":x.identifier_type,"value":x.identifier_value,"jurisdiction":x.jurisdiction,"status":x.status,"claim_id":x.claim_id} for x in identifiers],
        "identifier_candidates":[{"id":x.id,"type":x.identifier_type,"value":x.identifier_value,"jurisdiction":x.jurisdiction,"match_state":x.match_state,"confidence":x.confidence,"status":x.status,"claim_id":x.claim_id} for x in candidates],
        "research_queue":{"sources":[{"id":x.id,"document_type":x.document_type,"source_url":x.source_url,"target_predicates":json.loads(x.target_predicates_json),"discovery_score":x.discovery_score,"status":x.status} for x in source_candidates],"passages":passage_rows,"source_changes":[{"id":x.id,"source_candidate_id":x.source_candidate_id,"status":x.status,"similarity":x.similarity,"added_token_count":x.added_token_count,"removed_token_count":x.removed_token_count,"detected_at":x.detected_at.isoformat()} for x in changes],"claim_check_routes":[{"id":x.id,"claim_id":x.claim_id,"check_id":x.check_id,"passage_candidate_id":x.passage_candidate_id,"status":x.status,"reason":x.reason} for x in routes]},
        "specialist_signoffs":[{"reviewer":x.reviewer,"role":x.role,"decision":x.decision,"rationale":x.rationale,"signed_at":_utc(x.signed_at).isoformat()} for x in signoffs],
        "limitations":["Absence of evidence is not evidence of absence.","Potential conflicts require temporal, semantic, and specialist review.","Candidate identifiers are not accepted legal identity until independently adjudicated."],
    }
