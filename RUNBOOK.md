# Runbook

Bootstrap with `make bootstrap`, seed with `make seed`, and run locally with `make dev`. Research jobs are scoped by universe and can be restarted from checkpoints. Back up the private root to encrypted local storage. For a suspected leak: stop deployment, revoke credentials, preserve evidence, remove public access, audit Git history, rotate affected secrets, and do not resume until the safety checker and manual review pass.

For institutional OIDC mode, set a non-empty `PMOS_TENANT_ID` and map `PMOS_OIDC_TENANT_CLAIM` plus `PMOS_OIDC_PURPOSES_CLAIM` to IdP claims. The default claim URIs are `https://pmos.example/tenant` and `https://pmos.example/purposes`. Send `X-PMOS-Purpose` on every private request. Provision exact approved purpose strings; do not grant wildcard purpose in institutional tokens. A mismatch is an access denial, not a warning. Run one private datastore and service per tenant.

Configure the IdP to issue access tokens with `jti` and `auth_time`. PMOS defaults to a 15-minute maximum token age and a 12-hour maximum authentication age; configured values are clamped to one hour and 24 hours respectively. During an emergency revocation, SHA-256 hash the affected `jti`, add only the 64-character lowercase hash to comma-separated `PMOS_REVOKED_JTI_HASHES` in the private deployment configuration, roll every private API instance, and verify a 401 for that token. Remove expired hashes through a documented access-review change. Never place a raw token, raw `jti`, or revocation configuration in the public repository.

Run allowlisted batch jobs with resource and environment isolation where possible, for example `./.venv/bin/python scripts/run_isolated_job.py corroboration --limit 10`. The launcher does not provide a network firewall; production workers still require a low-privilege service account/container and an operating-system egress allowlist. Set `PMOS_ALLOWED_HOSTS` to the exact private API hostnames and enforce distributed rate limits at the institutional gateway.

Run `python scripts/run_isolated_job.py universe-coverage` after registry expansion, corroboration, adjudication, or case completion. The command persists a content-hashed aggregate report and ledger anchor; it emits totals only. Authorized all-universe administrators may inspect the latest report at `GET /universe-coverage` with `coverage:read`. Treat `registered`, `identity_evidence_backed`, `diligence_case_open`, and `decision_ready` as distinct populations. Missing regions or zero readiness are remediation queues, not permission to invent institutions or weaken evidence thresholds.

For a private import, set `PMOS_PRIVATE_ROOT` and `PMOS_DB_URL` to paths outside the repository, then run `python scripts/import_private.py --input-dir /external/private/imports`. Use a new database URL for schema revisions instead of overwriting an earlier datastore. The importer is idempotent by file hash, isolates source-file failures, and prints aggregate reconciliation only. Review every non-exact resolution before promotion.

Import limits can only be adjusted within hard safety ceilings through `PMOS_IMPORT_MAX_FILE_BYTES`, `PMOS_IMPORT_MAX_ROWS`, `PMOS_IMPORT_MAX_COLUMNS`, `PMOS_IMPORT_MAX_CELL_CHARS`, `PMOS_IMPORT_MAX_TOTAL_CELLS`, and `PMOS_IMPORT_MAX_XLSX_UNCOMPRESSED`. Do not raise limits merely to force a malformed source through; quarantine and inspect it first.

Prepare persistent review and corroboration queues with `python scripts/prepare_adjudication_queue.py`. Run first-party work in bounded batches with `python scripts/run_corroboration_jobs.py --limit 10`. Robots denial or retrieval failure is a recorded outcome, never a reason to bypass controls or mark a claim verified.

After official identity corroboration, discover review-only diligence documents with `python scripts/discover_case_sources.py --limit 10 --per-entity 20`. Retrieve a bounded cohort with `python scripts/retrieve_source_candidates.py --limit 5`. Both commands emit aggregate outcomes only. Retrieval can create sanitized document snapshots and exact candidate passages; it cannot create or complete claims/checks. Review `RETRIEVED_REVIEW_REQUIRED`, `UNSUPPORTED_CONTENT_TYPE`, `BLOCKED_ROBOTS`, `BLOCKED_SIZE`, and `RETRY_REQUIRED` separately. Never reset a terminal outcome merely to increase coverage.

