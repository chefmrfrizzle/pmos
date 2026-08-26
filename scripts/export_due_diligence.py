#!/usr/bin/env python3
"""Create a local, classified export outside the public worktree."""
from pathlib import Path
import sys, csv, hashlib, json, os
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/research"))
from pmos_research.db import init_db, SessionLocal, Entity, PRIVATE_ROOT

ROOT=Path(__file__).resolve().parents[1]
out=(PRIVATE_ROOT/"exports").resolve()
if out == ROOT or ROOT in out.parents:
    raise SystemExit("refusing to export inside the public repository")
out.mkdir(parents=True,exist_ok=True,mode=0o700)
if out.is_symlink() or PRIVATE_ROOT.resolve() not in out.parents:
    raise SystemExit("export path escapes PMOS_PRIVATE_ROOT")
path=out/"counterparties.csv"
def safe(value):
    text="" if value is None else str(value)
    return "'"+text if text[:1] in {"=","+","-","@","\t","\r"} else text
with SessionLocal() as s, path.open("w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["id","name","universe","country","city","official_url","verification_status","last_verified","evidence_confidence","strategic_priority","useful_wedge"])
    count=0
    for e in s.query(Entity).order_by(Entity.strategic_priority.desc(),Entity.name).all():
        w.writerow([safe(x) for x in [e.id,e.name,e.universe,e.country,e.city,e.official_url,e.verification_status,e.last_verified,e.evidence_confidence,e.strategic_priority,e.useful_wedge]])
        count+=1
os.chmod(path,0o600)
digest=hashlib.sha256(path.read_bytes()).hexdigest()
manifest=path.with_suffix(".manifest.json")
manifest.write_text(json.dumps({"classification":"PMOS PRIVATE — DO NOT DISTRIBUTE","rows":count,"sha256":digest,"schema_version":1},indent=2)+"\n",encoding="utf-8")
os.chmod(manifest,0o600)
print(path)
