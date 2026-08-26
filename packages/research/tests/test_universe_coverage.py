import hashlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Claim,ClaimEvidence,Entity,EvidencePassage,SourceDocument,UniverseCoverageRun
from pmos_research.universe_coverage import build_universe_coverage,persist_coverage,region_for

def test_universe_coverage_distinguishes_registry_evidence_and_readiness_without_names():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Private Example Institution",canonical_name="private example institution",universe="venture_capital",country="US",official_url="https://official.example");db.add(entity);db.flush();text="The legal identity is Private Example Institution.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=entity.id,publisher="official.example",publisher_independence_group="official.example",source_rank="S1",source_type="official_website",source_url="https://official.example",content_hash=digest);db.add(document);db.flush();passage=EvidencePassage(document_id=document.id,passage=text,passage_hash=digest);db.add(passage);db.flush();claim=Claim(entity_id=entity.id,field="official_identity",value=entity.name,source_url=document.source_url,source_type=document.source_type,confidence=.9,verification_status="SUPPORTED",extractor="test",evidence_hash=digest);db.add(claim);db.flush();db.add(ClaimEvidence(claim_id=claim.id,passage_id=passage.id,directness=.9,supports=True));db.flush()
        report=build_universe_coverage(db);row=next(x for x in report["universes"] if x["universe"]=="venture_capital")
        assert report["status"]=="INCOMPLETE" and row["registered"]==1 and row["identity_evidence_backed"]==1 and row["decision_ready"]==0
        assert "Private Example Institution" not in str(report) and region_for("US")=="NORTH_AMERICA" and region_for("BM")=="CARIBBEAN" and region_for("XX")=="UNMAPPED"
        run=persist_coverage(db,report);db.commit();assert db.get(UniverseCoverageRun,run.id).report_hash==hashlib.sha256(run.report_json.encode()).hexdigest()
