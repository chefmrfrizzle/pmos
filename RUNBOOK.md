# Runbook

Bootstrap with `make bootstrap`, seed with `make seed`, and run locally with `make dev`. Research jobs are scoped by universe and can be restarted from checkpoints. Back up the private root to encrypted local storage. For a suspected leak: stop deployment, revoke credentials, preserve evidence, remove public access, audit Git history, rotate affected secrets, and do not resume until the safety checker and manual review pass.

For institutional OIDC mode, set a non-empty `PMOS_TENANT_ID` and map `PMOS_OIDC_TENANT_CLAIM` plus `PMOS_OIDC_PURPOSES_CLAIM` to IdP claims. The default claim URIs are `https://pmos.example/tenant` and `https://pmos.example/purposes`. Send `X-PMOS-Purpose` on every private request. Provision exact approved purpose strings; do not grant wildcard purpose in institutional tokens. A mismatch is an access denial, not a warning. Run one private datastore and service per tenant.

Run allowlisted batch jobs with resource and environment isolation where possible, for example `./.venv/bin/python scripts/run_isolated_job.py corroboration --limit 10`. The launcher does not provide a network firewall; production workers still require a low-privilege service account/container and an operating-system egress allowlist. Set `PMOS_ALLOWED_HOSTS` to the exact private API hostnames and enforce distributed rate limits at the institutional gateway.

For a private import, set `PMOS_PRIVATE_ROOT` and `PMOS_DB_URL` to paths outside the repository, then run `python scripts/import_private.py --input-dir /external/private/imports`. Use a new database URL for schema revisions instead of overwriting an earlier datastore. The importer is idempotent by file hash, isolates source-file failures, and prints aggregate reconciliation only. Review every non-exact resolution before promotion.

Import limits can only be adjusted within hard safety ceilings through `PMOS_IMPORT_MAX_FILE_BYTES`, `PMOS_IMPORT_MAX_ROWS`, `PMOS_IMPORT_MAX_COLUMNS`, `PMOS_IMPORT_MAX_CELL_CHARS`, `PMOS_IMPORT_MAX_TOTAL_CELLS`, and `PMOS_IMPORT_MAX_XLSX_UNCOMPRESSED`. Do not raise limits merely to force a malformed source through; quarantine and inspect it first.

Prepare persistent review and corroboration queues with `python scripts/prepare_adjudication_queue.py`. Run first-party work in bounded batches with `python scripts/run_corroboration_jobs.py --limit 10`. Robots denial or retrieval failure is a recorded outcome, never a reason to bypass controls or mark a claim verified.

After official identity corroboration, discover review-only diligence documents with `python scripts/discover_case_sources.py --limit 10 --per-entity 20`. Retrieve a bounded cohort with `python scripts/retrieve_source_candidates.py --limit 5`. Both commands emit aggregate outcomes only. Retrieval can create sanitized document snapshots and exact candidate passages; it cannot create or complete claims/checks. Review `RETRIEVED_REVIEW_REQUIRED`, `UNSUPPORTED_CONTENT_TYPE`, `BLOCKED_ROBOTS`, `BLOCKED_SIZE`, and `RETRY_REQUIRED` separately. Never reset a terminal outcome merely to increase coverage.

After installing bounded PDF support, requeue legacy `.pdf` candidates exactly once with `python scripts/requeue_pdf_candidates.py --limit 10`. The command accepts only same-domain URL paths ending in `.pdf` that were previously `UNSUPPORTED_CONTENT_TYPE` and writes a capability-migration ledger event. Do not use it for malformed, encrypted, oversized, blocked, or non-PDF sources. PDF extraction limits are bounded by `PMOS_MAX_PDF_BYTES`, `PMOS_PDF_MAX_PAGES`, `PMOS_PDF_MAX_PAGE_CHARS`, and `PMOS_PDF_MAX_TEXT_CHARS`.

Run stale-source comparison with `python scripts/reverify_sources.py --limit 5 --min-age-hours 168`. Use zero age only for controlled testing. Changed documents appear at `GET /evidence-review/source-changes`; reviewers may `ACKNOWLEDGE`, `DEFER`, or `ESCALATE` through the scoped action route. Acknowledgement documents review only—it does not update or reject any claim. Reassess affected passage candidates and checks through their own workflows.

Run `python scripts/assure_private_controls.py` before an adjudication batch, sensitive export, backup handoff, or private deployment. It exits nonzero on any exception and records a content-hashed aggregate report plus ledger anchor. Review the latest report through authenticated `GET /assurance/latest` with `assurance:read`. A zero-population control proves no contradictory live record exists; it does not substitute for workflow tests or future populated sampling.

## Governed dossier exports

The legacy broad CSV command is disabled. Create a single-case JSON export request through authenticated `POST /exports/requests`; its purpose must exactly match the case’s permitted use. A different `EXPORTER` or `ADMIN` must approve through `/exports/requests/{id}/actions`, and a passing control-assurance run from the preceding 24 hours is mandatory. Execute an approved request locally with `python scripts/execute_approved_export.py --request-id ID --actor ACTOR`. The executor cannot be the requester. Files are written only under `PMOS_PRIVATE_ROOT/exports` on verified encrypted storage with `0600` permissions and a classified hash manifest. Expired, rejected, already-used, self-approved, unassured, repository-targeted, or symlinked exports fail closed. There is no browser download route.

Use authenticated `GET /evidence-review/passages` to inspect exact passage packets. `PROPOSE_SUPPORT` requires `evidence:write`, an exact passage substring, substantive rationale, and the current status. `APPROVE_SUPPORT` requires `evidence:approve`, a different reviewer, the identical value, and `SUPPORT_PROPOSED`. Use `MARK_CONFLICT` when material claims disagree; do not force a support transition. The resulting supported claim still needs check-level evidence attachment and independent check approval.

