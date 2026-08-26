#!/usr/bin/env python3
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from pmos_research.db import SessionLocal,init_db
from pmos_research.identity_review_assignment import expire_identity_assignments

init_db()
with SessionLocal() as db:
    result=expire_identity_assignments(db);db.commit()
print(json.dumps(result,sort_keys=True))
