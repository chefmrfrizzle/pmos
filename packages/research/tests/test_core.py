from pmos_research.entity_resolution import canonicalize_name, domain, resolve, MatchState
from pmos_research.scoring import strategic_score, explain_score
from pmos_research.importers import detect_header, import_csv
from pmos_research.db import Base, Claim, Contact, CorroborationJob, Entity, ImportBatch, RawImportRow, ResolutionDecision
from pmos_research.adjudication import run_corroboration_job
from pmos_research.adapters.official_web import OfficialWebAdapter, UnsafeResearchTarget
from pmos_research.fact_extraction import identity_supported
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

def test_canonicalize():
    assert canonicalize_name("Mubadala Investment Company PJSC") == "mubadala investment pjsc"

def test_domain():
    assert domain("https://www.adia.ae/about") == "adia.ae"

def test_score_bounds():
    w={"capital_access":.5,"network_leverage":.5}
    assert strategic_score({"capital_access":100,"network_leverage":100},w)==100

def test_score_is_explainable():
    result=explain_score({"capital_access":80,"network_leverage":40},{"capital_access":.75,"network_leverage":.25})
    assert result["score"]==70
    assert sum(x["contribution"] for x in result["factors"])==70

def test_resolution_does_not_merge_ambiguous_names():
    result=resolve({"name":"Northstar Capital"},{"name":"Northstar Collection"})
    assert result.state in {MatchState.POSSIBLE,MatchState.REVIEW}

def test_resolution_conflict():
    result=resolve({"name":"Jane Doe","email":"a@example.test"},{"name":"Jane Doe","email":"b@example.test"})
    assert result.state==MatchState.CONFLICT

def test_header_detection_prefers_identity_row():
    assert detect_header([["Private list"],["Investor Name","Country","Email"],["Example","CA","x@example.test"]])==1

def test_import_preserves_every_nonempty_row_and_resolves_exact_duplicates(tmp_path):
    source=tmp_path/"synthetic.csv"
    source.write_text("Investor Name,Country,Contact Name,Email\nExample Capital,CA,Alex Example,alex@example.test\nExample Capital,CA,Alex Example,alex@example.test\n",encoding="utf-8")
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        assert import_csv(db,source)==3
        db.commit()
        batch=db.scalar(select(ImportBatch))
        assert batch.rows_seen==3
        assert db.scalar(select(func.count()).select_from(RawImportRow))==3
        assert db.scalar(select(func.count()).select_from(Entity))==1
        assert db.scalar(select(func.count()).select_from(Contact))==1
        assert db.scalar(select(func.count()).select_from(Claim))>=2
        states=set(db.scalars(select(ResolutionDecision.state)))
        assert "EXACT_MATCH" in states
        assert "REQUIRES_REVIEW" in states

def test_import_is_idempotent_by_source_hash(tmp_path):
    source=tmp_path/"synthetic.csv";source.write_text("Name,Email\nAlex Example,alex@example.test\n",encoding="utf-8")
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        assert import_csv(db,source)==2
        db.commit()
        assert import_csv(db,source)==0

def test_same_email_with_conflicting_person_name_is_not_merged(tmp_path):
    source=tmp_path/"synthetic.csv";source.write_text("Contact Name,Email\nAlex Example,alex@example.test\nDifferent Person,alex@example.test\n",encoding="utf-8")
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        import_csv(db,source);db.commit()
        assert db.scalar(select(func.count()).select_from(Contact))==2
        assert "CONFLICT" in set(db.scalars(select(ResolutionDecision.state)))

def test_role_inbox_never_exactly_identifies_a_person(tmp_path):
    source=tmp_path/"synthetic.csv";source.write_text("Contact Name,Email\nAlex Example,info@example.test\nAlex Example,info@example.test\n",encoding="utf-8")
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        import_csv(db,source);db.commit()
        assert db.scalar(select(func.count()).select_from(Contact))==2
        assert "REQUIRES_REVIEW" in set(db.scalars(select(ResolutionDecision.state)))

def test_official_adapter_rejects_private_network_targets():
    adapter=OfficialWebAdapter(resolver=lambda *args,**kwargs:[(None,None,None,None,("127.0.0.1",80))])
    with pytest.raises(UnsafeResearchTarget):adapter._validate_url("http://example.test/")

def test_robots_failure_is_fail_closed():
    adapter=OfficialWebAdapter(resolver=lambda *args,**kwargs:[(None,None,None,None,("93.184.216.34",443))])
    class Broken:
        def get(self,*args,**kwargs):raise RuntimeError("network unavailable")
    adapter.client=Broken()
    assert adapter.allowed("https://example.com/about") is False

def test_identity_support_requires_meaningful_name_tokens():
    assert identity_supported("Northstar Collection","About Northstar Collection")
    assert not identity_supported("Northstar Collection","Generic institutional investment page")

def test_successful_fetch_does_not_verify_identity_without_name_support():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    class GenericPage:
        def fetch(self,url):return {"status":"ok","url":url,"title":"Institutional home","text":"Generic investment information","hash":"a"*64}
    with factory() as db:
        entity=Entity(name="Northstar Collection",canonical_name="northstar collection",universe="test",official_url="https://example.test",evidence_confidence=0)
        db.add(entity);db.flush()
        job=CorroborationJob(entity_id=entity.id,source_url=entity.official_url,source_domain="example.test",checkpoint_json="{}")
        db.add(job);db.flush()
        assert run_corroboration_job(db,job,GenericPage())=="HUMAN_REVIEW_REQUIRED"
        assert entity.verification_status=="EVIDENCE_COLLECTED"
        assert db.scalar(select(func.count()).select_from(Claim).where(Claim.verification_status=="SUPPORTED"))==0
