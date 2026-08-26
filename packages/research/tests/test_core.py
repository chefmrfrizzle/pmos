from pmos_research.entity_resolution import canonicalize_name, domain, resolve, MatchState
from pmos_research.scoring import strategic_score, explain_score
from pmos_research.importers import ImportSafetyError,detect_header,import_csv,preflight_import
from pmos_research.db import Base, AdjudicationEvent, AuditLedgerEntry, Claim, ClaimEvidence, Contact, CorroborationJob, Entity, EvidencePassage, IdentityCluster, IdentityMembership, ImportBatch, LegalIdentifier, RawImportRow, RegistryIdentifierCandidate, RelationshipAssertion, ResolutionDecision, ReviewQueueItem, CheckResult, ConflictCase, SourceDocument, install_ledger_guards
from pmos_research.adjudication import AdjudicationInputError, StaleReviewError, adjudicate, run_corroboration_job
from pmos_research.diligence import open_case, readiness, specialist_signoff
from pmos_research.identity_audit import shadow_audit
from pmos_research.audit_ledger import append_ledger_event,verify_ledger
from pmos_research.relationship_controls import propose_relationship,verify_relationship
from pmos_research.registry_research import assess_lei_candidate,persist_lei_candidate
from pmos_research.registry_adjudication import IdentifierAdjudicationError,adjudicate_identifier
from pmos_research.adapters.official_web import OfficialWebAdapter, ResponseTooLarge, UnsafeResearchTarget
from pmos_research.fact_extraction import identity_evidence_passage,identity_supported
import pytest
import httpx
import csv
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.exc import DatabaseError
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
        assert db.scalar(select(func.count()).select_from(Entity))==2
        assert db.scalar(select(func.count()).select_from(Contact))==1
        assert db.scalar(select(func.count()).select_from(Claim))>=2
        states=set(db.scalars(select(ResolutionDecision.state)))
        assert "REQUIRES_REVIEW" in states

def test_organization_requires_domain_for_exact_match(tmp_path):
    source=tmp_path/"synthetic.csv";source.write_text("Investor Name,Country,Website\nExample Capital,CA,https://example.test\nExample Capital,CA,https://example.test\n",encoding="utf-8")
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        import_csv(db,source);db.commit()
        assert db.scalar(select(func.count()).select_from(Entity))==1
        assert "EXACT_MATCH" in set(db.scalars(select(ResolutionDecision.state)))

def test_same_name_and_jurisdiction_without_domain_is_not_exact(tmp_path):
    source=tmp_path/"synthetic.csv";source.write_text("Investor Name,Country\nExample Capital,CA\nExample Capital,CA\n",encoding="utf-8")
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        import_csv(db,source);db.commit()
        assert db.scalar(select(func.count()).select_from(Entity))==2
        assert "EXACT_MATCH" not in set(db.scalars(select(ResolutionDecision.state)))

def test_import_is_idempotent_by_source_hash(tmp_path):
    source=tmp_path/"synthetic.csv";source.write_text("Name,Email\nAlex Example,alex@example.test\n",encoding="utf-8")
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        assert import_csv(db,source)==2
        db.commit()
        assert import_csv(db,source)==0

def test_import_rejects_oversized_cells_and_row_counts(tmp_path,monkeypatch):
    import pmos_research.importers as importers
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    oversized=tmp_path/"oversized.csv";oversized.write_text("Name\n"+"x"*1001+"\n",encoding="utf-8")
    monkeypatch.setattr(importers,"MAX_CELL_CHARS",1000)
    with factory() as db:
        with pytest.raises((ImportSafetyError,csv.Error)):import_csv(db,oversized)
    rows=tmp_path/"rows.csv";rows.write_text("Name\nA\nB\n",encoding="utf-8");monkeypatch.setattr(importers,"MAX_ROWS",2)
    with factory() as db:
        with pytest.raises(ImportSafetyError):import_csv(db,rows)

def test_import_rejects_symlinks_and_invalid_xlsx_archives(tmp_path):
    source=tmp_path/"source.csv";source.write_text("Name\nExample\n",encoding="utf-8");link=tmp_path/"link.csv";link.symlink_to(source)
    with pytest.raises(ImportSafetyError):preflight_import(link,".csv")
    fake=tmp_path/"fake.xlsx";fake.write_bytes(b"not a zip")
    with pytest.raises(ImportSafetyError):preflight_import(fake,".xlsx")

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

