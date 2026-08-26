from __future__ import annotations
import os
from typing import Optional
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, Float, DateTime, ForeignKey, UniqueConstraint, Integer, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

PRIVATE_ROOT = Path(os.getenv("PMOS_PRIVATE_ROOT", Path.home()/".local"/"share"/"pmos")).expanduser()
DB_URL = os.getenv("PMOS_DB_URL", f"sqlite:///{PRIVATE_ROOT/'pmos.db'}")
engine = create_engine(DB_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), index=True)
    canonical_name: Mapped[str] = mapped_column(String(300), index=True)
    universe: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    official_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mandate: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(50), default="needs_verification")
    last_verified: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    capital_access: Mapped[float] = mapped_column(Float, default=0)
    asset_access: Mapped[float] = mapped_column(Float, default=0)
    network_leverage: Mapped[float] = mapped_column(Float, default=0)
    private_asset_fit: Mapped[float] = mapped_column(Float, default=0)
    engagement_probability: Mapped[float] = mapped_column(Float, default=0)
    immediate_value_fit: Mapped[float] = mapped_column(Float, default=0)
    evidence_confidence: Mapped[float] = mapped_column(Float, default=0)
    strategic_priority: Mapped[float] = mapped_column(Float, default=0)
    useful_wedge: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(50), default="official")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    content_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    __table_args__ = (UniqueConstraint("entity_id", "source_url", "content_hash", name="uq_evidence_snapshot"),)


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    field: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(50), default="official")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    verification_status: Mapped[str] = mapped_column(String(50), default="candidate")
    extractor: Mapped[str] = mapped_column(String(100), default="deterministic")
    evidence_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("entities.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(250), index=True)
    title: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    relationship_stage: Mapped[str] = mapped_column(String(50), default="not_contacted")
    last_verified: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class Relationship(Base):
    __tablename__ = "relationships"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    to_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(80), index=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    verification_status: Mapped[str] = mapped_column(String(50), default="candidate")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Outcome(Base):
    __tablename__ = "outcomes"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    outcome: Mapped[str] = mapped_column(String(50))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_file: Mapped[str] = mapped_column(Text)
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="running")
    rows_seen: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    rows_review: Mapped[int] = mapped_column(Integer, default=0)
    rows_support: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("source_sha256", "source_file", name="uq_import_source_version"),)

class RawImportRow(Base):
    __tablename__ = "raw_import_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    source_file: Mapped[str] = mapped_column(Text)
    sheet_name: Mapped[str] = mapped_column(String(250))
    source_row_number: Mapped[int] = mapped_column(Integer)
    row_hash: Mapped[str] = mapped_column(String(64), index=True)
    original_row_json: Mapped[str] = mapped_column(Text)
    normalized_row_json: Mapped[str] = mapped_column(Text)
    disposition: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("entities.id"), nullable=True, index=True)
    contact_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contacts.id"), nullable=True, index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("batch_id", "sheet_name", "source_row_number", name="uq_import_physical_row"),)