Retrieval writes an append-only attempt record containing only bounded operational metadata: attempt number, stable outcome/error class, HTTP status when available, retryability, and next-attempt time. Transient HTTP/network failures use 15/30-minute bounded exponential backoff and stop after three attempts; permanent HTTP responses enter `HTTP_ERROR_REVIEW_REQUIRED`. Run `python scripts/run_isolated_job.py source-retry-requeue --limit 5` only after backoff elapses. `--include-legacy` is an explicit, ledgered migration escape hatch for pre-attempt-history records and must not be routine operations.

When deterministic phrase coverage improves, re-run extraction over stored snapshots with `python scripts/run_isolated_job.py passage-reextraction --limit 25`. This job performs no network access and queues only missing exact-passage candidates for human review. It never creates claims, changes check status, or promotes evidence. Review yield by document type and target predicate before expanding phrase rules; broad words such as `board`, `company`, or `investments` are intentionally insufficient.

After installing bounded PDF support, requeue legacy `.pdf` candidates exactly once with `python scripts/requeue_pdf_candidates.py --limit 10`. The command accepts only same-domain URL paths ending in `.pdf` that were previously `UNSUPPORTED_CONTENT_TYPE` and writes a capability-migration ledger event. Do not use it for malformed, encrypted, oversized, blocked, or non-PDF sources. PDF extraction limits are bounded by `PMOS_MAX_PDF_BYTES`, `PMOS_PDF_MAX_PAGES`, `PMOS_PDF_MAX_PAGE_CHARS`, and `PMOS_PDF_MAX_TEXT_CHARS`.

Run stale-source comparison with `python scripts/reverify_sources.py --limit 5 --min-age-hours 168`. Use zero age only for controlled testing. Changed documents appear at `GET /evidence-review/source-changes`; reviewers may `ACKNOWLEDGE`, `DEFER`, or `ESCALATE` through the scoped action route. Acknowledgement documents review only—it does not update or reject any claim. Reassess affected passage candidates and checks through their own workflows.

Run `python scripts/assure_private_controls.py` before an adjudication batch, sensitive export, backup handoff, or private deployment. It exits nonzero on any exception and records a content-hashed aggregate report plus ledger anchor. Review the latest report through authenticated `GET /assurance/latest` with `assurance:read`. A zero-population control proves no contradictory live record exists; it does not substitute for workflow tests or future populated sampling.

Run `python scripts/run_isolated_job.py security-readiness` for the consolidated release and operating-control assessment. Review its content-hashed result through admin-only `GET /security-readiness`. Do not interpret green tests, a valid backup, or a passing assurance run as private production approval when the matrix still reports `NOT_CONFIGURED`, `NOT_STAFFED`, `NOT_EXERCISED`, or `NOT_EVIDENCED` controls.

Run `python scripts/run_isolated_job.py relationship-discovery --limit 100` after exact-passage retrieval. Inspect candidates through authenticated `GET /relationship-candidates`. A researcher may reject, defer, or `PROPOSE_ASSERTION`; the latter creates only a controlled assertion using the same exact passage. Never treat a candidate, co-mention, or single S1 source as a verified edge. Continue through independent relationship review, and require dispositive S0 evidence for ownership, control, beneficial ownership, or trustee relationships.

For a proposed assertion, use `evidence_controls.corroboration_gaps` as a bounded remediation queue. Resolve hash, scope, freshness, and semantic failures before sourcing additional material. `SECOND_INDEPENDENT_PUBLISHER_REQUIRED` means content-distinct evidence, not a second URL carrying the same document. `DISPOSITIVE_S0_REQUIRED` cannot be cleared with press coverage or counterparty self-description.