def test_official_adapter_rejects_alternate_ports():
    adapter=OfficialWebAdapter(resolver=lambda *args,**kwargs:[(None,None,None,None,("93.184.216.34",8443))])
    with pytest.raises(UnsafeResearchTarget):adapter._validate_url("https://example.test:8443/")

def test_official_adapter_streams_with_decompressed_size_cap():
    adapter=OfficialWebAdapter(resolver=lambda *args,**kwargs:[(None,None,None,None,("93.184.216.34",443))]);adapter.max_bytes=65536;adapter.delay=.5
    adapter.client=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=b"x"*70000,headers={"content-type":"text/html"})),trust_env=False)
    with pytest.raises(ResponseTooLarge):adapter._get("https://example.test/")

def test_robots_failure_is_fail_closed():
    adapter=OfficialWebAdapter(resolver=lambda *args,**kwargs:[(None,None,None,None,("93.184.216.34",443))])
    class Broken:
        def get(self,*args,**kwargs):raise RuntimeError("network unavailable")
    adapter.client=Broken()
    assert adapter.allowed("https://example.com/about") is False

def test_identity_support_requires_meaningful_name_tokens():
    assert identity_supported("Northstar Collection","About Northstar Collection")
    assert not identity_supported("Northstar Collection","Generic institutional investment page")

def test_identity_passage_is_bounded_and_never_invents_support():
    result=identity_evidence_passage("Northstar Collection","About","Intro. Northstar Collection is an institutional example. "+"context "*200)
    assert result and len(result["passage"])<=700 and identity_supported("Northstar Collection",result["passage"])
    assert identity_evidence_passage("Northstar Collection","Generic","Unrelated institutional page") is None

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

def test_homepage_match_supports_claim_but_not_whole_entity():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    class OfficialPage:
        def fetch(self,url):return {"status":"ok","url":url,"title":"Northstar Collection","text":"About Northstar Collection","hash":"b"*64}
    with factory() as db:
        entity=Entity(name="Northstar Collection",canonical_name="northstar collection",universe="test",official_url="https://example.test",evidence_confidence=0)
        db.add(entity);db.flush()
        job=CorroborationJob(entity_id=entity.id,source_url=entity.official_url,source_domain="example.test",checkpoint_json="{}")
        db.add(job);db.flush()
        assert run_corroboration_job(db,job,OfficialPage())=="SUPPORTED"
        assert entity.verification_status=="EVIDENCE_COLLECTED"
        assert db.scalar(select(func.count()).select_from(Claim).where(Claim.verification_status=="SUPPORTED"))==1
        assert db.scalar(select(func.count()).select_from(SourceDocument))==1
        assert db.scalar(select(func.count()).select_from(EvidencePassage))==1
        assert db.scalar(select(func.count()).select_from(ClaimEvidence))==1
        checkpoint=__import__("json").loads(job.checkpoint_json)
        assert {"document_id","passage_id","claim_evidence_id"}<=checkpoint.keys()

def test_diligence_case_has_type_specific_mandatory_checks():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Example CVC",canonical_name="example cvc",universe="test")
        db.add(entity);db.flush()
        case=open_case(db,entity.id,"corporate venture capital","counterparty assessment","internal decision support","maker",["US"])
        checks=set(db.scalars(select(CheckResult.check_code).where(CheckResult.case_id==case.id)))
        assert {"legal_identity","ownership_control","mandate","authority_to_transact"} <= checks
        assert readiness(db,case.id)["state"]=="RED"

def test_material_conflict_blocks_readiness_and_high_risk_requires_maker_checker():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Example Fund",canonical_name="example fund",universe="test")
        db.add(entity);db.flush()
        case=open_case(db,entity.id,"private equity","assessment","internal decision support","maker")
        case.risk_tier="HIGH"
        for check in db.scalars(select(CheckResult).where(CheckResult.case_id==case.id)):
            check.status="CORROBORATED"
        db.add(ConflictCase(entity_id=entity.id,predicate="fund_manager",materiality="MATERIAL"));db.flush()
        assert readiness(db,case.id)=={"state":"RED","missing_checks":[],"material_conflicts":["fund_manager"]}
        with pytest.raises(ValueError):specialist_signoff(db,case.id,"maker","reviewer","APPROVE","looks good")
        specialist_signoff(db,case.id,"independent-reviewer","reviewer","ESCALATE","manager conflict remains")

