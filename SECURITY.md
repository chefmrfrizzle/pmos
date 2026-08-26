# Security

Primary threats are accidental Git/deployment leakage, secrets, client-side exposure, unsafe imports, SSRF, malicious HTML, formula injection, path traversal, and incorrect identity merges.

`scripts/public_release_check.py` fails closed on private paths, archives, databases, spreadsheets, keys, likely secrets, large exports, and email-bearing CSV files. Run it before staging, committing, or deploying. Private services bind locally by default. Importers must preserve raw values, sanitize spreadsheet formulas on export, reject paths outside the configured import root, and queue ambiguous identity matches for review. Crawlers allow only credential-free public HTTP(S), validate DNS and every redirect, fail closed when robots rules are unavailable, reject oversized/non-HTML responses, strip executable HTML, and rate-limit per host.

## Current private-API boundary

Entity and claim routes fail closed unless `PMOS_ENABLE_PRIVATE_API=1`, accept loopback clients only, and require a strong `PMOS_DEV_API_TOKEN`. This is local development isolation—not production authentication. These routes must never be deployed publicly. Production private functionality is blocked until OIDC with MFA, deny-by-default role and object authorization, CSRF/session protections, rate limits, purpose/tenant constraints, and server-side audit identity are implemented and tested.

## Adjudication and exports

High-risk case approval requires independent maker-checker review. Material identity, ownership, regulatory, authority, fund-manager, or domicile conflicts block readiness. Case actions append actor, before/after state, rationale, and server timestamp; a production database must additionally deny application-level update/delete on the audit ledger and add tamper-evident chaining.

Exports resolve beneath `PMOS_PRIVATE_ROOT`, reject repository and symlink escape, neutralize spreadsheet formulas, use owner-only permissions, and emit a classified hash manifest. Authorization, approval, expiry, and encrypted delivery remain mandatory before multi-user production use.

## Remaining assurance gates

- scan staged blobs, Git history, browser bundles, source maps, deployment manifests, screenshots, dependencies, and SBOM before release
- pin/revalidate crawler peer IPs and cap streamed/decompressed data to mitigate DNS rebinding and decompression attacks
- cap import file size, archive expansion, rows, columns, cells, runtime, and batch quotas; encrypt private storage
- complete external threat modeling, penetration testing, privacy retention/deletion, and incident-response exercises before institutional deployment
