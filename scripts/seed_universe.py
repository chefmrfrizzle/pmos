#!/usr/bin/env python3
from pathlib import Path
import sys, yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/research"))
from pmos_research.db import init_db, SessionLocal, Entity
from pmos_research.entity_resolution import canonicalize_name

cfg=yaml.safe_load(Path("config/universes.yaml").read_text())
init_db()
with SessionLocal() as s:
    existing={(e.canonical_name,e.universe) for e in s.query(Entity).all()}
    added=0
    for universe, block in cfg["universes"].items():
        for x in block["entities"]:
            key=(canonicalize_name(x["name"]),universe)
            if key in existing: continue
            s.add(Entity(name=x["name"],canonical_name=key[0],universe=universe,country=x.get("country"),city=x.get("city"),official_url=x.get("url")))
            added+=1
    s.commit()
print(f"Seeded {added} new entities")
