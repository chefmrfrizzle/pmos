# Data model

Core nodes include people, organizations, funds, families, offices, allocators, fiduciaries, advisers, service providers, collections, assets, and opportunities. Relationships are typed graph edges with source, confidence, verification state, and first/last-seen timestamps. Claims preserve subject, predicate, value, source metadata, extractor, evidence hash, confidence, and lifecycle state. Import batches retain source file, original row, normalization, and resolution decisions.

Resolution states are `EXACT_MATCH`, `PROBABLE_MATCH`, `POSSIBLE_MATCH`, `CONFLICT`, and `REQUIRES_REVIEW`; only exact matches are safe to auto-link.

Private imports use `ImportBatch`, `RawImportRow`, and `ResolutionDecision`. Every non-empty physical row retains its original values, normalized mapping, source coordinates, hash, import time, and disposition. Import-derived claims stay `CANDIDATE`; they are private-source evidence, not public verification, and never enter the deployed demo.

Institutional diligence adds `DiligenceCase`, mandatory `CheckResult` records, `SourceDocument` snapshots, exact `EvidencePassage` records, claim-to-passage links, `ConflictCase` members, `ReviewSignoff`, and case audit events. Legal identifiers and jurisdiction profiles are stored separately from display names.

`JurisdictionReviewCase` preserves an invalid original country value and tracks a proposed ISO alpha-2 correction without rewriting the entity. `PROPOSE_CORRECTION` requires a qualifying evidence-hashed country, jurisdiction, or domicile claim for the same entity. `APPROVE_CORRECTION` requires a different reviewer; only that transition updates the entity. `JurisdictionReviewEvent` retains the full decision history.

`EvidenceReviewBatch` freezes a specialist queue selection into a deterministic manifest hash. Its items preserve the candidate status, predicate, passage hash, source-document hash, and eligibility state observed at assignment time. The batch never copies raw private rows and never promotes a claim. Manifest integrity is independently recalculated by the API and control-assurance job.

`EvidenceReviewDecisionBinding` binds each passage adjudication event to its frozen batch item. Support approval is valid only when proposal and approval reference the same item, their evidence hashes still match the source chain, and maker-checker controls pass. This prevents decisions from drifting across assignments or silently inheriting changed evidence.

`EvidenceReviewAssignment` grants a named reviewer a single role on one frozen batch for a bounded period. Assignment, expiry, revocation, and batch closure remain auditable through assignment events and the hash-chain ledger. `EvidenceReviewDecisionAuthorization` records the exact grant used by each decision so later revocation does not erase the historical authorization basis.

`IdentityCluster` and `IdentityMembership` represent proposed, accepted, or rejected canonicalization without deleting source entities. `EntityAlias` retains sourced names. Institutional structures distinguish legal entities and vehicles and preserve metric type, currency, basis, and date rather than collapsing AUM, AUA, NAV, commitments, target close, and final close.

`IdentityReviewBatch` freezes a scoped priority queue into a deterministic privacy-safe manifest. `IdentityReviewBatchItem` retains the queue-item version, resolution state, priority, queue type, and a one-way fingerprint of the exact identity pair. `IdentityReviewDecisionBinding` requires proposal and approval to use the same frozen item; it stores no private names or raw source rows.

`IdentityReviewAssignment` grants a named reviewer a bounded role and expiry on one identity batch. Assignment events retain issuance, expiry, revocation, and closure. `IdentityReviewDecisionAuthorization` links every decision to the exact grant used, allowing assurance to prove authorization at decision time even after the grant is revoked.

An entity-level verification label is a coverage roll-up. Only assertion-level evidence can be supported or corroborated, and only a scoped human review can become specialist-verified. A single official webpage never verifies an entire entity.

`RelationshipAssertion` is the controlled graph-edge model. It retains effective dates, jurisdiction, sensitivity, proposer/reviewer separation, review rationale, and links to source documents and exact passages. `RelationshipAdjudicationEvent` preserves proposal, deferral, rejection, and approval history with a deterministic evidence-package hash. Sensitive ownership/control/trustee edges require dispositive primary evidence; graph display must never treat a legacy or candidate edge as specialist-verified. Confidence is derived transparently from source rank, independence, freshness, scope, and passage integrity.

`RelationshipResearchCandidate` is a pre-assertion queue item created only when a versioned rule finds a controlled relationship phrase and a full registered counterparty name in an exact passage. It retains the source/target IDs, suggested type, passage, reasons, and conservative confidence. Review may reject, defer, or promote it into a separate assertion; discovery never writes a graph edge or verified relationship.

`RelationshipMentionCandidate` preserves a bounded named object following a controlled relationship phrase when no registered target matches. Its lifecycle is `ENTITY_RESOLUTION_REQUIRED`, `TARGET_LINKED`, `DEFERRED`, or `REJECTED`. Linking requires a distinct registered target and produces only a `HUMAN_REVIEW_REQUIRED` relationship candidate; it never auto-registers an institution.

`PrivateSaleCase` binds an asset entity, optional seller entity, jurisdiction, purpose, permitted use, and owner. Nine `PrivateSaleGate` records cover seller identity, authority to sell, provenance, attribution, restitution, cultural property, export, sanctions, and condition. `PrivateSaleGateEvidence` links only qualifying exact-evidence claims; `PrivateSaleGateEvent` preserves maker-checker and counsel decisions. Transaction readiness is derived from gates and never stored as an unexplainable score.