Before counting two publishers, propose the observed domain and its ultimate publisher-control group at authenticated `POST /publisher-independence` with exact ownership/control evidence. Review pending work at `GET /publisher-independence`; a different `REVIEWER` or `ADMIN` with `evidence:approve` must approve the unchanged package. Until approval, relationship packets show `PUBLISHER_INDEPENDENCE_REVIEW_REQUIRED`. Never infer independence from different hostnames, brands, or mastheads alone.

Diligence-check sufficiency and two-source private-sale gate packets expose `unreviewed_publisher_count`, `duplicate_content_count`, approved `independence_groups`, and per-document source factors. Clear publisher governance before proposing completion or pass; do not use an exception merely to avoid a missing independence assessment.

Inspect unmatched named objects through authenticated `GET /relationship-mentions`. Never create a new institution merely to clear this queue. Confirm legal identity through the identity workflow first, then propose the existing target and continue through relationship-candidate review only after independent approval.

Use `PROPOSE_TARGET`—not direct linkage—with a distinct registered target and `identity:write`. The mention becomes `TARGET_PROPOSED` without creating a candidate. A different `REVIEWER` or `ADMIN` with `identity:approve` must use `APPROVE_TARGET` against the unchanged identity package; `REJECT_TARGET` preserves the rejected version and returns the mention to `ENTITY_RESOLUTION_REQUIRED`. Legacy `LINK_TARGET` is not accepted.

First freeze `ENTITY_RESOLUTION_REQUIRED` work with `POST /relationship-mentions/batches`, then have an `ADMIN` assign a named `RESEARCHER` through the batch assignment route. Include that batch ID with `PROPOSE_TARGET`. Freeze a new `TARGET_PROPOSED` batch, assign a different `REVIEWER`, and include the new batch ID with `APPROVE_TARGET` or `REJECT_TARGET`. Assignments expire after the configured bounded period and may be revoked; close superseded batches instead of reusing stale manifests.

Reviewers retrieve exact assigned packets with `GET /relationship-mentions?review_batch_id=<id>`. Calls without a valid frozen batch, an assignment for the authenticated subject, an unexpired assignment, or the matching assignment role fail closed. Administrators should use batch manifests and aggregate counts for staffing; do not assign themselves merely to browse mention text.

For aggregate queue preparation, run `python scripts/run_isolated_job.py mention-review-batches --status ENTITY_RESOLUTION_REQUIRED --limit-per-universe 100`. The job freezes one content-addressed batch per represented universe and prints counts and batch IDs only. It does not print mention text, assign staff, propose targets, or adjudicate anything.

Copy `config/retention-policy.example.json` to encrypted private storage, have the accountable policy owner and counsel choose and approve the jurisdiction-appropriate periods, then set `PMOS_RETENTION_POLICY_PATH` to that external regular file. Run `python scripts/run_isolated_job.py retention-assessment`. The report is aggregate and deletion-free. `REVIEW_REQUIRED` means records meet the age rule and require separate disposition review; it is not deletion authorization. `NOT_CONFIGURED` must not be bypassed. Place class-wide legal holds through the governed retention module before any future disposition workflow; this phase intentionally provides no purge command.

Private control and ledger scripts select their datastore only through `PMOS_DB_URL`; they reject unsupported command-line arguments. Set the absolute external SQLite URL in the command environment and confirm the reported populations are consistent with the intended datastore before relying on the result.

Prepare jurisdiction exceptions with `python scripts/run_isolated_job.py jurisdiction-review-prepare`. Invalid non-empty country values are preserved in `HUMAN_REVIEW_REQUIRED` cases. A researcher may propose a correction only from a qualifying evidence-hashed jurisdiction claim; a different reviewer must approve it before the entity changes. Use authenticated `GET /jurisdiction-review` and `POST /jurisdiction-review/{case_id}/actions`. Never repair an ambiguous jurisdiction directly in SQL.

Freeze a prioritized identity population with `python scripts/run_isolated_job.py identity-review-freeze --universe imported_private --min-priority 85 --limit 100`. The manifest contains queue IDs, versions, states, priorities, and one-way identity-pair fingerprints—not names, raw rows, contacts, or evidence excerpts. Create/read batches through authenticated `/identity-review/batches`. Every identity action must include the batch ID; pair drift, version drift, manifest tampering, and cross-batch approval fail closed. The batch does not authorize access by itself and never merges source records.

