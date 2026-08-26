# Research method

The deterministic pipeline starts with first-party pages, robots rules, sitemaps and structured metadata, then uses reputable public registries. Every assertion becomes a claim; missing facts remain missing. Snapshots are content-addressed, changes create review work, and history is never overwritten. Jobs are bounded, checkpointed, retry with backoff, and isolate failures by institution.

Machine-written or generic pages are not treated as inherently authoritative. Source specificity, named authorship, primary documents, corroboration, freshness, and exact supporting passages contribute separately to confidence.

Private source rows generate provenance-linked candidate claims only. Deterministic resolution auto-links exact evidence; ambiguous names stay separate and enter review.

Official-web research validates public HTTP(S) targets and every redirect against private/local addresses, fails closed when robots rules are unavailable, rate-limits per host, limits response size and content type, and records bounded job outcomes. A successful fetch creates evidence; only predicate-specific matching can create a `SUPPORTED` claim. `VERIFIED` remains a human promotion.
