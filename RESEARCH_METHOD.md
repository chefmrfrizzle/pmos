# Research method

The deterministic pipeline starts with first-party pages, robots rules, sitemaps and structured metadata, then uses reputable public registries. Every assertion becomes a claim; missing facts remain missing. Snapshots are content-addressed, changes create review work, and history is never overwritten. Jobs are bounded, checkpointed, retry with backoff, and isolate failures by institution.

Machine-written or generic pages are not treated as inherently authoritative. Source specificity, named authorship, primary documents, corroboration, freshness, and exact supporting passages contribute separately to confidence.

Private source rows generate provenance-linked candidate claims only. Deterministic resolution auto-links exact evidence; ambiguous names stay separate and enter review.

Official-web research validates public HTTP(S) targets and every redirect against private/local addresses, fails closed when robots rules are unavailable, rate-limits per host, limits response size and content type, and records bounded job outcomes. A successful fetch creates evidence; only predicate-specific matching can create a `SUPPORTED` claim. `VERIFIED` remains a human promotion.

A supported identity assertion creates four linked records: the immutable claim, ranked `SourceDocument`, bounded `EvidencePassage`, and `ClaimEvidence` link with directness. Page-level retrieval is insufficient. Passage extraction must find the institution’s identity tokens in the title or bounded body context; otherwise the job enters review. The passage, offsets/section, document hash, publisher independence group, retrieval time, and extractor version remain inspectable.

Official-institution homepages are S1 self-description. They can support public identity but cannot independently verify ownership/control, regulatory standing, transaction authority, comparable AUM, reputation, or an institutional relationship.

GLEIF is treated as S2 recognized market infrastructure. Search results create `RegistryIdentifierCandidate` records and structured evidence passages; result order never determines identity. Deterministic comparison produces `PROBABLE_MATCH`, `POSSIBLE_MATCH`, `CONFLICT`, or `REQUIRES_REVIEW`. No candidate populates `LegalIdentifier` automatically. Acceptance requires a probable registry match, separately supported official identity evidence, maker-checker approval, and a new specialist-verified claim while preserving the candidate claim.
