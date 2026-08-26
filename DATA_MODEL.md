# Data model

Core nodes include people, organizations, funds, families, offices, allocators, fiduciaries, advisers, service providers, collections, assets, and opportunities. Relationships are typed graph edges with source, confidence, verification state, and first/last-seen timestamps. Claims preserve subject, predicate, value, source metadata, extractor, evidence hash, confidence, and lifecycle state. Import batches retain source file, original row, normalization, and resolution decisions.

Resolution states are `EXACT_MATCH`, `PROBABLE_MATCH`, `POSSIBLE_MATCH`, `CONFLICT`, and `REQUIRES_REVIEW`; only exact matches are safe to auto-link.

Private imports use `ImportBatch`, `RawImportRow`, and `ResolutionDecision`. Every non-empty physical row retains its original values, normalized mapping, source coordinates, hash, import time, and disposition. Import-derived claims stay `CANDIDATE`; they are private-source evidence, not public verification, and never enter the deployed demo.
