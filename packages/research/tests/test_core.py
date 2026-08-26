from pmos_research.entity_resolution import canonicalize_name, domain, resolve, MatchState
from pmos_research.scoring import strategic_score, explain_score
from pmos_research.importers import detect_header, import_csv
from pmos_research.db import Base, Claim, Contact, Entity, ImportBatch, RawImportRow, ResolutionDecision
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
    with factory() as session:
        assert import_csv(session,source)==3
        session.commit()
        batch=session.scalar(select(ImportBatch))
        assert batch.rows_seen==3
        assert session.scalar(select(func.count()).select_from(RawImportRow))==3
        assert session.scalar(select(func.count()).select_from(Entity))==1
        assert session.scalar(select(func.count()).select_from(Contact))==1
        assert session.scalar(select(func.count()).select_from(Claim))>=2
        states=set(session.scalars(select(ResolutionDecision.state)))
        assert "EXACT_MATCH" in states
        assert "REQUIRES_REVIEW" in states

def test_import_is_idempotent_by_source_hash(tmp_path):
    source=tmp_path/"synthetic.csv";source.write_text("Name,Email\nAlex Example,alex@example.test\n",encoding="utf-8")
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as session:
        assert import_csv(session,source)==2
        session.commit()
        assert import_csv(session,source)==0
