from __future__ import annotations

import hashlib,json
from datetime import datetime,timezone

from sqlalchemy import select

from .audit_ledger import verify_ledger
from .case_checks import evidence_sufficiency
from .db import (
    AdjudicationEvent,Claim,ClaimCheckRoutingCandidate,ClaimEvidence,ControlAssuranceRun,
    CheckResult,DiligenceCheckAdjudicationEvent,DiligenceCheckEvidence,ExportRequest,ExportRequestEvent,
    EvidencePassage,IdentifierAdjudicationEvent,IdentityCluster,IdentityMembership,PrivateSaleGate,PrivateSaleGateEvent,RelationshipAdjudicationEvent,
    LegalIdentifier,RegistryIdentifierCandidate,RelationshipAssertion,
    ResearchDocumentSnapshot,
    ResearchPassageAdjudicationEvent,ResearchPassageCandidate,
    SourceChangeEvent,SourceChangeReviewEvent,SourceDocument,SourceRetrievalAttempt,ResearchSourceCandidate,
)
from .relationship_controls import relationship_evidence_controls
from .private_sale import gate_sufficiency

QUALIFYING_CLAIMS={"SUPPORTED","CORROBORATED","SPECIALIST_VERIFIED"}

def _control(name:str,population:int,exceptions:int)->dict:
    return {"control":name,"status":"PASS" if exceptions==0 else "FAIL","population":population,"exceptions":exceptions}