An `ADMIN` with `identity:assign` must grant a named `RESEARCHER` or `REVIEWER` access to one frozen identity batch for 1–168 hours. Only an assigned `REVIEWER` may approve. Revoke through `/identity-review/assignments/{id}/revoke`, close through `/identity-review/batches/{id}/close`, and run `python scripts/run_isolated_job.py identity-review-expire` before review sessions. Every decision records both its frozen item and the exact unexpired authorization used.

## Governed dossier exports

The legacy broad CSV command is disabled. Create a single-case JSON export request through authenticated `POST /exports/requests`; its purpose must exactly match the case’s permitted use. A different `EXPORTER` or `ADMIN` must approve through `/exports/requests/{id}/actions`, and a passing control-assurance run from the preceding 24 hours is mandatory. Execute an approved request locally with `python scripts/execute_approved_export.py --request-id ID --actor ACTOR`. The executor cannot be the requester. Files are written only under `PMOS_PRIVATE_ROOT/exports` on verified encrypted storage with `0600` permissions and a classified hash manifest. Expired, rejected, already-used, self-approved, unassured, repository-targeted, or symlinked exports fail closed. There is no browser download route.

Use authenticated `GET /evidence-review/passages?review_batch_id=<id>` to inspect exact passage packets from the caller’s active assigned batch. Universe-level `evidence:review` without a matching assignment is insufficient. `PROPOSE_SUPPORT` requires `evidence:write`, an exact passage substring, substantive rationale, and the current status. `APPROVE_SUPPORT` requires `evidence:approve`, a different reviewer, the identical value, and `SUPPORT_PROPOSED`. Use `MARK_CONFLICT` when material claims disagree; do not force a support transition. The resulting supported claim still needs check-level evidence attachment and independent check approval.

Each passage packet reports passage/snapshot hash integrity, exact snapshot containment, first-party source-rank eligibility, predicate-specific freshness, open conflicts, existing assertions, and prior specialist decisions. Use `predicate`, `min_confidence`, and `evidence_state=ELIGIBLE|BLOCKED|STALE|CONFLICT` to triage. Support and conflict-claim creation fail closed when the evidence chain is tampered, stale, missing its snapshot, or not S1. An open material conflict blocks ordinary support and must remain in the conflict workflow; rejection and deferral remain available so broken evidence can be dispositioned safely.

Before assigning a specialist review session, freeze its population with `python scripts/run_isolated_job.py evidence-review-freeze --universe pensions --limit 50`. The resulting manifest commits to the criteria, candidate state, predicate, passage hash, document hash, and evidence eligibility state. Authenticated reviewers can create or inspect the same object through `POST /evidence-review/batches` and `GET /evidence-review/batches/{id}`. A frozen batch is a review-control artifact, not an approval or factual assertion; assurance fails if its manifest is altered.

Every passage action must include `review_batch_id`. Proposal, rejection, deferral, and conflict actions fail when the current candidate state or evidence hashes differ from the frozen item. Approval must use the exact batch that contains the linked proposal; creating a replacement batch cannot authorize an earlier proposal. Freeze a new batch instead of bypassing a stale assignment.

An `ADMIN` with `evidence:assign` must assign each reviewer through `POST /evidence-review/batches/{id}/assignments`. Assignments name one reviewer, bind one role, expire within 1–168 hours, and cannot be self-assigned. Revoke authority through `POST /evidence-review/assignments/{id}/revoke`; retire the entire session through `POST /evidence-review/batches/{id}/close`, which revokes every active assignment. Passage actions require an active, unexpired assignment whose role matches the authenticated principal. Approval requires an assigned `REVIEWER` or `COUNSEL`.

Run `python scripts/run_isolated_job.py evidence-review-expire` before an adjudication session and from a bounded scheduler. It records an explicit expiry event for every elapsed active grant. Control assurance fails if an elapsed grant remains active or if assignment history, separation, role, or terminal-state evidence is incomplete.

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

