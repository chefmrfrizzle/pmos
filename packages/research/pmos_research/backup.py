from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import uuid
from datetime import datetime,timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from .audit_ledger import verify_ledger

class BackupSafetyError(RuntimeError):pass

def _inside(path:Path,parent:Path)->bool:
    try:path.relative_to(parent);return True
    except ValueError:return False

def sha256_file(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()

def encrypted_storage_active()->bool:
    if platform.system()=="Darwin" and Path("/usr/bin/fdesetup").exists():
        result=subprocess.run(["/usr/bin/fdesetup","status"],capture_output=True,text=True,timeout=10,check=False)
        return result.returncode==0 and "FileVault is On" in result.stdout
    return os.getenv("PMOS_ENCRYPTED_STORAGE_ATTESTATION","").casefold()=="true"

def sqlite_path_from_url(db_url:str)->Path:
    url=make_url(db_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database==":memory:":raise BackupSafetyError("backup currently requires a file-backed SQLite database")
    path=Path(url.database).expanduser().resolve()
    if not path.is_file() or path.is_symlink():raise BackupSafetyError("source database is missing or unsafe")
    return path

def verify_sqlite_database(path:Path)->dict:
    engine=create_engine(f"sqlite:///{path}",future=True);factory=sessionmaker(bind=engine)
    try:
        with sqlite3.connect(f"file:{path}?mode=ro",uri=True) as connection:
            integrity=connection.execute("PRAGMA integrity_check").fetchone()[0]
        with factory() as audit_db:
            ledger=verify_ledger(audit_db)
    finally:engine.dispose()
    return {"integrity":integrity,"ledger":ledger}

def create_private_backup(db_url:str,repo_root:Path,backup_root:Path|None=None,require_encrypted_storage:bool=True)->dict:
    source=sqlite_path_from_url(db_url);repo=repo_root.resolve()
    if _inside(source,repo):raise BackupSafetyError("source database is inside the public repository")
    if require_encrypted_storage and not encrypted_storage_active():raise BackupSafetyError("encrypted storage could not be verified")
    root=(backup_root or (source.parent.parent/"backups" if source.parent.name=="datastore" else source.parent/"backups")).expanduser()
    if root.exists() and root.is_symlink():raise BackupSafetyError("backup root cannot be a symlink")
    root=root.resolve();root.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(root,0o700)
    if _inside(root,repo):raise BackupSafetyError("backup root is inside the public repository")
    source_check=verify_sqlite_database(source)
    if source_check["integrity"]!="ok" or not source_check["ledger"]["valid"]:raise BackupSafetyError("source integrity or audit ledger verification failed")
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");target=root/f"{source.stem}-{stamp}-{uuid.uuid4().hex[:8]}.db";manifest=target.with_suffix(".manifest.json")
    try:
        with sqlite3.connect(f"file:{source}?mode=ro",uri=True) as origin,sqlite3.connect(target) as destination:origin.backup(destination)
        os.chmod(target,0o600);target_check=verify_sqlite_database(target)
        if target_check["integrity"]!="ok" or not target_check["ledger"]["valid"]:raise BackupSafetyError("backup integrity or audit ledger verification failed")
        digest=sha256_file(target);payload={"classification":"PMOS PRIVATE — DO NOT DISTRIBUTE","created_at":datetime.now(timezone.utc).isoformat(),"source_file":source.name,"backup_file":target.name,"bytes":target.stat().st_size,"sha256":digest,"sqlite_integrity":target_check["integrity"],"audit_ledger_entries":target_check["ledger"]["entries"],"audit_ledger_valid":target_check["ledger"]["valid"],"encrypted_storage_verified":require_encrypted_storage}
        manifest.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8");os.chmod(manifest,0o600)
        return {"target":target,"manifest":manifest,"metadata":payload}
    except Exception:
        if target.exists():target.unlink()
        if manifest.exists():manifest.unlink()
        raise

def verify_backup_manifest(manifest_path:Path,repo_root:Path)->dict:
    manifest=manifest_path.expanduser().resolve();repo=repo_root.resolve()
    if not manifest.is_file() or manifest.is_symlink() or _inside(manifest,repo) or manifest.stat().st_size>65536:raise BackupSafetyError("backup manifest is missing or unsafe")
    try:metadata=json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError,UnicodeDecodeError) as exc:raise BackupSafetyError("backup manifest is invalid") from exc
    name=metadata.get("backup_file","")
    if Path(name).name!=name or metadata.get("classification")!="PMOS PRIVATE — DO NOT DISTRIBUTE":raise BackupSafetyError("backup manifest classification or filename is invalid")
    target=(manifest.parent/name).resolve()
    if not target.is_file() or target.is_symlink() or target.parent!=manifest.parent:raise BackupSafetyError("backup artifact is missing or unsafe")
    if target.stat().st_size!=metadata.get("bytes") or sha256_file(target)!=metadata.get("sha256"):raise BackupSafetyError("backup size or hash does not match manifest")
    check=verify_sqlite_database(target)
    if check["integrity"]!="ok" or not check["ledger"]["valid"]:raise BackupSafetyError("backup database or ledger verification failed")
    return {"target":target,"manifest":manifest,"metadata":metadata,"verification":check}

def restore_private_backup(manifest_path:Path,target_path:Path,repo_root:Path,require_encrypted_storage:bool=True)->dict:
    verified=verify_backup_manifest(manifest_path,repo_root);target=target_path.expanduser()
    if target.exists() or target.is_symlink():raise BackupSafetyError("restore target must not already exist")
    target=target.resolve();repo=repo_root.resolve()
    if _inside(target,repo):raise BackupSafetyError("restore target is inside the public repository")
    if require_encrypted_storage and not encrypted_storage_active():raise BackupSafetyError("encrypted storage could not be verified")
    parent=target.parent
    if parent.exists() and parent.is_symlink():raise BackupSafetyError("restore directory cannot be a symlink")
    parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:
        with sqlite3.connect(f"file:{verified['target']}?mode=ro",uri=True) as origin,sqlite3.connect(target) as destination:origin.backup(destination)
        os.chmod(target,0o600);check=verify_sqlite_database(target)
        if check["integrity"]!="ok" or not check["ledger"]["valid"] or sha256_file(target)!=verified["metadata"]["sha256"]:raise BackupSafetyError("restored database does not match verified backup")
        return {"target":target,"sha256":verified["metadata"]["sha256"],"ledger_entries":check["ledger"]["entries"]}
    except Exception:
        if target.exists():target.unlink()
        raise