class ResolutionDecision(Base):
    __tablename__ = "resolution_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    raw_row_id: Mapped[int] = mapped_column(ForeignKey("raw_import_rows.id"), index=True)
    candidate_entity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("entities.id"), nullable=True)
    candidate_contact_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contacts.id"), nullable=True)
    state: Mapped[str] = mapped_column(String(40), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    reasons_json: Mapped[str] = mapped_column(Text)
    automatic: Mapped[bool] = mapped_column(Boolean, default=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ReviewQueueItem(Base):
    __tablename__ = "review_queue_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    resolution_decision_id: Mapped[int] = mapped_column(ForeignKey("resolution_decisions.id"), unique=True, index=True)
    queue_type: Mapped[str] = mapped_column(String(50), index=True)
    priority: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    reasons_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class AdjudicationEvent(Base):
    __tablename__ = "adjudication_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    queue_item_id: Mapped[int] = mapped_column(ForeignKey("review_queue_items.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    prior_state: Mapped[str] = mapped_column(String(40))
    resulting_state: Mapped[str] = mapped_column(String(40))
    reviewer: Mapped[str] = mapped_column(String(150))
    rationale: Mapped[str] = mapped_column(Text)
    evidence_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class CorroborationJob(Base):
    __tablename__ = "corroboration_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    source_domain: Mapped[str] = mapped_column(String(300), index=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint_json: Mapped[str] = mapped_column(Text, default="{}")
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("entity_id", "source_url", name="uq_corroboration_target"),)

class ResearchSourceCandidate(Base):
    __tablename__ = "research_source_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    source_domain: Mapped[str] = mapped_column(String(300), index=True)
    document_type: Mapped[str] = mapped_column(String(80), index=True)
    target_predicates_json: Mapped[str] = mapped_column(Text, default="[]")
    link_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    discovered_from_url: Mapped[str] = mapped_column(Text)
    discovery_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    status: Mapped[str] = mapped_column(String(40), default="PENDING_REVIEW", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("entity_id", "source_url", name="uq_entity_research_source"),)

class SourceRetrievalAttempt(Base):
    __tablename__ = "source_retrieval_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_candidate_id: Mapped[int] = mapped_column(ForeignKey("research_source_candidates.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(60), index=True)
    error_class: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("source_candidate_id", "attempt_number", name="uq_source_retrieval_attempt"),)

class ResearchDocumentSnapshot(Base):
    __tablename__ = "research_document_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_candidate_id: Mapped[int] = mapped_column(ForeignKey("research_source_candidates.id"), index=True)
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), index=True)
    normalized_text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("source_candidate_id", "text_hash", name="uq_candidate_document_snapshot"),)

