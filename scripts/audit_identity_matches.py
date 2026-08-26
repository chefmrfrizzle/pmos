#!/usr/bin/env python3
"""Read-only aggregate shadow audit; never prints private identity values."""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from pmos_research.db import SessionLocal
from pmos_research.identity_audit import shadow_audit

with SessionLocal() as db:print(json.dumps(shadow_audit(db),sort_keys=True))