`AuditLedgerEntry` is an append-only, per-stream hash chain containing authenticated actor ID/role, action, canonical payload, correlation ID, server timestamp, predecessor hash, and event hash. Identity, diligence-case, and relationship decisions write separate replayable streams. SQLite guards reject updates/deletes; chain verification detects altered payloads or predecessor links.

`RegistryIdentifierCandidate` separates a registry search result from an accepted `LegalIdentifier`. Each candidate retains the legal name, jurisdiction, registry status, structured S2 document, exact structured passage, deterministic match state/confidence/reasons, and review state. `IdentifierAdjudicationEvent` preserves maker-checker transitions. Acceptance creates a new specialist-verified claim and identifier; it never rewrites the original candidate claim.

`DiligenceCheckEvidence` links scoped case procedures to assertion-level claims. `DiligenceCheckAdjudicationEvent` records evidence submission, completion/exception proposals, independent approvals, rejections, rationale, and state transitions. Check sufficiency is computed from qualifying claim status, source rank, publisher independence, and unresolved conflicts. Exceptions remain visible readiness restrictions; they never silently count as GREEN.

The institutional dossier is a read model, not a new truth store. It assembles a scoped `DiligenceCase`, exact claim/passage/source chains, per-fact freshness, check sufficiency, recorded conflicts, potential material contradictions, accepted identifiers, candidate identifiers, specialist signoffs, limitations, and readiness. Potential conflicts never select a winner or mutate claim status. Every private dossier is classified and can only be returned by the authenticated, universe-scoped API.

Identity review packets intentionally exclude `RawImportRow.original_row_json` and direct contact secrets. They expose only the two identity candidates, deterministic reasons, priority, version, and scoped evidence metadata needed for review. A match proposal requires content-addressed evidence belonging to an identity under review; approval requires a different reviewer and the identical evidence digest.

`ResearchSourceCandidate` separates same-domain document discovery from evidence retrieval. It records the discovered URL, source page, document classification, target predicates, deterministic score, and lifecycle state. `ResearchDocumentSnapshot` stores bounded normalized text and a content hash outside the public application. `ResearchPassageCandidate` links an exact immutable passage to one possible predicate and always begins `HUMAN_REVIEW_REQUIRED`. Discovery, retrieval, and passage extraction never create a factual `Claim`.

`SourceRetrievalAttempt` is the append-only operational history for a source candidate. It stores a monotonic attempt number, stable outcome/error class, optional HTTP status, retryability, and bounded next-attempt timestamp. It excludes document bodies, credentials, and raw exception messages. Control assurance verifies sequence continuity and retry-state consistency.

`UniverseCoverageRun` stores a content-hashed aggregate assessment with no entity names. It separates registry representation, metadata completeness, exact identity evidence, diligence-case inclusion, and decision readiness across required institutional categories and geographic regions. Historical runs remain available for coverage trend and change review.

PDF snapshots use the same source/snapshot models as HTML, while each extracted `EvidencePassage.page` preserves its PDF page number. The raw PDF is not stored in the application database or public repository; the source document retains its URL and content-addressed normalized-text snapshot for review.

`SourceChangeEvent` immutably links the prior and resulting document snapshots with both hashes, text similarity, added/removed token counts, detection time, and review state. Unchanged retrievals remain explicit `UNCHANGED` events. Changed sources begin `HUMAN_REVIEW_REQUIRED`. `SourceChangeReviewEvent` preserves acknowledgements, deferrals, and escalations without rewriting either snapshot or changing downstream claims.

`ResearchPassageAdjudicationEvent` is the append-only decision history for passage candidates. A maker may propose an exact normalized substring already present in the passage. A different reviewer must approve the identical value before PMOS appends a `SUPPORTED` claim and `ClaimEvidence` link. Rejection and deferral create no claim. `MARK_CONFLICT` creates a conflict-state claim and links it with contradictory material claims in a `ConflictCase`; it never selects a winner.

`ClaimCheckRoutingCandidate` is the controlled bridge between an assertion and a case procedure. It is generated only for a supported-or-better claim whose predicate exactly matches an open check’s fact class. A route remains `PENDING_REVIEW` until a reviewer attaches, rejects, or defers it. `ClaimCheckRoutingEvent` preserves that decision. Attachment changes a check only to `EVIDENCE_COLLECTED`; it cannot approve or complete the check.

`ControlAssuranceRun` stores an aggregate-only, canonical JSON control report, its SHA-256 hash, pass/fail state, control and exception totals, actor, and timestamp. The corresponding ledger event anchors the report hash. Reports contain populations and exception counts, never entity names, claim values, passages, contact details, or source URLs.

`ExportRequest` defines one case-scoped `DILIGENCE_DOSSIER` JSON export, exact permitted purpose, requester, expiry, independent approval, executor, artifact filename, and hash. `ExportRequestEvent` preserves request, decision, and execution transitions. Export state is single-use: only `APPROVED` can execute, and successful execution becomes `EXPORTED`.
