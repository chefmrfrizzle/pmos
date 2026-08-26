# Runbook

Bootstrap with `make bootstrap`, seed with `make seed`, and run locally with `make dev`. Research jobs are scoped by universe and can be restarted from checkpoints. Back up the private root to encrypted local storage. For a suspected leak: stop deployment, revoke credentials, preserve evidence, remove public access, audit Git history, rotate affected secrets, and do not resume until the safety checker and manual review pass.

For a private import, set `PMOS_PRIVATE_ROOT` and `PMOS_DB_URL` to paths outside the repository, then run `python scripts/import_private.py --input-dir /external/private/imports`. Use a new database URL for schema revisions instead of overwriting an earlier datastore. The importer is idempotent by file hash, isolates source-file failures, and prints aggregate reconciliation only. Review every non-exact resolution before promotion.

Prepare persistent review and corroboration queues with `python scripts/prepare_adjudication_queue.py`. Run first-party work in bounded batches with `python scripts/run_corroboration_jobs.py --limit 10`. Robots denial or retrieval failure is a recorded outcome, never a reason to bypass controls or mark a claim verified.
