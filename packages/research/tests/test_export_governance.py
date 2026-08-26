import json,subprocess,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pmos_research.control_assurance import persist_assurance_run,run_control_assurance
from pmos_research.db import Base,Entity,ExportRequest
from pmos_research.diligence import open_case
from pmos_research.export_governance import ExportGovernanceError,adjudicate_export_request,execute_export,request_dossier_export

def test_export_requires_exact_purpose_recent_assurance_independent_approval_and_executor(tmp_path):
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    repo=tmp_path/"repo";repo.mkdir();private=tmp_path/"private";private.mkdir()
    with factory() as db:
        entity=Entity(name="Private Institution",canonical_name="private institution",universe="family_office");db.add(entity);db.flush();case=open_case(db,entity.id,"default","assessment","internal diligence","owner")
        persist_assurance_run(db,run_control_assurance(db));db.commit()
        with pytest.raises(ExportGovernanceError):request_dossier_export(db,case.id,"external marketing","requester")
        request=request_dossier_export(db,case.id,"internal diligence","requester");db.commit()
        with pytest.raises(ExportGovernanceError):adjudicate_export_request(db,request.id,"APPROVE","requester","Attempting self approval of private export","REQUESTED")
        adjudicate_export_request(db,request.id,"APPROVE","exporter","Independent approval for the scoped internal diligence dossier","REQUESTED");db.commit()
        with pytest.raises(ExportGovernanceError):execute_export(db,request.id,"requester",private,repo,require_encrypted_storage=False)
        result=execute_export(db,request.id,"operations",private,repo,require_encrypted_storage=False)
        assert result["artifact"].stat().st_mode&0o777==0o600 and result["manifest"].stat().st_mode&0o777==0o600
        metadata=json.loads(result["manifest"].read_text());assert metadata["request_id"]==request.id and metadata["sha256"]==result["sha256"]
        saved=db.get(ExportRequest,request.id);assert saved.status=="EXPORTED" and saved.artifact_name==result["artifact"].name

def test_expired_export_request_fails_closed():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Institution",canonical_name="institution",universe="pension");db.add(entity);db.flush();case=open_case(db,entity.id,"default","assessment","internal","owner");persist_assurance_run(db,run_control_assurance(db));db.commit()
        request=request_dossier_export(db,case.id,"internal","requester");request.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
        with pytest.raises(ExportGovernanceError):adjudicate_export_request(db,request.id,"APPROVE","exporter","Independent approval after expiry must fail","REQUESTED")

def test_legacy_broad_export_command_is_disabled():
    root=Path(__file__).resolve().parents[3];result=subprocess.run([sys.executable,str(root/"scripts/export_due_diligence.py")],capture_output=True,text=True)
    assert result.returncode!=0 and "Broad direct export is disabled" in result.stderr
