import hashlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pmos_research.control_assurance import persist_assurance_run,run_control_assurance
from pmos_research.db import Base,Claim,ClaimEvidence,ControlAssuranceRun,Entity,EvidencePassage,IdentityCluster,IdentityMembership,JurisdictionReviewCase,PrivateSaleCase,PrivateSaleGate,ResearchDocumentSnapshot,ResearchSourceCandidate,SourceDocument

def _clean_fixture(db):
    entity=Entity(name="Private Example Name",canonical_name="private example name",universe="test");db.add(entity);db.flush()
    text="The legal name is Private Example Name.";digest=hashlib.sha256(text.encode()).hexdigest()
    document=SourceDocument(entity_id=entity.id,publisher="official.example",publisher_independence_group="official.example",source_rank="S1",source_type="official_website",source_url="https://official.example",content_hash=digest);db.add(document);db.flush()
    passage=EvidencePassage(document_id=document.id,passage=text,passage_hash=digest);db.add(passage);db.flush()
    claim=Claim(entity_id=entity.id,field="legal_identity",value="Private Example Name",source_url=document.source_url,source_type=document.source_type,confidence=.9,verification_status="SUPPORTED",extractor="test",evidence_hash=digest);db.add(claim);db.flush();db.add(ClaimEvidence(claim_id=claim.id,passage_id=passage.id,directness=.9,supports=True))
    source=ResearchSourceCandidate(entity_id=entity.id,source_url=document.source_url,source_domain="official.example",document_type="LEGAL_IDENTITY",target_predicates_json='["legal_identity"]',discovered_from_url=document.source_url,discovery_score=80,status="RETRIEVED_REVIEW_REQUIRED");db.add(source);db.flush();snapshot=ResearchDocumentSnapshot(source_candidate_id=source.id,source_document_id=document.id,normalized_text=text,text_hash=digest);db.add(snapshot);db.flush();return snapshot

def test_control_assurance_passes_clean_state_and_emits_no_record_values():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        _clean_fixture(db);db.commit();result=run_control_assurance(db)
        assert result["status"]=="PASS" and result["exception_count"]==0
        assert "Private Example Name" not in str(result)
        run=persist_assurance_run(db,result);db.commit();assert db.get(ControlAssuranceRun,run.id).report_hash==run.report_hash

def test_control_assurance_fails_closed_on_hash_tampering():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        snapshot=_clean_fixture(db);snapshot.text_hash="0"*64;db.commit();result=run_control_assurance(db)
        control=next(x for x in result["controls"] if x["control"]=="research_snapshot_hash_integrity")
        assert result["status"]=="FAIL" and control["exceptions"]==1

def test_control_assurance_detects_identity_membership_in_competing_clusters():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        first=Entity(name="First",canonical_name="first",universe="test");second=Entity(name="Second",canonical_name="second",universe="test");third=Entity(name="Third",canonical_name="third",universe="test");db.add_all([first,second,third]);db.flush()
        one=IdentityCluster(identity_type="ENTITY",canonical_label="One",status="PROPOSED",created_by="maker-a");two=IdentityCluster(identity_type="ENTITY",canonical_label="Two",status="PROPOSED",created_by="maker-b");db.add_all([one,two]);db.flush()
        db.add_all([IdentityMembership(cluster_id=one.id,entity_id=first.id,status="PROPOSED",confidence=1),IdentityMembership(cluster_id=one.id,entity_id=second.id,status="PROPOSED",confidence=.9),IdentityMembership(cluster_id=two.id,entity_id=first.id,status="PROPOSED",confidence=1),IdentityMembership(cluster_id=two.id,entity_id=third.id,status="PROPOSED",confidence=.8)]);db.flush()
        result=run_control_assurance(db);control=next(x for x in result["controls"] if x["control"]=="active_identity_pair_exclusivity")
        assert result["status"]=="FAIL" and control["exceptions"]==1

def test_control_assurance_rejects_retry_state_without_attempt_history():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Institution",canonical_name="institution",universe="test");db.add(entity);db.flush()
        db.add(ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example",source_domain="official.example",document_type="LEGAL_IDENTITY",target_predicates_json='["legal_identity"]',discovered_from_url="https://official.example",status="RETRY_REQUIRED"));db.flush()
        result=run_control_assurance(db);control=next(x for x in result["controls"] if x["control"]=="source_retrieval_attempt_integrity")
        assert result["status"]=="FAIL" and control["exceptions"]==1

def test_control_assurance_rejects_private_sale_pass_without_review_history():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        asset=Entity(name="Asset",canonical_name="asset",universe="asset");db.add(asset);db.flush();case=PrivateSaleCase(asset_entity_id=asset.id,purpose="assessment",permitted_use="diligence",owner="owner");db.add(case);db.flush();db.add(PrivateSaleGate(case_id=case.id,gate_code="provenance",fact_class="provenance",critical=True,status="PASS"));db.flush()
        result=run_control_assurance(db);control=next(x for x in result["controls"] if x["control"]=="private_sale_gate_maker_checker_and_evidence")
        assert result["status"]=="FAIL" and control["exceptions"]==1

def test_control_assurance_rejects_approved_jurisdiction_without_review_history():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Institution",canonical_name="institution",universe="test",country="CA");db.add(entity);db.flush();claim=Claim(entity_id=entity.id,field="country",value="CA",source_url="https://official.example",verification_status="SUPPORTED",evidence_hash="a"*64);db.add(claim);db.flush();db.add(JurisdictionReviewCase(entity_id=entity.id,original_country="0",proposed_country="CA",source_claim_id=claim.id,status="APPROVED",proposed_by="maker",reviewed_by="checker"));db.flush()
        result=run_control_assurance(db);control=next(x for x in result["controls"] if x["control"]=="approved_jurisdiction_correction_evidence_and_maker_checker")
        assert result["status"]=="FAIL" and control["exceptions"]==1
