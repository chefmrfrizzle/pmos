#!/usr/bin/env python3
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"packages/research"))
from pmos_research.db import SessionLocal,init_db
from pmos_research.universe_coverage import build_universe_coverage,persist_coverage
init_db()
with SessionLocal() as db:
    report=build_universe_coverage(db);run=persist_coverage(db,report);db.commit();print(json.dumps({"status":report["status"],"report_hash":run.report_hash,"totals":report["totals"],"missing_required_universe_count":len(report["missing_required_universes"]),"missing_required_region_count":len(report["missing_required_regions"]),"unmapped_country_count":report["unmapped_country_count"]},sort_keys=True))
