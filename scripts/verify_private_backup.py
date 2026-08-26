#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from pmos_research.backup import BackupSafetyError,verify_backup_manifest

parser=argparse.ArgumentParser();parser.add_argument("--manifest",type=Path,required=True);args=parser.parse_args()
try:
    result=verify_backup_manifest(args.manifest,Path(__file__).resolve().parents[1]);print(json.dumps({"backup_file":result["target"].name,"sha256":result["metadata"]["sha256"],"bytes":result["metadata"]["bytes"],"ledger_entries":result["verification"]["ledger"]["entries"],"valid":True},sort_keys=True))
except BackupSafetyError as exc:raise SystemExit(str(exc))
