# Runbook

Bootstrap with `make bootstrap`, seed with `make seed`, and run locally with `make dev`. Research jobs are scoped by universe and can be restarted from checkpoints. Back up the private root to encrypted local storage. For a suspected leak: stop deployment, revoke credentials, preserve evidence, remove public access, audit Git history, rotate affected secrets, and do not resume until the safety checker and manual review pass.
