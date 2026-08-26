from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pmos_research.backup import create_private_backup
from pmos_research.db import Base
from pmos_research.restore_drill import run_restore_drill
from pmos_research.security_readiness import build_security_readiness

def test_restore_drill_restores_verifies_removes_and_records(tmp_path,monkeypatch):
    repo=Path(__file__).resolve().parents[3];source=tmp_path/"private"/"datastore"/"pmos.db";source.parent.mkdir(parents=True);engine=create_engine(f"sqlite:///{source}");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    backup=create_private_backup(f"sqlite:///{source}",repo,tmp_path/"private"/"backups",require_encrypted_storage=False)
    import pmos_research.backup as backup_module
    import pmos_research.restore_drill as drill_module
    monkeypatch.setattr(backup_module,"encrypted_storage_active",lambda:True);monkeypatch.setattr(drill_module,"encrypted_storage_active",lambda:True)
    with factory() as db:
        run,report=run_restore_drill(db,backup["manifest"],repo,"recovery-operator");db.commit()
        assert run.status=="PASS" and run.temporary_restore_removed and run.encrypted_storage_verified
        assert report["audit_ledger_valid"] and not any("path" in key.casefold() for key in report) and "/" not in str(report)
        readiness=build_security_readiness(db,repo,{"public_release_check":True,"backend_tests":True,"web_build":True,"browser_tests":True},backup_verified=True)
        control=next(x for x in readiness["controls"] if x["control"]=="restore_drill")
        assert control["status"]=="PROVEN"
    assert not any((tmp_path/"private"/"restore-drills").iterdir())
