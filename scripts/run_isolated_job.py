#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"packages/research"))
from pmos_research.runtime_isolation import apply_resource_limits,sanitized_environment

JOBS={
    "corroboration":"run_corroboration_jobs.py",
    "source-discovery":"discover_case_sources.py",
    "source-retrieval":"retrieve_source_candidates.py",
    "pdf-requeue":"requeue_pdf_candidates.py",
    "identity-audit":"audit_identity_matches.py",
    "lei-research":"research_lei_candidates.py",
    "ledger-verify":"verify_audit_ledger.py",
    "public-check":"public_release_check.py",
}

def main()->int:
    parser=argparse.ArgumentParser(description="Run an allowlisted PMOS job with a sanitized environment and resource limits.")
    parser.add_argument("job",choices=sorted(JOBS));parser.add_argument("job_args",nargs=argparse.REMAINDER)
    args=parser.parse_args()
    if any(x in {";","&&","||"} or "\x00" in x for x in args.job_args):parser.error("invalid job argument")
    command=[sys.executable,str(ROOT/"scripts"/JOBS[args.job]),*args.job_args]
    return subprocess.run(command,cwd=ROOT,env=sanitized_environment(),preexec_fn=apply_resource_limits,check=False).returncode

if __name__=="__main__":raise SystemExit(main())
