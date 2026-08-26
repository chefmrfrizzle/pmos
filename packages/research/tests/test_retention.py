import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,ImportBatch,RawImportRow
from pmos_research.retention import RetentionError,adjudicate_legal_hold,build_retention_assessment,load_retention_policy,persist_retention_assessment,propose_class_legal_hold

def _policy(path:Path,status="APPROVED"):
    value={"version":"1","status":status,"approved_by":"policy-owner" if status=="APPROVED" else "","approved_at":"2026-01-01T00:00:00+00:00" if status=="APPROVED" else "","classes":{name:{"retention_days":30,"disposition":"REVIEW_DELETE"} for name in ("RAW_IMPORT","CONTACT_DATA","RESEARCH_CACHE","RETRIEVAL_TELEMETRY")}};path.write_text(json.dumps(value),encoding="utf-8");return path

def test_retention_assessment_is_aggregate_dry_run_and_honors_class_hold(tmp_path):
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        batch=ImportBatch(source_file="logical/private.csv",source_sha256="a"*64);db.add(batch);db.flush();row=RawImportRow(batch_id=batch.id,source_file="logical/private.csv",sheet_name="CSV",source_row_number=2,row_hash="b"*64,original_row_json="{}",normalized_row_json="{}",disposition="review",imported_at=datetime.now(timezone.utc)-timedelta(days=60));db.add(row);db.flush();policy=_policy(tmp_path/"policy.json");report=build_retention_assessment(db,Path(__file__).resolve().parents[3],policy);raw=next(x for x in report["classes"] if x["data_class"]=="RAW_IMPORT");assert report["status"]=="REVIEW_REQUIRED" and raw["population"]==1 and raw["disposition_review_count"]==1 and all("id" not in x for x in report["classes"])
        hold=propose_class_legal_hold(db,"RAW_IMPORT","maker","Preserve imported records for pending legal review");assert hold.status=="PROPOSED"
        with pytest.raises(RetentionError,match="independent hold approver"):adjudicate_legal_hold(db,hold.id,"APPROVE","maker","Maker cannot approve the same legal hold","PROPOSED")
        adjudicate_legal_hold(db,hold.id,"APPROVE","counsel","Independent counsel approves preservation hold","PROPOSED");held=build_retention_assessment(db,Path(__file__).resolve().parents[3],policy);raw=next(x for x in held["classes"] if x["data_class"]=="RAW_IMPORT");assert raw["active_class_hold"] and raw["disposition_review_count"]==0
        with pytest.raises(RetentionError,match="independent hold releaser"):adjudicate_legal_hold(db,hold.id,"RELEASE","maker","Maker cannot release the legal hold","ACTIVE")
        adjudicate_legal_hold(db,hold.id,"RELEASE","independent-counsel","Matter closed after documented independent review","ACTIVE");assert hold.status=="RELEASED"
        run=persist_retention_assessment(db,report);assert run.status=="REVIEW_REQUIRED" and run.report_hash

def test_retention_policy_fails_closed_for_draft_repo_file_and_symlink(tmp_path):
    repo=Path(__file__).resolve().parents[3];draft=repo/"config/retention-policy.example.json"
    with pytest.raises(RetentionError):load_retention_policy(draft,repo)
    target=_policy(tmp_path/"approved.json");link=tmp_path/"policy-link.json";link.symlink_to(target)
    with pytest.raises(RetentionError,match="symlink"):load_retention_policy(link,repo)
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:report=build_retention_assessment(db,repo,draft);assert report["status"]=="NOT_CONFIGURED" and report["summary"]["disposition_review_count"]==0
