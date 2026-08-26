#!/usr/bin/env python3
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packages/research"))
from pmos_research.backup import BackupSafetyError,restore_private_backup

parser=argparse.ArgumentParser();parser.add_argument("--manifest",type=Path,required=True);parser.add_argument("--target",type=Path,required=True);parser.add_argument("--allow-unverified-storage",action="store_true");args=parser.parse_args()
try:
    result=restore_private_backup(args.manifest,args.target,Path(__file__).resolve().parents[1],not args.allow_unverified_storage);print(json.dumps({"restored_file":result["target"].name,"sha256":result["sha256"],"ledger_entries":result["ledger_entries"],"valid":True},sort_keys=True))
except BackupSafetyError as exc:raise SystemExit(str(exc))