def _review_fixture(db):
    batch=ImportBatch(source_file="synthetic.csv",source_sha256="c"*64);db.add(batch);db.flush()
    existing=Entity(name="Example Capital",canonical_name="example capital",universe="test",country="CA",official_url="https://example.test")
    source=Entity(name="Example Capital Inc.",canonical_name="example capital",universe="imported_private",country="CA",official_url="https://example.test")
    db.add_all([existing,source]);db.flush()
    raw=RawImportRow(batch_id=batch.id,source_file="synthetic.csv",sheet_name="CSV",source_row_number=2,row_hash="d"*64,original_row_json="[]",normalized_row_json='{"investor name":"Example Capital Inc.","country":"CA","website":"https://example.test"}',disposition="imported",entity_id=source.id)
    db.add(raw);db.flush()
    decision=ResolutionDecision(raw_row_id=raw.id,candidate_entity_id=existing.id,state="PROBABLE_MATCH",confidence=.92,reasons_json='["strong name match"]')
    db.add(decision);db.flush()
    item=ReviewQueueItem(resolution_decision_id=decision.id,queue_type="ENTITY",priority=85,reasons_json='["review"]')
    db.add(item);db.flush();return item

def test_adjudication_is_two_stage_and_preserves_source_entities():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        item=_review_fixture(db);version=item.updated_at.replace(tzinfo=timezone.utc).isoformat() if item.updated_at.tzinfo is None else item.updated_at.isoformat()
        result=adjudicate(db,item.id,"PROPOSE_MATCH","maker","same official domain and jurisdiction",expected_version=version)
        assert result["resulting_state"]=="PROPOSED"
        with pytest.raises(AdjudicationInputError):adjudicate(db,item.id,"APPROVE_MATCH","maker","self approval")
        adjudicate(db,item.id,"APPROVE_MATCH","checker","independent review completed",expected_version=result["version"])
        assert item.status=="ACCEPTED"
        assert db.scalar(select(func.count()).select_from(Entity))==2
        assert db.scalar(select(func.count()).select_from(IdentityCluster).where(IdentityCluster.status=="ACCEPTED"))==1
        assert db.scalar(select(func.count()).select_from(IdentityMembership).where(IdentityMembership.status=="ACCEPTED"))==2
        assert db.scalar(select(func.count()).select_from(AdjudicationEvent))==2

def test_adjudication_rejects_stale_review_version():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        item=_review_fixture(db)
        with pytest.raises(StaleReviewError):adjudicate(db,item.id,"DEFER","reviewer","needs more evidence",expected_version="stale")
        assert item.status=="PENDING"

def test_shadow_audit_only_retains_exact_matches_meeting_strict_identity_controls():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        item=_review_fixture(db);decision=db.get(ResolutionDecision,item.resolution_decision_id);decision.state="EXACT_MATCH"
        result=shadow_audit(db)
        assert result["total_prior_exact"]==1
        assert result["still_exact"]==1
        raw=db.get(RawImportRow,decision.raw_row_id);raw.normalized_row_json='{"investor name":"Example Capital Inc.","country":"CA"}'
        result=shadow_audit(db)
        assert result["still_exact"]==0
        assert result["reasons"]["review:official_domain_missing_or_mismatch"]==1

def test_case_corroboration_queues_public_registry_only():
    from pmos_research.adjudication import enqueue_case_corroboration
    from pmos_research.db import DiligenceCase
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        public=Entity(name="Public Example",canonical_name="public example",universe="venture_capital",official_url="https://public.example")
        private=Entity(name="Private Example",canonical_name="private example",universe="imported_private",official_url="https://private.example")
        db.add_all([public,private]);db.flush()
        for entity in (public,private):db.add(DiligenceCase(entity_id=entity.id,purpose="test",permitted_use="test",owner="test"))
        db.flush();result=enqueue_case_corroboration(db)
        assert result["queued"]==1
        job=db.scalar(select(CorroborationJob));assert job.entity_id==public.id

