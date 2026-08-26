#!/usr/bin/env python3
from pathlib import Path
import argparse, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/research"))
from pmos_research.db import init_db, SessionLocal, ImportBatch
from pmos_research.importers import import_csv, import_xlsx

ap=argparse.ArgumentParser(); ap.add_argument("--input-dir",required=True); args=ap.parse_args()
root=Path(args.input_dir).expanduser().resolve()
if not root.is_dir():raise SystemExit("Input directory does not exist or is not a directory")
init_db(); total=0; failed=[]
for p in sorted(root.rglob("*")):
    if p.suffix.lower() not in {".csv",".xlsx"}:continue
    resolved=p.resolve()
    if root not in resolved.parents:failed.append((p.name,"path escaped input root"));continue
    with SessionLocal() as s:
        try:
            total+=(import_csv(s,resolved) if p.suffix.lower()==".csv" else import_xlsx(s,resolved));s.commit()
        except Exception as exc:
            s.rollback();failed.append((p.name,type(exc).__name__))
with SessionLocal() as s:
    batches=s.query(ImportBatch).all()
    print(f"Reconciled {sum(x.rows_seen for x in batches)} non-empty source rows across {len(batches)} source files")
    print(f"Materialized {sum(x.rows_imported for x in batches)} identity rows; preserved {sum(x.rows_support for x in batches)} header, preamble, or support rows")
if failed:
    print(f"{len(failed)} source files failed without stopping the remaining import: "+", ".join(f"{name} ({error})" for name,error in failed))
    raise SystemExit(1)