Approved passage claims create review-only routing candidates when an open case check has the same fact class. Inspect them through `GET /evidence-review/routing`; use the separate `evidence:routing:write` permission to `ATTACH`, `REJECT`, or `DEFER`. Attachment is not check approval. Continue through the check evidence-sufficiency and maker-checker workflow before relying on the case result.

## Public release

Build before the final check so compiled browser bundles and source maps are inspected:

```bash
cd apps/web && npm run build && cd ../..
./.venv/bin/python scripts/public_release_check.py
```

Run the safety checker before staging, every commit, every push, and every deployment. It checks the current tree, reachable Git history, and generated browser assets.

## Identity shadow audit and adjudication

Before promoting historical exact matches under a newer resolver policy, run the read-only aggregate audit against the configured private datastore:

```bash
PMOS_DB_URL='sqlite:////absolute/private/path/pmos.db' \
  ./.venv/bin/python scripts/audit_identity_matches.py
```

The command outputs counts and reason categories only. It does not print identity values or mutate decisions. Any `requires_review` result enters adjudication; historical decisions are never rewritten.

Accepted identity matches use two stages: `PROPOSE_MATCH` by the maker, then `APPROVE_MATCH` by a different reviewer. Rejections, conflicts, evidence references, rationale, and prior/resulting states remain append-only events. A stale version must be reloaded instead of overwritten.

Use authenticated `GET /identity-review` to request a bounded, priority-ordered queue and `POST /identity-review/{item_id}/actions` to act. Proposals and approvals must include the scoped evidence IDs shown in the packet; approval must use the same evidence package as the proposal. Never work around a 409 stale-version or 422 evidence-scope response. `GET /diligence-cases/{case_id}/dossier` returns the classified review dossier and requires the separate `dossiers:read` permission.

## Bounded institutional cohort

Open review-first cases across allocator and manager structures without verifying or merging any identity:

```bash
PMOS_DB_URL='sqlite:////absolute/private/path/pmos.db' \
  ./.venv/bin/python scripts/initialize_diligence_cohort.py --per-universe 2
```

Cases begin with mandatory checks in `NOT_STARTED`. Creation is intake, not diligence completion or endorsement.
The initializer also queues official-domain corroboration only for the selected public-registry cohort. Run those jobs explicitly with `scripts/run_corroboration_jobs.py --case-cohort --limit 10`; without the filter the worker processes the oldest pending job globally. Retrieval alone never completes a diligence check.

## Audit ledger

After installing a new ledger schema, create a single aggregate baseline and verify it:

```bash
PMOS_DB_URL='sqlite:////absolute/private/path/pmos.db' \
  ./.venv/bin/python scripts/initialize_audit_ledger.py
PMOS_DB_URL='sqlite:////absolute/private/path/pmos.db' \
  ./.venv/bin/python scripts/verify_audit_ledger.py
```

The baseline does not invent historical actors. SQLite rejects `UPDATE` and `DELETE` against ledger rows. A failed ledger verification is a security incident: stop adjudication/export, preserve the database and logs, and investigate before resuming.

## Evidence-passage backfill

After upgrading an older datastore, bind existing supported official-identity claims to exact passages without changing their status:

```bash
PMOS_DB_URL='sqlite:////absolute/private/path/pmos.db' \
  ./.venv/bin/python scripts/backfill_identity_passages.py
```

Back up the database first. Review `missing_snapshot` and `passage_not_found` outcomes manually; never substitute a generic passage or promote the claim to make reconciliation pass.

## LEI candidate research

Create structured, review-only GLEIF candidates for public-registry diligence cases:

```bash
PMOS_DB_URL='sqlite:////absolute/private/path/pmos.db' \
  ./.venv/bin/python scripts/research_lei_candidates.py --limit 32
```

The command emits aggregate counts only. Candidate order is not precedence. `PROBABLE_MATCH` still requires separate official identity evidence, a maker proposal, and independent approval. Possible, conflicting, or review-required candidates cannot enter the accepted legal-identifier table.

## Diligence-check adjudication

Use authenticated private API routes to inspect `/diligence-cases/{case_id}`, attach claim IDs to a check, propose completion or an exception, and obtain independent approval. Evidence must belong to the case entity and contain exact-passage links. A 409 response means the state, source sufficiency, entity scope, or conflict policy failed; reload and investigate instead of retrying blindly.

`PROPOSE_COMPLETE` and `APPROVE` require source sufficiency. `PROPOSE_EXCEPTION` and `APPROVE_EXCEPTION` preserve the restriction and never create GREEN readiness. Researchers cannot approve their own work. Verify the audit ledger after every adjudication batch.

## Backup and recovery

Create a consistent private SQLite backup only on verified encrypted storage:

```bash
PMOS_DB_URL='sqlite:////absolute/private/path/pmos.db' \
PMOS_PRIVATE_ROOT='/absolute/private/root' \
  ./.venv/bin/python scripts/backup_private.py --backup-root /absolute/private/backups
```

The job verifies the source ledger and SQLite integrity, uses SQLite’s online backup operation, sets `0700/0600` permissions, verifies the copied ledger/integrity, hashes the artifact, creates a classified manifest, and appends a backup event to the source ledger. `--allow-unverified-storage` is development-only and must not be used for institutional data.

Verify and restore without overwriting the operating database:

```bash
./.venv/bin/python scripts/verify_private_backup.py --manifest /private/backups/example.manifest.json
./.venv/bin/python scripts/restore_private_backup.py \
  --manifest /private/backups/example.manifest.json \
  --target /private/restore-verification/restored.db
```

Restore targets must be new paths outside the repository. After verification, change `PMOS_DB_URL` only through an approved recovery procedure; never restore over a live database.
