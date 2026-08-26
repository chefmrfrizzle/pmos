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

def init_db() -> None:
    PRIVATE_ROOT.mkdir(parents=True,exist_ok=True)
    Base.metadata.create_all(engine)