def test_audit_ledger_detects_payload_tampering():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        append_ledger_event(db,"TEST","1","actor","REVIEWER","OPENED",{"status":"OPEN"},"correlation-1")
        append_ledger_event(db,"TEST","1","actor-2","REVIEWER","CLOSED",{"status":"CLOSED"},"correlation-2")
        assert verify_ledger(db,"TEST","1")=={"valid":True,"entries":2,"errors":[]}
        first=db.scalar(select(AuditLedgerEntry).where(AuditLedgerEntry.sequence==1));first.payload_json='{"status":"FORGED"}'
        result=verify_ledger(db,"TEST","1")
        assert not result["valid"]
        assert {x["error"] for x in result["errors"]}>={"event_hash_mismatch"}

def test_sqlite_ledger_guards_reject_update_and_delete():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);install_ledger_guards(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entry=append_ledger_event(db,"TEST","1","actor","REVIEWER","OPENED",{"status":"OPEN"});db.commit()
        with pytest.raises(DatabaseError):db.execute(update(AuditLedgerEntry).where(AuditLedgerEntry.id==entry.id).values(payload_json="{}"));db.commit()
        db.rollback()
        with pytest.raises(DatabaseError):db.delete(entry);db.commit()

def _relationship_fixture(db,ranks):
    source=Entity(name="Source",canonical_name="source",universe="test");target=Entity(name="Target",canonical_name="target",universe="test")
    db.add_all([source,target]);db.flush();documents=[]
    offset=db.scalar(select(func.count()).select_from(SourceDocument)) or 0
    for index,(rank,group) in enumerate(ranks,offset+1):
        document=SourceDocument(entity_id=source.id,publisher=group,publisher_independence_group=group,source_rank=rank,source_type="registry",source_url=f"https://source{index}.example",content_hash=f"{index:064x}"[-64:])
        db.add(document);documents.append(document)
    db.flush();return source,target,documents

def test_sensitive_relationship_requires_dispositive_primary_source_and_independent_review():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        source,target,documents=_relationship_fixture(db,[("S1","official-site")])
        assertion=propose_relationship(db,source.id,target.id,"CONTROLS","maker",[documents[0].id],"GB")
        assert assertion.status=="HUMAN_REVIEW_REQUIRED" and assertion.sensitive
        with pytest.raises(ValueError):verify_relationship(db,assertion.id,"maker","self approval")
        with pytest.raises(ValueError):verify_relationship(db,assertion.id,"checker","official site is not dispositive ownership evidence")
        assert assertion.status=="HUMAN_REVIEW_REQUIRED"

def test_relationship_verification_accepts_s0_or_independent_corroboration():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        source,target,documents=_relationship_fixture(db,[("S0","companies-house")])
        sensitive=propose_relationship(db,source.id,target.id,"OWNS","maker",[documents[0].id],"GB")
        verify_relationship(db,sensitive.id,"checker","registry instrument directly records ownership")
        assert sensitive.status=="SPECIALIST_VERIFIED"
        assert verify_ledger(db,"RELATIONSHIP_ASSERTION",sensitive.id)["valid"]
    with factory() as db:
        source,target,documents=_relationship_fixture(db,[("S1","annual-report"),("S2","market-infrastructure")])
        ordinary=propose_relationship(db,source.id,target.id,"ADVISES","maker",[x.id for x in documents])
        verify_relationship(db,ordinary.id,"checker","independent sources corroborate the advisory relationship")
        assert ordinary.status=="SPECIALIST_VERIFIED"

def _lei_record(**overrides):
    value={"lei":"549300EXAMPLE0000001","legal_name":"Example Capital Limited","entity_status":"ACTIVE","jurisdiction":"CA","legal_address_country":"CA","legal_form_id":"8888","registration_authority_id":"RA000071","registration_authority_entity_id":"12345","lei_registration_status":"ISSUED","initial_registration_date":"2020-01-01","last_update_date":"2026-01-01","next_renewal_date":"2027-01-01","record_url":"https://api.gleif.org/api/v1/lei-records/549300EXAMPLE0000001","content_hash":"e"*64}
    value.update(overrides);return value

def test_lei_candidate_is_never_auto_accepted_as_identifier():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Example Capital Limited",canonical_name="example capital",universe="private_equity",country="CA");db.add(entity);db.flush()
        state,confidence,reasons=assess_lei_candidate(entity,_lei_record())
        assert state=="PROBABLE_MATCH" and confidence==.92
        candidate,created=persist_lei_candidate(db,entity,_lei_record())
        assert created and candidate.status=="PENDING_REVIEW" and candidate.match_state=="PROBABLE_MATCH"
        assert db.scalar(select(func.count()).select_from(LegalIdentifier))==0
        claim=db.get(Claim,candidate.claim_id);assert claim.verification_status=="CANDIDATE"
        assert db.scalar(select(func.count()).select_from(ClaimEvidence).where(ClaimEvidence.claim_id==claim.id))==1
        same,created=persist_lei_candidate(db,entity,_lei_record());assert same.id==candidate.id and not created

def test_lei_jurisdiction_conflict_fails_closed():
    entity=Entity(name="Example Capital Limited",canonical_name="example capital",universe="private_equity",country="CA")
    state,confidence,reasons=assess_lei_candidate(entity,_lei_record(jurisdiction="US-DE",legal_address_country="US"))
    assert state=="CONFLICT" and confidence==.25 and "conflicting jurisdiction" in reasons

def _supported_identity(db,entity):
    document=SourceDocument(entity_id=entity.id,publisher="official.example",publisher_independence_group="official.example",source_rank="S1",source_type="official_website",source_url="https://official.example",content_hash="f"*64);db.add(document);db.flush()
    passage=EvidencePassage(document_id=document.id,section="title",passage=entity.name,passage_hash="a"*64);db.add(passage);db.flush()
    claim=Claim(entity_id=entity.id,field="official_identity",value=entity.name,source_url=document.source_url,source_type="official",confidence=.9,verification_status="SUPPORTED",extractor="test",evidence_hash=document.content_hash);db.add(claim);db.flush();db.add(ClaimEvidence(claim_id=claim.id,passage_id=passage.id,directness=.95,supports=True));db.flush()

def test_identifier_acceptance_requires_two_stage_review_and_separate_identity_evidence():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Example Capital Limited",canonical_name="example capital",universe="private_equity",country="CA");db.add(entity);db.flush()
        candidate,_=persist_lei_candidate(db,entity,_lei_record())
        with pytest.raises(IdentifierAdjudicationError):adjudicate_identifier(db,candidate.id,"PROPOSE_ACCEPTANCE","maker","registry match",candidate.status)
        _supported_identity(db,entity)
        adjudicate_identifier(db,candidate.id,"PROPOSE_ACCEPTANCE","maker","legal name and jurisdiction align with separate official identity evidence","PENDING_REVIEW")
        with pytest.raises(IdentifierAdjudicationError):adjudicate_identifier(db,candidate.id,"APPROVE","maker","self approval","PROPOSED_ACCEPTANCE")
        adjudicate_identifier(db,candidate.id,"APPROVE","checker","independent review confirms the scoped LEI identity","PROPOSED_ACCEPTANCE")
        identifier=db.scalar(select(LegalIdentifier));assert identifier.status=="SPECIALIST_VERIFIED"
        accepted=db.get(Claim,identifier.claim_id);assert accepted.field=="lei" and accepted.verification_status=="SPECIALIST_VERIFIED"
        assert db.scalar(select(func.count()).select_from(ClaimEvidence).where(ClaimEvidence.claim_id==accepted.id))==1
        assert verify_ledger(db,"IDENTIFIER_REVIEW",candidate.id)["valid"]

def test_possible_identifier_candidate_cannot_be_proposed():
    engine=create_engine("sqlite:///:memory:");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Example Capital",canonical_name="example capital",universe="private_equity",country="CA");db.add(entity);db.flush();_supported_identity(db,entity)
        candidate,_=persist_lei_candidate(db,entity,_lei_record(legal_name="Example Capital Management"));candidate.match_state="POSSIBLE_MATCH"
        with pytest.raises(IdentifierAdjudicationError):adjudicate_identifier(db,candidate.id,"PROPOSE_ACCEPTANCE","maker","needs acceptance","PENDING_REVIEW")