class SourceChangeEvent(Base):
    __tablename__ = "source_change_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_candidate_id: Mapped[int] = mapped_column(ForeignKey("research_source_candidates.id"), index=True)
    prior_snapshot_id: Mapped[int] = mapped_column(ForeignKey("research_document_snapshots.id"), index=True)
    resulting_snapshot_id: Mapped[int] = mapped_column(ForeignKey("research_document_snapshots.id"), index=True)
    prior_hash: Mapped[str] = mapped_column(String(64))
    resulting_hash: Mapped[str] = mapped_column(String(64))
    similarity: Mapped[float] = mapped_column(Float)
    added_token_count: Mapped[int] = mapped_column(Integer, default=0)
    removed_token_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class SourceChangeReviewEvent(Base):
    __tablename__ = "source_change_review_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    change_event_id: Mapped[int] = mapped_column(ForeignKey("source_change_events.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    prior_state: Mapped[str] = mapped_column(String(40))
    resulting_state: Mapped[str] = mapped_column(String(40))
    reviewer: Mapped[str] = mapped_column(String(150))
    rationale: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ResearchPassageCandidate(Base):
    __tablename__ = "research_passage_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_candidate_id: Mapped[int] = mapped_column(ForeignKey("research_source_candidates.id"), index=True)
    evidence_passage_id: Mapped[int] = mapped_column(ForeignKey("evidence_passages.id"), index=True)
    predicate: Mapped[str] = mapped_column(String(120), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    extractor: Mapped[str] = mapped_column(String(100), default="deterministic_passage_v1")
    status: Mapped[str] = mapped_column(String(40), default="HUMAN_REVIEW_REQUIRED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("source_candidate_id", "evidence_passage_id", "predicate", name="uq_candidate_passage_predicate"),)

class ResearchPassageAdjudicationEvent(Base):
    __tablename__ = "research_passage_adjudication_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    passage_candidate_id: Mapped[int] = mapped_column(ForeignKey("research_passage_candidates.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    prior_state: Mapped[str] = mapped_column(String(40))
    resulting_state: Mapped[str] = mapped_column(String(40))
    reviewer: Mapped[str] = mapped_column(String(150))
    rationale: Mapped[str] = mapped_column(Text)
    claim_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resulting_claim_id: Mapped[Optional[int]] = mapped_column(ForeignKey("claims.id"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class EvidenceReviewBatch(Base):
    __tablename__ = "evidence_review_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(30), default="FROZEN", index=True)
    criteria_json: Mapped[str] = mapped_column(Text)
    manifest_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    item_count: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class EvidenceReviewBatchItem(Base):
    __tablename__ = "evidence_review_batch_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("evidence_review_batches.id"), index=True)
    passage_candidate_id: Mapped[int] = mapped_column(ForeignKey("research_passage_candidates.id"), index=True)
    candidate_status: Mapped[str] = mapped_column(String(40))
    predicate: Mapped[str] = mapped_column(String(120))
    passage_hash: Mapped[str] = mapped_column(String(64))
    document_hash: Mapped[str] = mapped_column(String(64))
    evidence_state: Mapped[str] = mapped_column(String(30))
    __table_args__ = (UniqueConstraint("batch_id", "passage_candidate_id", name="uq_batch_passage_candidate"),)

class EvidenceReviewDecisionBinding(Base):
    __tablename__ = "evidence_review_decision_bindings"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_item_id: Mapped[int] = mapped_column(ForeignKey("evidence_review_batch_items.id"), index=True)
    adjudication_event_id: Mapped[int] = mapped_column(ForeignKey("research_passage_adjudication_events.id"), unique=True, index=True)
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ClaimCheckRoutingCandidate(Base):
    __tablename__ = "claim_check_routing_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("diligence_check_results.id"), index=True)
    passage_candidate_id: Mapped[Optional[int]] = mapped_column(ForeignKey("research_passage_candidates.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="PENDING_REVIEW", index=True)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("claim_id", "check_id", name="uq_claim_check_route"),)

class ClaimCheckRoutingEvent(Base):
    __tablename__ = "claim_check_routing_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    routing_candidate_id: Mapped[int] = mapped_column(ForeignKey("claim_check_routing_candidates.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    prior_state: Mapped[str] = mapped_column(String(40))
    resulting_state: Mapped[str] = mapped_column(String(40))
    reviewer: Mapped[str] = mapped_column(String(150))
    rationale: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ControlAssuranceRun(Base):
    __tablename__ = "control_assurance_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    control_count: Mapped[int] = mapped_column(Integer)
    exception_count: Mapped[int] = mapped_column(Integer)
    report_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    report_json: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class UniverseCoverageRun(Base):
    __tablename__ = "universe_coverage_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    report_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    report_json: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ExportRequest(Base):
    __tablename__ = "export_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("diligence_cases.id"), index=True)
    scope: Mapped[str] = mapped_column(String(60), default="DILIGENCE_DOSSIER")
    format: Mapped[str] = mapped_column(String(20), default="JSON")
    purpose: Mapped[str] = mapped_column(Text)
    requester: Mapped[str] = mapped_column(String(150), index=True)
    status: Mapped[str] = mapped_column(String(30), default="REQUESTED", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_by: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    artifact_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    artifact_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

class ExportRequestEvent(Base):
    __tablename__ = "export_request_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    export_request_id: Mapped[int] = mapped_column(ForeignKey("export_requests.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    prior_state: Mapped[str] = mapped_column(String(30))
    resulting_state: Mapped[str] = mapped_column(String(30))
    actor: Mapped[str] = mapped_column(String(150))
    rationale: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class DiligenceCase(Base):
    __tablename__ = "diligence_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    purpose: Mapped[str] = mapped_column(Text)
    permitted_use: Mapped[str] = mapped_column(Text)
    jurisdiction_scope_json: Mapped[str] = mapped_column(Text, default="[]")
    scope_exclusions_json: Mapped[str] = mapped_column(Text, default="[]")
    risk_tier: Mapped[str] = mapped_column(String(30), default="STANDARD", index=True)
    status: Mapped[str] = mapped_column(String(40), default="INTAKE", index=True)
    owner: Mapped[str] = mapped_column(String(150))
    reviewer: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    decision: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class PrivateSaleCase(Base):
    __tablename__ = "private_sale_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    seller_entity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("entities.id"), nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(Text)
    permitted_use: Mapped[str] = mapped_column(Text)
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    owner: Mapped[str] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(40), default="EVIDENCE_COLLECTION", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class PrivateSaleGate(Base):
    __tablename__ = "private_sale_gates"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("private_sale_cases.id"), index=True)
    gate_code: Mapped[str] = mapped_column(String(80), index=True)
    fact_class: Mapped[str] = mapped_column(String(80), index=True)
    critical: Mapped[bool] = mapped_column(Boolean, default=True)
    counsel_required: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="NOT_STARTED", index=True)
    exception_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("case_id", "gate_code", name="uq_private_sale_gate"),)

class PrivateSaleGateEvidence(Base):
    __tablename__ = "private_sale_gate_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    gate_id: Mapped[int] = mapped_column(ForeignKey("private_sale_gates.id"), index=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    added_by: Mapped[str] = mapped_column(String(150))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("gate_id", "claim_id", name="uq_private_sale_gate_claim"),)

class PrivateSaleGateEvent(Base):
    __tablename__ = "private_sale_gate_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    gate_id: Mapped[int] = mapped_column(ForeignKey("private_sale_gates.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    prior_state: Mapped[str] = mapped_column(String(40))
    resulting_state: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(150))
    actor_role: Mapped[str] = mapped_column(String(40))
    rationale: Mapped[str] = mapped_column(Text)
    evidence_package_hash: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class SourceDocument(Base):
    __tablename__ = "source_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("entities.id"), nullable=True, index=True)
    publisher: Mapped[str] = mapped_column(String(300), index=True)
    publisher_independence_group: Mapped[str] = mapped_column(String(300), index=True)
    source_rank: Mapped[str] = mapped_column(String(10), index=True)
    source_type: Mapped[str] = mapped_column(String(80), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    document_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("source_url", "content_hash", name="uq_source_document_snapshot"),)

class EvidencePassage(Base):
    __tablename__ = "evidence_passages"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), index=True)
    page: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    section: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    passage: Mapped[str] = mapped_column(Text)
    passage_hash: Mapped[str] = mapped_column(String(64), index=True)
    __table_args__ = (UniqueConstraint("document_id", "passage_hash", name="uq_document_passage"),)

class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    passage_id: Mapped[int] = mapped_column(ForeignKey("evidence_passages.id"), index=True)
    directness: Mapped[float] = mapped_column(Float)
    supports: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("claim_id", "passage_id", name="uq_claim_passage"),)

