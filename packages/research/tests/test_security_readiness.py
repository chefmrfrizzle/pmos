from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pmos_research.control_assurance import persist_assurance_run,run_control_assurance
from pmos_research.db import Base,SecurityReadinessRun
from pmos_research.security_readiness import build_security_readiness,persist_security_readiness

def test_readiness_fails_closed_and_never_claims_test_evidence_is_production_readiness(tmp_path):
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        assurance=run_control_assurance(db);persist_assurance_run(db,assurance);db.flush();technical={"public_release_check":True,"backend_tests":True,"web_build":True,"browser_tests":True};report=build_security_readiness(db,tmp_path,technical,environment={"PMOS_AUTH_MODE":"disabled"},backup_verified=True)
        assert report["status"]=="NOT_PRODUCTION_READY" and report["summary"]["PROVEN"]>=5
        states={x["control"]:x["status"] for x in report["controls"]};assert states["production_oidc_mfa_tenant_configuration"]=="NOT_CONFIGURED" and states["reviewer_operating_assignments"]=="NOT_STAFFED" and states["external_security_review"]=="NOT_EVIDENCED"
        run=persist_security_readiness(db,report);db.commit();assert db.get(SecurityReadinessRun,run.id).report_hash==run.report_hash and "secret" not in run.report_json.casefold()

def test_control_assurance_detects_readiness_report_tampering(tmp_path):
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        report=build_security_readiness(db,tmp_path,{"public_release_check":False,"backend_tests":False,"web_build":False,"browser_tests":False},environment={},backup_verified=False);run=persist_security_readiness(db,report);run.report_hash="0"*64;db.flush();assurance=run_control_assurance(db);control=next(x for x in assurance["controls"] if x["control"]=="security_readiness_report_integrity");assert assurance["status"]=="FAIL" and control["exceptions"]==1
