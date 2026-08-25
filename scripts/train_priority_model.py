#!/usr/bin/env python3
from pathlib import Path
import sys, joblib
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/research"))
from pmos_research.db import init_db, SessionLocal, Entity, Outcome
from sklearn.linear_model import LogisticRegression
import numpy as np

positive={"replied","meeting","warm_intro","pilot","client","investor","partner"}
init_db()
with SessionLocal() as s:
    rows=[]
    for o in s.query(Outcome).all():
        e=s.get(Entity,o.entity_id)
        if not e: continue
        X=[e.capital_access,e.asset_access,e.network_leverage,e.private_asset_fit,e.engagement_probability,e.immediate_value_fit,e.evidence_confidence]
        rows.append((X,1 if o.outcome in positive else 0))
if len(rows)<20 or len(set(y for _,y in rows))<2:
    raise SystemExit("Need at least 20 labeled outcomes containing both positive and negative examples before training.")
X=np.array([x for x,_ in rows]); y=np.array([y for _,y in rows])
model=LogisticRegression(max_iter=2000).fit(X,y)
Path("data/private/models").mkdir(parents=True,exist_ok=True)
joblib.dump(model,"data/private/models/priority_model.joblib")
print("Saved local priority model")