class CheckResult(Base):
    __tablename__ = "diligence_check_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("diligence_cases.id"), index=True)
    check_code: Mapped[str] = mapped_column(String(100), index=True)
    fact_class: Mapped[str] = mapped_column(String(80), index=True)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(40), default="NOT_STARTED", index=True)
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exception_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("case_id", "check_code", name="uq_case_check"),)

class ReviewSignoff(Base):
    __tablename__ = "review_signoffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("diligence_cases.id"), index=True)
    reviewer: Mapped[str] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(80))
    decision: Mapped[str] = mapped_column(String(40))
    rationale: Mapped[str] = mapped_column(Text)
    scope_json: Mapped[str] = mapped_column(Text, default="[]")
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ConflictCase(Base):
    __tablename__ = "conflict_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    predicate: Mapped[str] = mapped_column(String(120), index=True)
    effective_period: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    materiality: Mapped[str] = mapped_column(String(20), default="MATERIAL", index=True)
    status: Mapped[str] = mapped_column(String(40), default="HUMAN_REVIEW_REQUIRED", index=True)
    selected_claim_id: Mapped[Optional[int]] = mapped_column(ForeignKey("claims.id"), nullable=True)
    reviewer: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class ConflictMember(Base):
    __tablename__ = "conflict_members"
    id: Mapped[int] = mapped_column(primary_key=True)
    conflict_id: Mapped[int] = mapped_column(ForeignKey("conflict_cases.id"), index=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    __table_args__ = (UniqueConstraint("conflict_id", "claim_id", name="uq_conflict_claim"),)

class LegalIdentifier(Base):
    __tablename__ = "legal_identifiers"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    identifier_type: Mapped[str] = mapped_column(String(50), index=True)
    identifier_value: Mapped[str] = mapped_column(String(250), index=True)
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="CANDIDATE", index=True)
    claim_id: Mapped[Optional[int]] = mapped_column(ForeignKey("claims.id"), nullable=True)
    __table_args__ = (UniqueConstraint("identifier_type", "identifier_value", "jurisdiction", name="uq_legal_identifier"),)