def run_control_assurance(session)->dict:
    controls=[]
    ledger=verify_ledger(session);controls.append(_control("audit_ledger_integrity",ledger["entries"],len(ledger["errors"])))

    qualifying=session.scalars(select(Claim).where(Claim.verification_status.in_(QUALIFYING_CLAIMS))).all();bad=0
    for claim in qualifying:
        links=session.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id==claim.id,ClaimEvidence.supports.is_(True))).all();valid=False
        for link in links:
            passage=session.get(EvidencePassage,link.passage_id);document=session.get(SourceDocument,passage.document_id) if passage else None
            if passage and document and claim.entity_id==document.entity_id and claim.evidence_hash==document.content_hash:valid=True;break
        bad+=not valid
    controls.append(_control("qualifying_claim_exact_evidence_chain",len(qualifying),bad))

    passages=session.scalars(select(EvidencePassage)).all();controls.append(_control("evidence_passage_hash_integrity",len(passages),sum(hashlib.sha256(x.passage.encode()).hexdigest()!=x.passage_hash for x in passages)))
    snapshots=session.scalars(select(ResearchDocumentSnapshot)).all();controls.append(_control("research_snapshot_hash_integrity",len(snapshots),sum(hashlib.sha256(x.normalized_text.encode()).hexdigest()!=x.text_hash for x in snapshots)))

    attempts=session.scalars(select(SourceRetrievalAttempt).order_by(SourceRetrievalAttempt.source_candidate_id,SourceRetrievalAttempt.attempt_number)).all();grouped={};bad=0
    for attempt in attempts:grouped.setdefault(attempt.source_candidate_id,[]).append(attempt)
    for rows in grouped.values():
        bad+=([x.attempt_number for x in rows]!=list(range(1,len(rows)+1)))
        bad+=sum(bool(x.retryable)!=bool(x.next_attempt_at) or (x.retryable and x.attempt_number>=3) for x in rows)
    retry_candidates=session.scalars(select(ResearchSourceCandidate).where(ResearchSourceCandidate.status=="RETRY_REQUIRED")).all()
    for candidate in retry_candidates:
        rows=grouped.get(candidate.id,[]);bad+=not rows or not rows[-1].retryable
    controls.append(_control("source_retrieval_attempt_integrity",len(attempts)+len(retry_candidates),bad))

    accepted=session.scalars(select(IdentityCluster).where(IdentityCluster.status=="ACCEPTED")).all();bad=0
    for cluster in accepted:
        members=session.scalars(select(IdentityMembership).where(IdentityMembership.cluster_id==cluster.id)).all()
        bad+=len(members)!=2 or any(x.status!="ACCEPTED" or not x.decided_by for x in members) or any(x.decided_by==cluster.created_by for x in members)
    controls.append(_control("accepted_identity_cluster_maker_checker",len(accepted),bad))

    active=session.scalars(select(IdentityCluster).where(IdentityCluster.status.in_(("PROPOSED","ACCEPTED")))).all();membership_counts={};bad=0;population=0
    for cluster in active:
        members=session.scalars(select(IdentityMembership).where(IdentityMembership.cluster_id==cluster.id)).all();population+=len(members)
        if len(members)!=2:bad+=1
        for member in members:
            value=member.entity_id if cluster.identity_type=="ENTITY" else member.contact_id
            if value is None:bad+=1;continue
            key=(cluster.identity_type,value);membership_counts[key]=membership_counts.get(key,0)+1
    bad+=sum(count-1 for count in membership_counts.values() if count>1)
    controls.append(_control("active_identity_pair_exclusivity",population,bad))

    identifiers=session.scalars(select(LegalIdentifier).where(LegalIdentifier.status=="SPECIALIST_VERIFIED")).all();bad=0
    for identifier in identifiers:
        claim=session.get(Claim,identifier.claim_id) if identifier.claim_id else None
        candidate=session.scalar(select(RegistryIdentifierCandidate).where(RegistryIdentifierCandidate.entity_id==identifier.entity_id,RegistryIdentifierCandidate.identifier_type==identifier.identifier_type,RegistryIdentifierCandidate.identifier_value==identifier.identifier_value,RegistryIdentifierCandidate.status=="ACCEPTED"))
        events=session.scalars(select(IdentifierAdjudicationEvent).where(IdentifierAdjudicationEvent.candidate_id==candidate.id).order_by(IdentifierAdjudicationEvent.id)).all() if candidate else []
        proposer=next((x.reviewer for x in events if x.action=="PROPOSE_ACCEPTANCE"),None);approver=next((x.reviewer for x in reversed(events) if x.action=="APPROVE"),None)
        bad+=not claim or claim.entity_id!=identifier.entity_id or claim.value!=identifier.identifier_value or claim.verification_status!="SPECIALIST_VERIFIED" or not proposer or not approver or proposer==approver
    controls.append(_control("accepted_legal_identifier_maker_checker",len(identifiers),bad))

    relationships=session.scalars(select(RelationshipAssertion).where(RelationshipAssertion.status=="SPECIALIST_VERIFIED")).all();bad=0
    for assertion in relationships:
        controls=relationship_evidence_controls(session,assertion);events=session.scalars(select(RelationshipAdjudicationEvent).where(RelationshipAdjudicationEvent.relationship_assertion_id==assertion.id).order_by(RelationshipAdjudicationEvent.id)).all();proposal=next((x for x in events if x.action=="PROPOSE"),None);approval=next((x for x in reversed(events) if x.action=="APPROVE"),None)
        bad+=not assertion.reviewed_by or assertion.proposed_by==assertion.reviewed_by or not controls["verification_eligible"] or not proposal or not approval or proposal.actor==approval.actor or proposal.evidence_package_hash!=approval.evidence_package_hash or proposal.evidence_package_hash!=controls["evidence_package_hash"]
    controls.append(_control("verified_relationship_evidence_and_independence",len(relationships),bad))

    completed_gates=session.scalars(select(PrivateSaleGate).where(PrivateSaleGate.status.in_({"PASS","PASS_WITH_EXCEPTION","BLOCKED"}))).all();bad=0
    for gate in completed_gates:
        events=session.scalars(select(PrivateSaleGateEvent).where(PrivateSaleGateEvent.gate_id==gate.id).order_by(PrivateSaleGateEvent.id)).all()
        if gate.status=="PASS":
            proposal=next((x for x in events if x.action=="PROPOSE_PASS"),None);approval=next((x for x in reversed(events) if x.action=="APPROVE"),None)
            try:sufficient=gate_sufficiency(session,gate.id)["sufficient"]
            except Exception:sufficient=False
            current=gate_sufficiency(session,gate.id)["evidence_package_hash"]
            bad+=not proposal or not approval or proposal.actor==approval.actor or not sufficient or proposal.evidence_package_hash!=approval.evidence_package_hash or approval.evidence_package_hash!=current or (gate.counsel_required and approval.actor_role not in {"COUNSEL","ADMIN"})
        elif gate.status=="PASS_WITH_EXCEPTION":
            proposal=next((x for x in events if x.action=="PROPOSE_EXCEPTION"),None);approval=next((x for x in reversed(events) if x.action=="APPROVE_EXCEPTION"),None)
            current=gate_sufficiency(session,gate.id)["evidence_package_hash"]
            bad+=not proposal or not approval or proposal.actor==approval.actor or not gate.exception_reason or proposal.evidence_package_hash!=approval.evidence_package_hash or approval.evidence_package_hash!=current or (gate.counsel_required and approval.actor_role not in {"COUNSEL","ADMIN"})
        else:bad+=not any(x.action=="MARK_BLOCKED" for x in events)
    controls.append(_control("private_sale_gate_maker_checker_and_evidence",len(completed_gates),bad))

    completed=session.scalars(select(CheckResult).where(CheckResult.status.in_({"SPECIALIST_VERIFIED","CORROBORATED"}))).all();bad=0
    for check in completed:
        events=session.scalars(select(DiligenceCheckAdjudicationEvent).where(DiligenceCheckAdjudicationEvent.check_id==check.id).order_by(DiligenceCheckAdjudicationEvent.id)).all();proposer=next((x.reviewer for x in events if x.action=="PROPOSE_COMPLETE"),None);approver=next((x.reviewer for x in reversed(events) if x.action=="APPROVE"),None)
        try:sufficient=evidence_sufficiency(session,check.id)["sufficient"]
        except Exception:sufficient=False
        bad+=not proposer or not approver or proposer==approver or not sufficient
    controls.append(_control("completed_check_sufficiency_and_maker_checker",len(completed),bad))

    routes=session.scalars(select(ClaimCheckRoutingCandidate).where(ClaimCheckRoutingCandidate.status=="ATTACHED")).all();bad=0
    for route in routes:
        claim=session.get(Claim,route.claim_id);check=session.get(CheckResult,route.check_id);linked=session.scalar(select(DiligenceCheckEvidence.id).where(DiligenceCheckEvidence.check_id==route.check_id,DiligenceCheckEvidence.claim_id==route.claim_id))
        bad+=not claim or not check or claim.field!=check.fact_class or claim.verification_status not in QUALIFYING_CLAIMS or not linked
    controls.append(_control("attached_route_scope_and_linkage",len(routes),bad))

    supported_passages=session.scalars(select(ResearchPassageCandidate).where(ResearchPassageCandidate.status=="SUPPORTED")).all();bad=0
    for candidate in supported_passages:
        events=session.scalars(select(ResearchPassageAdjudicationEvent).where(ResearchPassageAdjudicationEvent.passage_candidate_id==candidate.id).order_by(ResearchPassageAdjudicationEvent.id)).all();proposal=next((x for x in events if x.action=="PROPOSE_SUPPORT"),None);approval=next((x for x in reversed(events) if x.action=="APPROVE_SUPPORT"),None);claim=session.get(Claim,approval.resulting_claim_id) if approval and approval.resulting_claim_id else None
        linked=session.scalar(select(ClaimEvidence.id).where(ClaimEvidence.claim_id==claim.id,ClaimEvidence.passage_id==candidate.evidence_passage_id)) if claim else None
        bad+=not proposal or not approval or proposal.reviewer==approval.reviewer or proposal.claim_value!=approval.claim_value or not claim or claim.verification_status!="SUPPORTED" or not linked
    controls.append(_control("supported_passage_maker_checker_and_claim_link",len(supported_passages),bad))

    reviewed_changes=session.scalars(select(SourceChangeEvent).where(SourceChangeEvent.status.in_({"ACKNOWLEDGED","ESCALATED","DEFERRED"}))).all();bad=0
    for event in reviewed_changes:
        actions=session.scalars(select(SourceChangeReviewEvent).where(SourceChangeReviewEvent.change_event_id==event.id).order_by(SourceChangeReviewEvent.id)).all()
        bad+=not actions or actions[-1].resulting_state!=event.status
    controls.append(_control("source_change_review_history",len(reviewed_changes),bad))

    exports=session.scalars(select(ExportRequest).where(ExportRequest.status=="EXPORTED")).all();bad=0
    for request in exports:
        events=session.scalars(select(ExportRequestEvent).where(ExportRequestEvent.export_request_id==request.id).order_by(ExportRequestEvent.id)).all();approved=next((x for x in events if x.action=="APPROVE"),None);executed=next((x for x in reversed(events) if x.action=="EXECUTE"),None)
        bad+=not approved or not executed or approved.actor==request.requester or executed.actor==request.requester or request.approved_by!=approved.actor or request.executed_by!=executed.actor or not request.artifact_name or not request.artifact_sha256
    controls.append(_control("executed_export_approval_and_manifest_metadata",len(exports),bad))

    failures=sum(x["exceptions"] for x in controls)
    return {"classification":"PMOS PRIVATE CONTROL TOTALS — NO RECORD VALUES","generated_at":datetime.now(timezone.utc).isoformat(),"status":"PASS" if failures==0 else "FAIL","control_count":len(controls),"exception_count":failures,"controls":controls}

def persist_assurance_run(session,result:dict,actor:str="control-assurance-worker")->ControlAssuranceRun:
    canonical=json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=False);digest=hashlib.sha256(canonical.encode()).hexdigest()
    run=ControlAssuranceRun(status=result["status"],control_count=result["control_count"],exception_count=result["exception_count"],report_hash=digest,report_json=canonical,actor=actor);session.add(run);session.flush()
    from .audit_ledger import append_ledger_event
    append_ledger_event(session,"CONTROL_ASSURANCE",run.id,actor,"SYSTEM","ASSURANCE_RUN_RECORDED",{"status":run.status,"control_count":run.control_count,"exception_count":run.exception_count,"report_hash":digest})
    return run
