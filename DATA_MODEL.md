# Data model

Core nodes include people, organizations, funds, families, offices, allocators, fiduciaries, advisers, service providers, collections, assets, and opportunities. Relationships are typed graph edges with source, confidence, verification state, and first/last-seen timestamps. Claims preserve subject, predicate, value, source metadata, extractor, evidence hash, confidence, and lifecycle state. Import batches retain source file, original row, normalization, and resolution decisions.

Resolution states are `EXACT_MATCH`, `PROBABLE_MATCH`, `POSSIBLE_MATCH`, `CONFLICT`, and `REQUIRES_REVIEW`; only exact matches are safe to auto-link.

Private imports use `ImportBatch`, `RawImportRow`, and `ResolutionDecision`. Every non-empty physical row retains its original values, normalized mapping, source coordinates, hash, import time, and disposition. Import-derived claims stay `CANDIDATE`; they are private-source evidence, not public verification, and never enter the deployed demo.

Institutional diligence adds `DiligenceCase`, mandatory `CheckResult` records, `SourceDocument` snapshots, exact `EvidencePassage` records, claim-to-passage links, `ConflictCase` members, `ReviewSignoff`, and case audit events. Legal identifiers and jurisdiction profiles are stored separately from display names.

`IdentityCluster` and `IdentityMembership` represent proposed, accepted, or rejected canonicalization without deleting source entities. `EntityAlias` retains sourced names. Institutional structures distinguish legal entities and vehicles and preserve metric type, currency, basis, and date rather than collapsing AUM, AUA, NAV, commitments, target close, and final close.

An entity-level verification label is a coverage roll-up. Only assertion-level evidence can be supported or corroborated, and only a scoped human review can become specialist-verified. A single official webpage never verifies an entire entity.

`RelationshipAssertion` is the controlled graph-edge model. It retains effective dates, jurisdiction, sensitivity, proposer/reviewer separation, review rationale, and links to source documents and exact passages. Sensitive ownership/control/trustee edges require dispositive primary evidence; graph display must never treat a legacy or candidate edge as specialist-verified.

`AuditLedgerEntry` is an append-only, per-stream hash chain containing authenticated actor ID/role, action, canonical payload, correlation ID, server timestamp, predecessor hash, and event hash. Identity, diligence-case, and relationship decisions write separate replayable streams. SQLite guards reject updates/deletes; chain verification detects altered payloads or predecessor links.

`RegistryIdentifierCandidate` separates a registry search result from an accepted `LegalIdentifier`. Each candidate retains the legal name, jurisdiction, registry status, structured S2 document, exact structured passage, deterministic match state/confidence/reasons, and review state. `IdentifierAdjudicationEvent` preserves maker-checker transitions. Acceptance creates a new specialist-verified claim and identifier; it never rewrites the original candidate claim.