class JurisdictionProfile(Base):
    __tablename__ = "jurisdiction_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    jurisdiction: Mapped[str] = mapped_column(String(10), index=True)
    legal_form: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    formation_status: Mapped[str] = mapped_column(String(40), default="UNASSESSED")
    regulatory_status: Mapped[str] = mapped_column(String(40), default="UNASSESSED")
    disclosure_limitations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("entity_id", "jurisdiction", name="uq_entity_jurisdiction"),)

class JurisdictionReviewCase(Base):
    __tablename__ = "jurisdiction_review_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), unique=True, index=True)
    original_country: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    proposed_country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    source_claim_id: Mapped[Optional[int]] = mapped_column(ForeignKey("claims.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="HUMAN_REVIEW_REQUIRED", index=True)
    proposed_by: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class JurisdictionReviewEvent(Base):
    __tablename__ = "jurisdiction_review_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("jurisdiction_review_cases.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    prior_state: Mapped[str] = mapped_column(String(40))
    resulting_state: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(150))
    rationale: Mapped[str] = mapped_column(Text)
    source_claim_id: Mapped[Optional[int]] = mapped_column(ForeignKey("claims.id"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class InstitutionalStructure(Base):
    __tablename__ = "institutional_structures"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    structure_type: Mapped[str] = mapped_column(String(60), index=True)
    strategy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    domicile: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    legal_form: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    vintage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metric_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    metric_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metric_currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    metric_as_of: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="CANDIDATE")
    claim_id: Mapped[Optional[int]] = mapped_column(ForeignKey("claims.id"), nullable=True)

class CaseAuditEvent(Base):
    __tablename__ = "case_audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("diligence_cases.id"), index=True)
    actor: Mapped[str] = mapped_column(String(150))
    action: Mapped[str] = mapped_column(String(80), index=True)
    prior_state_json: Mapped[str] = mapped_column(Text, default="{}")
    resulting_state_json: Mapped[str] = mapped_column(Text, default="{}")
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class IdentityCluster(Base):
    __tablename__ = "identity_clusters"
    id: Mapped[int] = mapped_column(primary_key=True)
    identity_type: Mapped[str] = mapped_column(String(40), index=True)
    canonical_label: Mapped[str] = mapped_column(String(300), index=True)
    status: Mapped[str] = mapped_column(String(30), default="PROPOSED", index=True)
    created_by: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class IdentityMembership(Base):
    __tablename__ = "identity_memberships"
    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("identity_clusters.id"), index=True)
    entity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("entities.id"), nullable=True, index=True)
    contact_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contacts.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="PROPOSED", index=True)
    match_basis_json: Mapped[str] = mapped_column(Text, default="[]")
    confidence: Mapped[float] = mapped_column(Float)
    decided_by: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class EntityAlias(Base):
    __tablename__ = "entity_aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    alias: Mapped[str] = mapped_column(String(300), index=True)
    alias_type: Mapped[str] = mapped_column(String(40), default="OTHER")
    status: Mapped[str] = mapped_column(String(30), default="CANDIDATE")
    claim_id: Mapped[Optional[int]] = mapped_column(ForeignKey("claims.id"), nullable=True)
    __table_args__ = (UniqueConstraint("entity_id", "alias", "alias_type", name="uq_entity_alias"),)

