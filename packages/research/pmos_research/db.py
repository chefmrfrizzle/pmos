from __future__ import annotations
import os
from typing import Optional
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, Float, DateTime, ForeignKey, UniqueConstraint
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
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    verification_status: Mapped[str] = mapped_column(String(50), default="candidate")
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

def init_db() -> None:
    PRIVATE_ROOT.mkdir(parents=True,exist_ok=True)
    Base.metadata.create_all(engine)
