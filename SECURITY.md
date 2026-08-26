# Security

Primary threats are accidental Git/deployment leakage, secrets, client-side exposure, unsafe imports, SSRF, malicious HTML, formula injection, path traversal, and incorrect identity merges.

`scripts/public_release_check.py` fails closed on private paths, archives, databases, spreadsheets, keys, likely secrets, large exports, and email-bearing CSV files. Run it before staging, committing, or deploying. Private services bind locally by default. Importers must preserve raw values, sanitize spreadsheet formulas on export, reject paths outside the configured import root, and queue ambiguous identity matches for review. Crawlers allow only credential-free public HTTP(S), validate DNS and every redirect, fail closed when robots rules are unavailable, reject oversized/non-HTML responses, strip executable HTML, and rate-limit per host.

## Current private-API boundary

Entity and claim routes are absent unless `PMOS_AUTH_MODE` explicitly selects `local` or `oidc`. Local mode is loopback-only and requires a strong `PMOS_DEV_API_TOKEN`. OIDC mode validates a fixed RS256 algorithm, same-issuer HTTPS JWKS, issuer, audience, expiry/issued-at, MFA, approved roles, action permissions, and universe-level object scope. Successful reads append actor, action, result metadata, and correlation ID to the audit ledger. The API also enforces trusted hosts, a bounded request body, per-process principal/IP rate limits, no-store responses, and defensive browser headers. Institutional deployments must set `PMOS_ALLOWED_HOSTS` explicitly and add gateway-level distributed rate limits.

The private API must never be deployed in the public Vercel project. An institutional deployment still requires enterprise IdP provisioning, browser session and CSRF controls, purpose/tenant claims, rate limits, session revocation, and operational access reviews. Backend OIDC enforcement is necessary but is not the complete production access-control program.

## Adjudication and exports

High-risk case approval requires independent maker-checker review. Material identity, ownership, regulatory, authority, fund-manager, or domicile conflicts block readiness. Case actions append actor, before/after state, rationale, and server timestamp. Production must preserve these controls while moving identity from local development tokens to authenticated server-side principals.

The local ledger is SHA-256 hash-chained per decision stream and SQLite installs fail-closed triggers that reject ledger updates and deletes. `scripts/verify_audit_ledger.py` replays every reachable stream and fails on changed payloads, broken predecessor hashes, or changed event hashes. Production PostgreSQL must additionally isolate ledger insert permissions from operational roles, sign periodic roots with an external key, and export roots to independent retention.

Sensitive relationship assertions (`OWNS`, `CONTROLS`, beneficial ownership, and trustee roles) require a dispositive S0 source and independent reviewer. Other relationship verification requires S0 or two independent S1–S3 sources including S1/S2. Names, domains, and private source rows never prove ownership.

Exports resolve beneath `PMOS_PRIVATE_ROOT`, reject repository and symlink escape, neutralize spreadsheet formulas, use owner-only permissions, and emit a classified hash manifest. Authorization, approval, expiry, and encrypted delivery remain mandatory before multi-user production use.

## Remaining assurance gates

- scan staged blobs, Git history, browser bundles, source maps, deployment manifests, screenshots, dependencies, and SBOM before release
- pin/revalidate crawler peer IPs and enforce an operating-system egress policy to mitigate DNS rebinding
- enforce an operating-system egress firewall and run research workers under a dedicated low-privilege account/container
- complete external threat modeling, penetration testing, privacy retention/deletion, and incident-response exercises before institutional deployment

The crawler accepts only default HTTP/HTTPS ports, ignores process proxy variables, revalidates every redirect, applies separate connection/read/pool timeouts, and caps declared, downloaded, and decompressed response bytes while streaming. DNS-to-connected-peer pinning and an operating-system egress firewall remain required defense-in-depth for production research workers.

Private imports reject symlinks, unsupported extensions, empty/oversized files, excessive rows/columns/cells, oversized cell values, malformed XLSX archives, excessive archive members, encrypted members, dangerous expansion ratios, and excessive uncompressed workbook size. Limits are bounded even when environment-configured. New provenance uses logical source IDs instead of machine-specific absolute paths, and local SQLite files are set to owner-read/write permissions. Per-process timeouts, encrypted-volume enforcement, and external quarantine orchestration remain deployment controls.

Private backups use SQLite’s consistent backup API rather than copying a live database file. Source and backup integrity plus audit chains are verified, artifacts/manifests are owner-only, manifests contain classification/size/hash/ledger metadata, and backup creation is logged after success. macOS production runs require FileVault; other platforms require an explicit encrypted-storage attestation. Restore verification never overwrites an existing database or accepts a repository path, symlink, hash mismatch, corrupt SQLite file, or broken ledger.

Allowlisted research jobs may be launched through `scripts/run_isolated_job.py`. The launcher builds a narrow environment, removes proxy and credential variables, rejects shell control arguments, and applies CPU, file-size, file-descriptor, process, and core-dump limits. These process controls are defense-in-depth, not a substitute for a dedicated worker identity, sandbox/container, DNS/peer pinning, or an operating-system egress firewall.
