from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base
from pmos_research.incident_exercise import run_public_leak_exercise
from pmos_research.security_readiness import build_security_readiness

def test_synthetic_leak_exercise_detects_contains_and_recovers(tmp_path,monkeypatch):
    repo=Path(__file__).resolve().parents[3];engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    import pmos_research.incident_exercise as exercise_module
    monkeypatch.setattr(exercise_module,"encrypted_storage_active",lambda:True)
    with factory() as db:
        run,report=run_public_leak_exercise(db,repo,tmp_path/"private-exercises","security-operator");db.commit()
        assert run.status=="PASS" and run.detection_count==5 and run.containment_verified and run.recovery_verified
        assert report["history_leak_detected"] and all(report["detections"].values())
        readiness=build_security_readiness(db,repo,{"public_release_check":True,"backend_tests":True,"web_build":True,"browser_tests":True},backup_verified=True)
        control=next(x for x in readiness["controls"] if x["control"]=="monitoring_and_incident_response")
        assert control["status"]=="EXERCISED"
    assert not any((tmp_path/"private-exercises").iterdir())
