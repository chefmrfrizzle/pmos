import json
from datetime import datetime,timezone
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,EvidenceReviewBatch
from pmos_research.reviewer_roster import ReviewerRosterError,build_reviewer_roster_assessment,load_reviewer_roster,persist_reviewer_roster_assessment

def _roster(path:Path):
    value={"version":"1","status":"APPROVED","approved_by":"identity-owner","approved_at":datetime.now(timezone.utc).isoformat(),"tenant_id":"tenant-a","reviewers":[
        {"subject":"subject-alpha-123","roles":["RESEARCHER"],"permissions":["evidence:write"],"universes":["pensions"],"purposes":["institutional diligence"],"status":"ACTIVE"},
        {"subject":"subject-beta-456","roles":["REVIEWER"],"permissions":["evidence:approve"],"universes":["pensions"],"purposes":["institutional diligence"],"status":"ACTIVE"},
        {"subject":"subject-gamma-789","roles":["ADMIN"],"permissions":["evidence:assign"],"universes":["pensions"],"purposes":["review administration"],"status":"ACTIVE"}]};path.write_text(json.dumps(value),encoding="utf-8");return path

def test_roster_preflight_proves_three_way_separation_without_subjects_in_report(tmp_path):
    repo=Path(__file__).resolve().parents[3];engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        db.add(EvidenceReviewBatch(status="FROZEN",criteria_json=json.dumps({"universe":"pensions"}),manifest_hash="a"*64,item_count=10,created_by="system"));db.flush();report=build_reviewer_roster_assessment(db,repo,_roster(tmp_path/"roster.json"));run=persist_reviewer_roster_assessment(db,report);assert report["status"]=="READY" and report["gap_count"]==0 and run.roster_hash and all(x not in json.dumps(report) for x in ("subject-alpha-123","subject-beta-456","subject-gamma-789"))

def test_roster_fails_closed_for_wildcards_overlap_and_repo_template(tmp_path):
    repo=Path(__file__).resolve().parents[3]
    with pytest.raises(ReviewerRosterError):load_reviewer_roster(repo/"config/reviewer-roster.example.json",repo)
    path=_roster(tmp_path/"roster.json");value=json.loads(path.read_text());value["reviewers"][0]["permissions"].append("evidence:approve");path.write_text(json.dumps(value))
    with pytest.raises(ReviewerRosterError,match="researcher entries"):load_reviewer_roster(path,repo)
