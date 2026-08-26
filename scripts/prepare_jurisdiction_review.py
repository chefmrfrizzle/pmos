#!/usr/bin/env python3
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from pmos_research.db import SessionLocal,init_db
from pmos_research.jurisdiction_review import enqueue_invalid_jurisdictions

init_db()
with SessionLocal() as db:
    result=enqueue_invalid_jurisdictions(db);db.commit()
print(json.dumps(result,sort_keys=True))
