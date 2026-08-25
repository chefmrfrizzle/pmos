#!/usr/bin/env python3
from pathlib import Path
import argparse, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/research"))
from pmos_research.db import init_db, SessionLocal
from pmos_research.importers import import_csv, import_xlsx

ap=argparse.ArgumentParser(); ap.add_argument("--input-dir",required=True); args=ap.parse_args()
root=Path(args.input_dir).expanduser(); init_db(); total=0
with SessionLocal() as s:
    for p in sorted(root.rglob("*")):
        if p.suffix.lower()==".csv": total+=import_csv(s,p)
        elif p.suffix.lower()==".xlsx": total+=import_xlsx(s,p)
    s.commit()
print(f"Imported {total} rows/records into the private local database")
