#!/usr/bin/env python3
from pathlib import Path
import sys, csv
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/research"))
from pmos_research.db import init_db, SessionLocal, Entity

init_db(); out=Path("data/private/exports"); out.mkdir(parents=True,exist_ok=True)
path=out/"counterparties.csv"
with SessionLocal() as s, path.open("w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["id","name","universe","country","city","official_url","verification_status","last_verified","evidence_confidence","strategic_priority","useful_wedge"])
    for e in s.query(Entity).order_by(Entity.strategic_priority.desc(),Entity.name).all():
        w.writerow([e.id,e.name,e.universe,e.country,e.city,e.official_url,e.verification_status,e.last_verified,e.evidence_confidence,e.strategic_priority,e.useful_wedge])
print(path)