class AuditLedgerEntry(Base):
    __tablename__ = "audit_ledger_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    stream_type: Mapped[str] = mapped_column(String(40), index=True)
    stream_id: Mapped[str] = mapped_column(String(100), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(String(150), index=True)
    actor_role: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    previous_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    correlation_id: Mapped[str] = mapped_column(String(100), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("stream_type", "stream_id", "sequence", name="uq_audit_stream_sequence"),)

class RelationshipAssertion(Base):
    __tablename__ = "relationship_assertions"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    to_entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(80), index=True)
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="HUMAN_REVIEW_REQUIRED", index=True)
    proposed_by: Mapped[str] = mapped_column(String(150))
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    review_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class RelationshipAssertionEvidence(Base):
    __tablename__ = "relationship_assertion_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    relationship_assertion_id: Mapped[int] = mapped_column(ForeignKey("relationship_assertions.id"), index=True)
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), index=True)
    evidence_passage_id: Mapped[Optional[int]] = mapped_column(ForeignKey("evidence_passages.id"), nullable=True)
    __table_args__ = (UniqueConstraint("relationship_assertion_id", "source_document_id", "evidence_passage_id", name="uq_relationship_assertion_evidence"),)

class RelationshipAdjudicationEvent(Base):
    __tablename__ = "relationship_adjudication_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    relationship_assertion_id: Mapped[int] = mapped_column(ForeignKey("relationship_assertions.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    prior_state: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    resulting_state: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(150))
    rationale: Mapped[str] = mapped_column(Text)
    evidence_package_hash: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class RegistryIdentifierCandidate(Base):
    __tablename__ = "registry_identifier_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), index=True)
    identifier_type: Mapped[str] = mapped_column(String(40), index=True)
    identifier_value: Mapped[str] = mapped_column(String(250), index=True)
    legal_name: Mapped[str] = mapped_column(String(300))
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    registry_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), index=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    match_state: Mapped[str] = mapped_column(String(40), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    reasons_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="PENDING_REVIEW", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("entity_id", "identifier_type", "identifier_value", name="uq_entity_registry_identifier_candidate"),)

class IdentifierAdjudicationEvent(Base):
    __tablename__ = "identifier_adjudication_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("registry_identifier_candidates.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    prior_state: Mapped[str] = mapped_column(String(40))
    resulting_state: Mapped[str] = mapped_column(String(40))
    reviewer: Mapped[str] = mapped_column(String(150))
    rationale: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class DiligenceCheckEvidence(Base):
    __tablename__ = "diligence_check_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("diligence_check_results.id"), index=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    added_by: Mapped[str] = mapped_column(String(150))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("check_id", "claim_id", name="uq_check_claim_evidence"),)

class DiligenceCheckAdjudicationEvent(Base):
    __tablename__ = "diligence_check_adjudication_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("diligence_check_results.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    prior_state: Mapped[str] = mapped_column(String(40))
    resulting_state: Mapped[str] = mapped_column(String(40))
    reviewer: Mapped[str] = mapped_column(String(150))
    rationale: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

def install_ledger_guards(target_engine) -> None:
    if target_engine.dialect.name=="sqlite":
        with target_engine.begin() as connection:
            connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS audit_ledger_no_update BEFORE UPDATE ON audit_ledger_entries BEGIN SELECT RAISE(ABORT, 'audit ledger is append-only'); END")
            connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS audit_ledger_no_delete BEFORE DELETE ON audit_ledger_entries BEGIN SELECT RAISE(ABORT, 'audit ledger is append-only'); END")

def init_db() -> None:
    PRIVATE_ROOT.mkdir(parents=True,exist_ok=True)
    Base.metadata.create_all(engine)
    install_ledger_guards(engine)
    if engine.dialect.name=="sqlite" and engine.url.database and engine.url.database!=":memory:":
        database_path=Path(engine.url.database)
        if database_path.exists():os.chmod(database_path,0o600)
