# Data model

Core nodes include people, organizations, funds, families, offices, allocators, fiduciaries, advisers, service providers, collections, assets, and opportunities. Relationships are typed graph edges with source, confidence, verification state, and first/last-seen timestamps. Claims preserve subject, predicate, value, source metadata, extractor, evidence hash, confidence, and lifecycle state. Import batches retain source file, original row, normalization, and resolution decisions.

Resolution states are `EXACT_MATCH`, `PROBABLE_MATCH`, `POSSIBLE_MATCH`, `CONFLICT`, and `REQUIRES_REVIEW`; only exact matches are safe to auto-link.
