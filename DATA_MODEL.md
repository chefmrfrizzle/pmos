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

`DiligenceCheckEvidence` links scoped case procedures to assertion-level claims. `DiligenceCheckAdjudicationEvent` records evidence submission, completion/exception proposals, independent approvals, rejections, rationale, and state transitions. Check sufficiency is computed from qualifying claim status, source rank, publisher independence, and unresolved conflicts. Exceptions remain visible readiness restrictions; they never silently count as GREEN.

The institutional dossier is a read model, not a new truth store. It assembles a scoped `DiligenceCase`, exact claim/passage/source chains, per-fact freshness, check sufficiency, recorded conflicts, potential material contradictions, accepted identifiers, candidate identifiers, specialist signoffs, limitations, and readiness. Potential conflicts never select a winner or mutate claim status. Every private dossier is classified and can only be returned by the authenticated, universe-scoped API.

Identity review packets intentionally exclude `RawImportRow.original_row_json` and direct contact secrets. They expose only the two identity candidates, deterministic reasons, priority, version, and scoped evidence metadata needed for review. A match proposal requires content-addressed evidence belonging to an identity under review; approval requires a different reviewer and the identical evidence digest.

`ResearchSourceCandidate` separates same-domain document discovery from evidence retrieval. It records the discovered URL, source page, document classification, target predicates, deterministic score, and lifecycle state. `ResearchDocumentSnapshot` stores bounded normalized text and a content hash outside the public application. `ResearchPassageCandidate` links an exact immutable passage to one possible predicate and always begins `HUMAN_REVIEW_REQUIRED`. Discovery, retrieval, and passage extraction never create a factual `Claim`.

PDF snapshots use the same source/snapshot models as HTML, while each extracted `EvidencePassage.page` preserves its PDF page number. The raw PDF is not stored in the application database or public repository; the source document retains its URL and content-addressed normalized-text snapshot for review.

`SourceChangeEvent` immutably links the prior and resulting document snapshots with both hashes, text similarity, added/removed token counts, detection time, and review state. Unchanged retrievals remain explicit `UNCHANGED` events. Changed sources begin `HUMAN_REVIEW_REQUIRED`. `SourceChangeReviewEvent` preserves acknowledgements, deferrals, and escalations without rewriting either snapshot or changing downstream claims.

`ResearchPassageAdjudicationEvent` is the append-only decision history for passage candidates. A maker may propose an exact normalized substring already present in the passage. A different reviewer must approve the identical value before PMOS appends a `SUPPORTED` claim and `ClaimEvidence` link. Rejection and deferral create no claim. `MARK_CONFLICT` creates a conflict-state claim and links it with contradictory material claims in a `ConflictCase`; it never selects a winner.

`ClaimCheckRoutingCandidate` is the controlled bridge between an assertion and a case procedure. It is generated only for a supported-or-better claim whose predicate exactly matches an open check’s fact class. A route remains `PENDING_REVIEW` until a reviewer attaches, rejects, or defers it. `ClaimCheckRoutingEvent` preserves that decision. Attachment changes a check only to `EVIDENCE_COLLECTED`; it cannot approve or complete the check.
