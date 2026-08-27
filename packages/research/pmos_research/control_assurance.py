from __future__ import annotations

import hashlib,json
from datetime import datetime,timezone

from sqlalchemy import select

from .audit_ledger import verify_ledger
from .case_checks import evidence_sufficiency
from .db import (
    AdjudicationEvent,Claim,ClaimCheckRoutingCandidate,ClaimEvidence,ControlAssuranceRun,CorroborationJob,Entity,
    CheckResult,DiligenceCheckAdjudicationEvent,DiligenceCheckEvidence,ExportRequest,ExportRequestEvent,
    EvidencePassage,EvidenceReviewAssignment,EvidenceReviewAssignmentEvent,EvidenceReviewBatch,EvidenceReviewBatchItem,EvidenceReviewDecisionAuthorization,EvidenceReviewDecisionBinding,IdentifierAdjudicationEvent,IdentityCluster,IdentityMembership,IdentityReviewAssignment,IdentityReviewAssignmentEvent,IdentityReviewBatch,IdentityReviewBatchItem,IdentityReviewDecisionAuthorization,IdentityReviewDecisionBinding,JurisdictionReviewCase,JurisdictionReviewEvent,PrivateSaleGate,PrivateSaleGateEvent,RelationshipAdjudicationEvent,
    LegalIdentifier,RegistryIdentifierCandidate,RelationshipAssertion,RelationshipAssertionEvidence,RelationshipCandidateDecisionAuthorization,RelationshipMentionCandidate,RelationshipMentionCandidateEvent,RelationshipMentionResolution,RelationshipMentionResolutionEvent,RelationshipMentionReviewAssignment,RelationshipMentionReviewAssignmentEvent,RelationshipMentionReviewBatch,RelationshipMentionReviewBatchItem,RelationshipMentionReviewDecisionBinding,RelationshipResearchCandidate,RelationshipResearchCandidateEvent,
    ResearchDocumentSnapshot,
    ResearchPassageAdjudicationEvent,ResearchPassageCandidate,
    IncidentResponseExerciseRun,LegalHold,LegalHoldEvent,PrivateEgressReviewCase,PrivateEgressReviewEvent,PublisherIndependenceAssessment,PublisherIndependenceEvent,RestoreDrillRun,RetentionAssessmentRun,ReviewerRosterAssessmentRun,SecurityReadinessRun,SourceChangeEvent,SourceChangeReviewEvent,SourceDocument,SourceRetrievalAttempt,ResearchSourceCandidate,ReviewQueueItem,UniverseCoverageRun,
)
from .relationship_controls import relationship_evidence_controls
from .private_sale import gate_sufficiency
from .evidence_review_batch import build_batch_packet
from .identity_review_batch import build_identity_batch_packet
from .publisher_independence import build_publisher_independence_packet
from .relationship_research import mention_identity_package_hash
from .relationship_mention_review import build_mention_review_batch_packet
from .private_egress_review import evidence_package

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
    batches=session.scalars(select(EvidenceReviewBatch)).all();controls.append(_control("frozen_evidence_review_batch_manifest_integrity",len(batches),sum(not build_batch_packet(session,x.id)["manifest_valid"] for x in batches)))
    identity_batches=session.scalars(select(IdentityReviewBatch)).all();controls.append(_control("frozen_identity_review_batch_manifest_integrity",len(identity_batches),sum(not build_identity_batch_packet(session,x.id)["manifest_valid"] for x in identity_batches)))
    mention_batches=session.scalars(select(RelationshipMentionReviewBatch)).all();controls.append(_control("frozen_mention_review_batch_manifest_integrity",len(mention_batches),sum(not build_mention_review_batch_packet(session,x.id)["manifest_valid"] for x in mention_batches)))
    assignments=session.scalars(select(EvidenceReviewAssignment)).all();bad=0;now=datetime.now(timezone.utc)
    for assignment in assignments:
        events=session.scalars(select(EvidenceReviewAssignmentEvent).where(EvidenceReviewAssignmentEvent.assignment_id==assignment.id).order_by(EvidenceReviewAssignmentEvent.id)).all();expires=assignment.expires_at if assignment.expires_at.tzinfo else assignment.expires_at.replace(tzinfo=timezone.utc);created=assignment.created_at if assignment.created_at.tzinfo else assignment.created_at.replace(tzinfo=timezone.utc)
        terminal={"REVOKED":"REVOKE","EXPIRED":"EXPIRE"}.get(assignment.status);bad+=assignment.assigned_by==assignment.reviewer or assignment.reviewer_role not in {"RESEARCHER","REVIEWER","COUNSEL"} or expires<=created or not events or events[0].action!="ASSIGN" or (assignment.status=="ACTIVE" and expires<=now) or bool(terminal and not any(x.action in {terminal,"BATCH_CLOSE"} for x in events)) or bool(assignment.status=="REVOKED" and (not assignment.revoked_by or not assignment.revocation_reason))
    controls.append(_control("evidence_review_assignment_lifecycle",len(assignments),bad))
    identity_assignments=session.scalars(select(IdentityReviewAssignment)).all();bad=0
    for assignment in identity_assignments:
        events=session.scalars(select(IdentityReviewAssignmentEvent).where(IdentityReviewAssignmentEvent.assignment_id==assignment.id).order_by(IdentityReviewAssignmentEvent.id)).all();expires=assignment.expires_at if assignment.expires_at.tzinfo else assignment.expires_at.replace(tzinfo=timezone.utc);created=assignment.created_at if assignment.created_at.tzinfo else assignment.created_at.replace(tzinfo=timezone.utc);terminal={"REVOKED":"REVOKE","EXPIRED":"EXPIRE"}.get(assignment.status);bad+=assignment.assigned_by==assignment.reviewer or assignment.reviewer_role not in {"RESEARCHER","REVIEWER"} or expires<=created or not events or events[0].action!="ASSIGN" or (assignment.status=="ACTIVE" and expires<=now) or bool(terminal and not any(x.action in {terminal,"BATCH_CLOSE"} for x in events)) or bool(assignment.status=="REVOKED" and (not assignment.revoked_by or not assignment.revocation_reason))
    controls.append(_control("identity_review_assignment_lifecycle",len(identity_assignments),bad))
    mention_assignments=session.scalars(select(RelationshipMentionReviewAssignment)).all();bad=0
    for assignment in mention_assignments:
        events=session.scalars(select(RelationshipMentionReviewAssignmentEvent).where(RelationshipMentionReviewAssignmentEvent.assignment_id==assignment.id).order_by(RelationshipMentionReviewAssignmentEvent.id)).all();expires=assignment.expires_at if assignment.expires_at.tzinfo else assignment.expires_at.replace(tzinfo=timezone.utc);created=assignment.created_at if assignment.created_at.tzinfo else assignment.created_at.replace(tzinfo=timezone.utc);terminal={"REVOKED":"REVOKE","EXPIRED":"EXPIRE"}.get(assignment.status);bad+=assignment.assigned_by==assignment.reviewer or assignment.reviewer_role not in {"RESEARCHER","REVIEWER"} or expires<=created or not events or events[0].action!="ASSIGN" or (assignment.status=="ACTIVE" and expires<=now) or bool(terminal and not any(x.action in {terminal,"BATCH_CLOSE"} for x in events)) or bool(assignment.status=="REVOKED" and (not assignment.revoked_by or not assignment.revocation_reason))
    controls.append(_control("mention_review_assignment_lifecycle",len(mention_assignments),bad))

    coverage_runs=session.scalars(select(UniverseCoverageRun)).all();bad=0
    for run in coverage_runs:
        try:parsed=json.loads(run.report_json);valid_status=parsed.get("status")==run.status
        except Exception:valid_status=False
        bad+=hashlib.sha256(run.report_json.encode()).hexdigest()!=run.report_hash or not valid_status
    controls.append(_control("universe_coverage_report_integrity",len(coverage_runs),bad))
    readiness_runs=session.scalars(select(SecurityReadinessRun)).all();bad=0
    for run in readiness_runs:
        try:parsed=json.loads(run.report_json);valid_status=parsed.get("status")==run.status and parsed.get("classification")=="PMOS PRIVATE AGGREGATE SECURITY READINESS — NO RECORD VALUES"
        except Exception:valid_status=False
        bad+=hashlib.sha256(run.report_json.encode()).hexdigest()!=run.report_hash or not valid_status
    controls.append(_control("security_readiness_report_integrity",len(readiness_runs),bad))
    retention_runs=session.scalars(select(RetentionAssessmentRun)).all();bad=0
    for run in retention_runs:
        try:parsed=json.loads(run.report_json);valid_status=parsed.get("status")==run.status and parsed.get("classification")=="PMOS PRIVATE AGGREGATE RETENTION ASSESSMENT — NO RECORD VALUES" and parsed.get("policy_hash")==run.policy_hash
        except Exception:valid_status=False
        bad+=hashlib.sha256(run.report_json.encode()).hexdigest()!=run.report_hash or not valid_status
    controls.append(_control("retention_assessment_report_integrity",len(retention_runs),bad))
    restore_drills=session.scalars(select(RestoreDrillRun)).all();bad=0
    for run in restore_drills:
        try:parsed=json.loads(run.report_json);valid=parsed.get("classification")=="PMOS PRIVATE AGGREGATE RESTORE DRILL — NO PATHS OR RECORD VALUES" and parsed.get("status")==run.status and parsed.get("backup_sha256")==run.backup_sha256 and parsed.get("ledger_entries")==run.ledger_entries
        except Exception:valid=False
        bad+=not valid or hashlib.sha256(run.report_json.encode()).hexdigest()!=run.result_hash or run.status!="PASS" or len(run.backup_sha256)!=64 or run.sqlite_integrity!="ok" or not run.encrypted_storage_verified or not run.temporary_restore_removed or run.ledger_entries<0
    controls.append(_control("restore_drill_integrity",len(restore_drills),bad))
    exercises=session.scalars(select(IncidentResponseExerciseRun)).all();bad=0
    for run in exercises:
        try:parsed=json.loads(run.report_json);valid=parsed.get("classification")=="PMOS PRIVATE AGGREGATE INCIDENT EXERCISE — SYNTHETIC CANARIES ONLY" and parsed.get("status")==run.status and parsed.get("scenario")==run.scenario and parsed.get("detection_count")==run.detection_count
        except Exception:valid=False
        bad+=not valid or hashlib.sha256(run.report_json.encode()).hexdigest()!=run.report_hash or run.status!="PASS" or run.detection_count<5 or not run.containment_verified or not run.recovery_verified
    controls.append(_control("incident_response_exercise_integrity",len(exercises),bad))
    roster_runs=session.scalars(select(ReviewerRosterAssessmentRun)).all();bad=0
    for run in roster_runs:
        try:parsed=json.loads(run.report_json);valid=parsed.get("classification")=="PMOS PRIVATE AGGREGATE REVIEWER STAFFING ASSESSMENT — NO SUBJECT IDENTITIES" and parsed.get("status")==run.status and parsed.get("roster_hash")==run.roster_hash
        except Exception:valid=False
        bad+=not valid or hashlib.sha256(run.report_json.encode()).hexdigest()!=run.report_hash
    controls.append(_control("reviewer_roster_assessment_integrity",len(roster_runs),bad))
    holds=session.scalars(select(LegalHold)).all();bad=0
    for hold in holds:
        events=session.scalars(select(LegalHoldEvent).where(LegalHoldEvent.legal_hold_id==hold.id).order_by(LegalHoldEvent.id)).all();proposal=next((x for x in events if x.action=="PROPOSE"),None);approval=next((x for x in events if x.action=="APPROVE"),None);released=next((x for x in reversed(events) if x.action=="RELEASE"),None)
        bad+=not proposal or proposal.actor!=hold.created_by or (hold.status in {"ACTIVE","RELEASED"} and (not approval or approval.actor==hold.created_by or hold.approved_by!=approval.actor)) or (hold.status=="RELEASED" and (not released or released.actor in {hold.created_by,hold.approved_by} or hold.released_by!=released.actor or not hold.released_at))
    controls.append(_control("legal_hold_maker_checker_and_history",len(holds),bad))

    attempts=session.scalars(select(SourceRetrievalAttempt).order_by(SourceRetrievalAttempt.source_candidate_id,SourceRetrievalAttempt.attempt_number)).all();grouped={};bad=0
    for attempt in attempts:grouped.setdefault(attempt.source_candidate_id,[]).append(attempt)
    for rows in grouped.values():
        bad+=([x.attempt_number for x in rows]!=list(range(1,len(rows)+1)))
        bad+=sum(bool(x.retryable)!=bool(x.next_attempt_at) or (x.retryable and x.attempt_number>=3) for x in rows)
    retry_candidates=session.scalars(select(ResearchSourceCandidate).where(ResearchSourceCandidate.status=="RETRY_REQUIRED")).all()
    for candidate in retry_candidates:
        rows=grouped.get(candidate.id,[]);bad+=not rows or not rows[-1].retryable
    controls.append(_control("source_retrieval_attempt_integrity",len(attempts)+len(retry_candidates),bad))
    corroboration_jobs=session.scalars(select(CorroborationJob)).all();bad=0
    for job in corroboration_jobs:
        bad+=job.attempts<0 or (job.status=="PENDING" and (job.attempts!=0 or job.next_attempt_at is not None)) or (job.status=="RETRY_REQUIRED" and (job.attempts not in {1,2} or job.next_attempt_at is None)) or (job.status not in {"PENDING","RETRY_REQUIRED"} and job.next_attempt_at is not None)
    controls.append(_control("corroboration_retry_lifecycle",len(corroboration_jobs),bad))
    entities_by_id={x.id:x for x in session.scalars(select(Entity)).all()};private_jobs=[x for x in corroboration_jobs if entities_by_id.get(x.entity_id) and entities_by_id[x.entity_id].universe=="imported_private"];reviewed_job_ids=set(session.scalars(select(PrivateEgressReviewCase.corroboration_job_id)).all());bad=sum((x.attempts==0 and x.status!="PRIVATE_EGRESS_QUARANTINED") or (x.attempts>0 and x.id not in reviewed_job_ids) for x in private_jobs)
    controls.append(_control("private_research_egress_quarantine",len(private_jobs),bad))
    private_sources=session.scalars(select(ResearchSourceCandidate).join(Entity,Entity.id==ResearchSourceCandidate.entity_id).where(Entity.universe=="imported_private")).all();bad=0
    for candidate in private_sources:
        attempted=session.scalar(select(SourceRetrievalAttempt.id).where(SourceRetrievalAttempt.source_candidate_id==candidate.id).limit(1));bad+=bool(attempted) or candidate.status!="PRIVATE_EGRESS_QUARANTINED"
    controls.append(_control("private_deep_source_egress_quarantine",len(private_sources),bad))
    egress_cases=session.scalars(select(PrivateEgressReviewCase)).all();bad=0
    for case in egress_cases:
        job=session.get(CorroborationJob,case.corroboration_job_id);events=session.scalars(select(PrivateEgressReviewEvent).where(PrivateEgressReviewEvent.case_id==case.id).order_by(PrivateEgressReviewEvent.id)).all();proposal=next((x for x in events if x.action.startswith("PROPOSE_")),None);approval=next((x for x in reversed(events) if x.action.startswith("APPROVE_")),None)
        try:current=evidence_package(session,case.id)["evidence_package_hash"]
        except Exception:current=None
        terminal=case.status in {"RESOLVED_NO_MATERIAL_DISCLOSURE","ESCALATED"};bad+=not job or job.attempts<1 or not current or (terminal and (not proposal or not approval or proposal.actor==approval.actor or proposal.evidence_package_hash!=approval.evidence_package_hash or approval.evidence_package_hash!=current))
    controls.append(_control("private_egress_review_maker_checker",len(egress_cases),bad))

    accepted=session.scalars(select(IdentityCluster).where(IdentityCluster.status=="ACCEPTED")).all();bad=0
    for cluster in accepted:
        members=session.scalars(select(IdentityMembership).where(IdentityMembership.cluster_id==cluster.id)).all()
        bad+=len(members)!=2 or any(x.status!="ACCEPTED" or not x.decided_by for x in members) or any(x.decided_by==cluster.created_by for x in members)
    controls.append(_control("accepted_identity_cluster_maker_checker",len(accepted),bad))

    accepted_items=session.scalars(select(ReviewQueueItem).where(ReviewQueueItem.status=="ACCEPTED")).all();bad=0
    for item in accepted_items:
        events=session.scalars(select(AdjudicationEvent).where(AdjudicationEvent.queue_item_id==item.id).order_by(AdjudicationEvent.id)).all();proposal=next((x for x in events if x.action=="PROPOSE_MATCH"),None);approval=next((x for x in reversed(events) if x.action=="APPROVE_MATCH"),None);proposal_binding=session.scalar(select(IdentityReviewDecisionBinding).where(IdentityReviewDecisionBinding.adjudication_event_id==proposal.id)) if proposal else None;approval_binding=session.scalar(select(IdentityReviewDecisionBinding).where(IdentityReviewDecisionBinding.adjudication_event_id==approval.id)) if approval else None;batch_item=session.get(IdentityReviewBatchItem,proposal_binding.batch_item_id) if proposal_binding else None
        proposal_auth=session.scalar(select(IdentityReviewDecisionAuthorization).where(IdentityReviewDecisionAuthorization.adjudication_event_id==proposal.id)) if proposal else None;approval_auth=session.scalar(select(IdentityReviewDecisionAuthorization).where(IdentityReviewDecisionAuthorization.adjudication_event_id==approval.id)) if approval else None;proposal_assignment=session.get(IdentityReviewAssignment,proposal_auth.assignment_id) if proposal_auth else None;approval_assignment=session.get(IdentityReviewAssignment,approval_auth.assignment_id) if approval_auth else None
        bad+=not proposal or not approval or proposal.reviewer==approval.reviewer or not proposal_binding or not approval_binding or proposal_binding.batch_item_id!=approval_binding.batch_item_id or not batch_item or batch_item.queue_item_id!=item.id or not proposal_assignment or not approval_assignment or proposal_assignment.reviewer!=proposal.reviewer or approval_assignment.reviewer!=approval.reviewer or proposal_assignment.reviewer_role not in {"RESEARCHER","REVIEWER"} or approval_assignment.reviewer_role!="REVIEWER" or proposal_assignment.assigned_by==proposal.reviewer or approval_assignment.assigned_by==approval.reviewer or proposal_auth.authorized_at>proposal_assignment.expires_at or approval_auth.authorized_at>approval_assignment.expires_at
    controls.append(_control("accepted_identity_decision_frozen_batch_binding",len(accepted_items),bad))

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

    jurisdiction_cases=session.scalars(select(JurisdictionReviewCase).where(JurisdictionReviewCase.status=="APPROVED")).all();bad=0
    for case in jurisdiction_cases:
        entity=session.get(Entity,case.entity_id);claim=session.get(Claim,case.source_claim_id) if case.source_claim_id else None;events=session.scalars(select(JurisdictionReviewEvent).where(JurisdictionReviewEvent.case_id==case.id).order_by(JurisdictionReviewEvent.id)).all();proposal=next((x for x in events if x.action=="PROPOSE_CORRECTION"),None);approval=next((x for x in reversed(events) if x.action=="APPROVE_CORRECTION"),None)
        bad+=not entity or entity.country!=case.proposed_country or not claim or claim.entity_id!=case.entity_id or claim.value.strip().upper()!=case.proposed_country or claim.verification_status not in QUALIFYING_CLAIMS or not claim.evidence_hash or not proposal or not approval or proposal.actor==approval.actor or case.proposed_by!=proposal.actor or case.reviewed_by!=approval.actor
    controls.append(_control("approved_jurisdiction_correction_evidence_and_maker_checker",len(jurisdiction_cases),bad))

    publisher_assessments=session.scalars(select(PublisherIndependenceAssessment).where(PublisherIndependenceAssessment.status=="APPROVED")).all();bad=0
    for assessment in publisher_assessments:
        packet=build_publisher_independence_packet(session,assessment.id);events=session.scalars(select(PublisherIndependenceEvent).where(PublisherIndependenceEvent.assessment_id==assessment.id).order_by(PublisherIndependenceEvent.id)).all();proposal=next((x for x in events if x.action=="PROPOSE"),None);approval=next((x for x in reversed(events) if x.action=="APPROVE"),None)
        bad+=not packet["evidence"] or not proposal or not approval or proposal.actor==approval.actor or proposal.evidence_package_hash!=assessment.evidence_package_hash or approval.evidence_package_hash!=assessment.evidence_package_hash
    controls.append(_control("approved_publisher_independence_maker_checker",len(publisher_assessments),bad))

    relationships=session.scalars(select(RelationshipAssertion).where(RelationshipAssertion.status=="SPECIALIST_VERIFIED")).all();bad=0
    for assertion in relationships:
        rel_controls=relationship_evidence_controls(session,assertion);events=session.scalars(select(RelationshipAdjudicationEvent).where(RelationshipAdjudicationEvent.relationship_assertion_id==assertion.id).order_by(RelationshipAdjudicationEvent.id)).all();proposal=next((x for x in events if x.action=="PROPOSE"),None);approval=next((x for x in reversed(events) if x.action=="APPROVE"),None)
        bad+=not assertion.reviewed_by or assertion.proposed_by==assertion.reviewed_by or not rel_controls["verification_eligible"] or not proposal or not approval or proposal.actor==approval.actor or proposal.evidence_package_hash!=approval.evidence_package_hash or proposal.evidence_package_hash!=rel_controls["evidence_package_hash"]
    controls.append(_control("verified_relationship_evidence_and_independence",len(relationships),bad))

    promoted_candidates=session.scalars(select(RelationshipResearchCandidate).where(RelationshipResearchCandidate.status=="ASSERTION_PROPOSED")).all();bad=0
    for candidate in promoted_candidates:
        assertion=session.get(RelationshipAssertion,candidate.resulting_assertion_id) if candidate.resulting_assertion_id else None;link=session.scalar(select(RelationshipAssertionEvidence.id).where(RelationshipAssertionEvidence.relationship_assertion_id==candidate.resulting_assertion_id,RelationshipAssertionEvidence.evidence_passage_id==candidate.evidence_passage_id)) if assertion else None
        bad+=not assertion or assertion.from_entity_id!=candidate.from_entity_id or assertion.to_entity_id!=candidate.to_entity_id or assertion.relation_type!=candidate.suggested_relation_type or not link
    controls.append(_control("relationship_candidate_promotion_exact_evidence_link",len(promoted_candidates),bad))
    candidate_events=session.scalars(select(RelationshipResearchCandidateEvent)).all();bad=0
    for event in candidate_events:
        authorization=session.scalar(select(RelationshipCandidateDecisionAuthorization).where(RelationshipCandidateDecisionAuthorization.candidate_event_id==event.id));assignment=session.get(EvidenceReviewAssignment,authorization.assignment_id) if authorization else None;item=session.get(EvidenceReviewBatchItem,authorization.batch_item_id) if authorization else None;candidate=session.get(RelationshipResearchCandidate,event.candidate_id);passage_candidate=session.get(ResearchPassageCandidate,item.passage_candidate_id) if item else None;occurred=event.occurred_at if event.occurred_at.tzinfo else event.occurred_at.replace(tzinfo=timezone.utc);expires=assignment.expires_at if assignment and assignment.expires_at.tzinfo else assignment.expires_at.replace(tzinfo=timezone.utc) if assignment else None
        bad+=not authorization or not assignment or not item or not candidate or not passage_candidate or passage_candidate.evidence_passage_id!=candidate.evidence_passage_id or assignment.batch_id!=item.batch_id or assignment.reviewer!=event.actor or assignment.reviewer_role not in {"RESEARCHER","REVIEWER"} or not expires or occurred>expires
    controls.append(_control("relationship_candidate_decision_assignment_binding",len(candidate_events),bad))
    mention_resolutions=session.scalars(select(RelationshipMentionResolution)).all();bad=0
    for resolution in mention_resolutions:
        mention=session.get(RelationshipMentionCandidate,resolution.mention_candidate_id);target=session.get(Entity,resolution.target_entity_id);events=session.scalars(select(RelationshipMentionResolutionEvent).where(RelationshipMentionResolutionEvent.resolution_id==resolution.id).order_by(RelationshipMentionResolutionEvent.id)).all();proposal=next((x for x in events if x.action=="PROPOSE_TARGET"),None);terminal=next((x for x in reversed(events) if x.action in {"APPROVE_TARGET","REJECT_TARGET"}),None)
        try:package_valid=bool(mention and target and resolution.identity_package_hash==mention_identity_package_hash(session,mention,target))
        except Exception:package_valid=False
        bad+=not proposal or proposal.actor!=resolution.proposed_by or proposal.identity_package_hash!=resolution.identity_package_hash or not package_valid or (resolution.status in {"APPROVED","REJECTED"} and (not terminal or terminal.actor==proposal.actor or terminal.identity_package_hash!=resolution.identity_package_hash))
    controls.append(_control("mention_resolution_package_and_history",len(mention_resolutions),bad))
    resolution_decisions=session.scalars(select(RelationshipMentionResolutionEvent)).all();direct_decisions=session.scalars(select(RelationshipMentionCandidateEvent).where(RelationshipMentionCandidateEvent.action.in_({"REJECT","DEFER"}))).all();bad=0
    for event in [*resolution_decisions,*direct_decisions]:
        is_resolution=isinstance(event,RelationshipMentionResolutionEvent);binding=session.scalar(select(RelationshipMentionReviewDecisionBinding).where(RelationshipMentionReviewDecisionBinding.resolution_event_id==event.id)) if is_resolution else session.scalar(select(RelationshipMentionReviewDecisionBinding).where(RelationshipMentionReviewDecisionBinding.mention_event_id==event.id));assignment=session.get(RelationshipMentionReviewAssignment,binding.assignment_id) if binding else None;batch_item=session.get(RelationshipMentionReviewBatchItem,binding.batch_item_id) if binding else None;mention=session.get(RelationshipMentionCandidate,session.get(RelationshipMentionResolution,event.resolution_id).mention_candidate_id) if is_resolution else session.get(RelationshipMentionCandidate,event.mention_candidate_id);occurred=event.occurred_at if event.occurred_at.tzinfo else event.occurred_at.replace(tzinfo=timezone.utc);expires=assignment.expires_at if assignment and assignment.expires_at.tzinfo else assignment.expires_at.replace(tzinfo=timezone.utc) if assignment else None;approval=is_resolution and event.action in {"APPROVE_TARGET","REJECT_TARGET"}
        bad+=not binding or not assignment or not batch_item or not mention or batch_item.mention_candidate_id!=mention.id or assignment.batch_id!=batch_item.batch_id or assignment.reviewer!=event.actor or (approval and assignment.reviewer_role!="REVIEWER") or (not approval and assignment.reviewer_role not in {"RESEARCHER","REVIEWER"}) or not expires or occurred>expires
    controls.append(_control("mention_review_decision_batch_and_assignment_binding",len(resolution_decisions)+len(direct_decisions),bad))
    linked_mentions=session.scalars(select(RelationshipMentionCandidate).where(RelationshipMentionCandidate.status=="TARGET_LINKED")).all();bad=0
    for mention in linked_mentions:
        candidate=session.get(RelationshipResearchCandidate,mention.resulting_candidate_id) if mention.resulting_candidate_id else None;resolution=session.scalar(select(RelationshipMentionResolution).where(RelationshipMentionResolution.mention_candidate_id==mention.id,RelationshipMentionResolution.status=="APPROVED").order_by(RelationshipMentionResolution.version.desc()));target=session.get(Entity,mention.resolved_entity_id) if mention.resolved_entity_id else None;events=session.scalars(select(RelationshipMentionResolutionEvent).where(RelationshipMentionResolutionEvent.resolution_id==resolution.id).order_by(RelationshipMentionResolutionEvent.id)).all() if resolution else [];proposal=next((x for x in events if x.action=="PROPOSE_TARGET"),None);approval=next((x for x in reversed(events) if x.action=="APPROVE_TARGET"),None)
        try:package_valid=bool(resolution and target and resolution.identity_package_hash==mention_identity_package_hash(session,mention,target))
        except Exception:package_valid=False
        bad+=not mention.resolved_entity_id or not candidate or not resolution or resolution.target_entity_id!=mention.resolved_entity_id or not proposal or not approval or proposal.actor==approval.actor or proposal.identity_package_hash!=approval.identity_package_hash or not package_valid or candidate.from_entity_id!=mention.from_entity_id or candidate.to_entity_id!=mention.resolved_entity_id or candidate.suggested_relation_type!=mention.suggested_relation_type or candidate.evidence_passage_id!=mention.evidence_passage_id
    controls.append(_control("relationship_mention_resolution_candidate_link",len(linked_mentions),bad))

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
        proposal_binding=session.scalar(select(EvidenceReviewDecisionBinding).where(EvidenceReviewDecisionBinding.adjudication_event_id==proposal.id)) if proposal else None;approval_binding=session.scalar(select(EvidenceReviewDecisionBinding).where(EvidenceReviewDecisionBinding.adjudication_event_id==approval.id)) if approval else None;batch_item=session.get(EvidenceReviewBatchItem,proposal_binding.batch_item_id) if proposal_binding else None
        proposal_auth=session.scalar(select(EvidenceReviewDecisionAuthorization).where(EvidenceReviewDecisionAuthorization.adjudication_event_id==proposal.id)) if proposal else None;approval_auth=session.scalar(select(EvidenceReviewDecisionAuthorization).where(EvidenceReviewDecisionAuthorization.adjudication_event_id==approval.id)) if approval else None;proposal_assignment=session.get(EvidenceReviewAssignment,proposal_auth.assignment_id) if proposal_auth else None;approval_assignment=session.get(EvidenceReviewAssignment,approval_auth.assignment_id) if approval_auth else None
        proposal_assignment_event=session.scalar(select(EvidenceReviewAssignmentEvent).where(EvidenceReviewAssignmentEvent.assignment_id==proposal_assignment.id,EvidenceReviewAssignmentEvent.action=="ASSIGN")) if proposal_assignment else None;approval_assignment_event=session.scalar(select(EvidenceReviewAssignmentEvent).where(EvidenceReviewAssignmentEvent.assignment_id==approval_assignment.id,EvidenceReviewAssignmentEvent.action=="ASSIGN")) if approval_assignment else None
        bad+=not proposal or not approval or proposal.reviewer==approval.reviewer or proposal.claim_value!=approval.claim_value or not claim or claim.verification_status!="SUPPORTED" or not linked or not proposal_binding or not approval_binding or proposal_binding.batch_item_id!=approval_binding.batch_item_id or not batch_item or batch_item.passage_candidate_id!=candidate.id or not proposal_assignment or not approval_assignment or proposal_assignment.reviewer!=proposal.reviewer or approval_assignment.reviewer!=approval.reviewer or proposal_assignment.assigned_by==proposal.reviewer or approval_assignment.assigned_by==approval.reviewer or proposal_assignment.reviewer_role not in {"RESEARCHER","REVIEWER","COUNSEL"} or approval_assignment.reviewer_role not in {"REVIEWER","COUNSEL"} or not proposal_assignment_event or not approval_assignment_event or proposal_auth.authorized_at>proposal_assignment.expires_at or approval_auth.authorized_at>approval_assignment.expires_at
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
