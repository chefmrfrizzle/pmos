from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker

from pmos_research.db import AuditLedgerEntry,Base,Entity,ResearchSourceCandidate
from pmos_research.source_discovery import canonical_public_url,discover_source_links,persist_source_candidates

def test_source_discovery_is_same_domain_deterministic_and_review_only():
    html='''<a href="/annual-report.pdf?utm_source=x">Annual Report 2025</a><a href="https://official.example/governance">Board & Governance</a><a href="https://attacker.example/team">Leadership</a><a href="mailto:test@example.com">Contact</a>'''
    rows=discover_source_links("https://official.example/",html)
    assert [x["document_type"] for x in rows]==["ANNUAL_REPORT","GOVERNANCE"]
    assert rows[0]["source_url"]=="https://official.example/annual-report.pdf"
    assert canonical_public_url("https://official.example","http://127.0.0.1/admin") is None
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Official Institution",canonical_name="official institution",universe="pension");db.add(entity);db.flush()
        counts=persist_source_candidates(db,entity,"https://official.example/",html);db.commit()
        candidates=db.scalars(select(ResearchSourceCandidate)).all()
        assert counts["queued"]==2 and all(x.status=="PENDING_REVIEW" for x in candidates)
        assert db.scalars(select(AuditLedgerEntry)).one().action=="CANDIDATES_DISCOVERED"
        assert persist_source_candidates(db,entity,"https://official.example/",html)["existing"]==2