Use authenticated `GET /identity-review?review_batch_id=<id>` to request packets from the caller’s active assigned frozen batch and `POST /identity-review/{item_id}/actions` to act. Universe-level identity permission does not grant queue-wide packet browsing. Proposals and approvals must include the scoped evidence IDs shown in the packet; approval must use the same evidence package as the proposal. Never work around a 409 stale-version or 422 evidence-scope response. Filter assigned work by documented risk with `resolution_state=PROBABLE_MATCH` and an explicit `min_priority`; freeze batch criteria separately when preparing the cohort. The packet reports distinct-pair, active-cluster, and exact-proposal controls. A proposal fails if either candidate belongs to another proposed or accepted cluster; approval succeeds only for the exact reviewed pair. Never clear an overlap merely to process the queue. `GET /diligence-cases/{case_id}/dossier` returns the classified review dossier and requires the separate `dossiers:read` permission.

Create relationship assertions through authenticated `POST /relationship-review` using an enumerated relationship type and exact passage IDs scoped to the two entities. Inspect the queue at `GET /relationship-review`; filter by status, relationship type, sensitivity, and minimum evidence confidence. `POST /relationship-review/{id}/actions` supports `APPROVE`, `REJECT`, and `DEFER`. Approval requires `relationships:approve`, a different reviewer, the unchanged proposal evidence package, fresh hash-valid passages, and policy-sufficient source rank/independence. Sensitive ownership/control/trustee assertions require dispositive S0 evidence. Ordinary edges require S0 or two independent qualifying publishers including S1/S2. Confidence is an inspectable evidence assessment, never a substitute for specialist judgment.

Open a private-sale case through authenticated `POST /private-sales`; the active purpose must exactly match `permitted_use`, and the principal must be authorized for both asset and seller universes. Inspect it with `GET /private-sales/{id}`. Attach qualifying claim IDs at `/private-sales/{id}/gates/{gate_id}/evidence`, then use the gate action route for `PROPOSE_PASS`, `PROPOSE_EXCEPTION`, `MARK_BLOCKED`, `APPROVE`, `APPROVE_EXCEPTION`, or `REJECT`. Authority, export, and sanctions require S0 evidence. Provenance, attribution, restitution, and cultural-property gates require S0 or two independent S1/S2 groups. Restitution, cultural-property, and export approvals require a different `COUNSEL` or `ADMIN`. Critical exceptions remain not-clear in readiness; never turn an exception into a silent pass.

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

The job does not initialize or migrate schema. It first verifies the existing source ledger and SQLite integrity, uses SQLite’s online backup operation, sets `0700/0600` permissions, verifies the copied ledger/integrity, hashes the artifact, creates a classified manifest, and only then appends a backup event to the source ledger. `--allow-unverified-storage` is development-only and must not be used for institutional data.

Exercise recovery with `python scripts/run_isolated_job.py restore-drill`. The job selects the latest verified manifest, restores it only to a newly created encrypted temporary directory outside the public repository, verifies the artifact hash, SQLite integrity, and audit ledger, removes the temporary restored database, and records only aggregate proof. A successful local SQLite drill does not prove recovery for a future production PostgreSQL deployment.

Exercise public-leak detection and containment with `python scripts/run_isolated_job.py incident-exercise`. The job creates an isolated synthetic Git repository outside PMOS, verifies the release gate catches private-path, database, email-bearing CSV, secret, and historical-blob canaries, removes the synthetic compromised repository, and proves a clean recovery repository passes. No real private value or credential is used. External alert delivery and timed staff response remain separate production evidence requirements.

Verify and restore without overwriting the operating database:

```bash
./.venv/bin/python scripts/verify_private_backup.py --manifest /private/backups/example.manifest.json
./.venv/bin/python scripts/restore_private_backup.py \
  --manifest /private/backups/example.manifest.json \
  --target /private/restore-verification/restored.db
```

Restore targets must be new paths outside the repository. After verification, change `PMOS_DB_URL` only through an approved recovery procedure; never restore over a live database.
