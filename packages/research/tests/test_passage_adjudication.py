import hashlib,pytest
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Claim,ClaimCheckRoutingCandidate,ClaimEvidence,ConflictCase,ConflictMember,Entity,EvidencePassage,ResearchDocumentSnapshot,ResearchPassageCandidate,ResearchSourceCandidate,SourceDocument
from pmos_research.diligence import open_case
from pmos_research.passage_adjudication import PassageAdjudicationError,adjudicate_passage
from pmos_research.evidence_review_batch import freeze_review_batch
from pmos_research.evidence_review_assignment import assign_reviewer

def _fixture(db,predicate="legal_identity",passage_text="The legal name is Example Capital LP."):
    entity=Entity(name="Example Capital",canonical_name="example capital",universe="venture_capital");db.add(entity);db.flush()
    source=ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example/legal",source_domain="official.example",document_type="LEGAL_IDENTITY",target_predicates_json=f'["{predicate}"]',discovered_from_url="https://official.example",discovery_score=80,status="RETRIEVED_REVIEW_REQUIRED");db.add(source);db.flush()
    digest=hashlib.sha256(passage_text.encode()).hexdigest();document=SourceDocument(entity_id=entity.id,publisher="official.example",publisher_independence_group="official.example",source_rank="S1",source_type="official_website",source_url=source.source_url,content_hash=digest);db.add(document);db.flush()
    db.add(ResearchDocumentSnapshot(source_candidate_id=source.id,source_document_id=document.id,normalized_text=passage_text,text_hash=digest));passage=EvidencePassage(document_id=document.id,section="candidate",passage=passage_text,passage_hash=digest);db.add(passage);db.flush()
    candidate=ResearchPassageCandidate(source_candidate_id=source.id,evidence_passage_id=passage.id,predicate=predicate,confidence=.75);db.add(candidate);db.flush();return entity,candidate

def test_passage_support_requires_exact_value_and_independent_approval():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity,candidate=_fixture(db)
        open_case(db,entity.id,"default","counterparty assessment","internal diligence","case-owner")
        batch=freeze_review_batch(db,"assigner","venture_capital")
        assign_reviewer(db,batch.id,"maker","RESEARCHER","assigner","Maker assigned for evidence proposal");assign_reviewer(db,batch.id,"checker","REVIEWER","assigner","Checker assigned for independent approval")
        with pytest.raises(PassageAdjudicationError):adjudicate_passage(db,candidate.id,"PROPOSE_SUPPORT","maker","RESEARCHER","The passage establishes the legal identity","Invented Holdings LP",candidate.status,review_batch_id=batch.id)
        proposal=adjudicate_passage(db,candidate.id,"PROPOSE_SUPPORT","maker","RESEARCHER","The passage explicitly states the legal identity","Example Capital LP",candidate.status,review_batch_id=batch.id)
        replacement=freeze_review_batch(db,"assigner","venture_capital",status="SUPPORT_PROPOSED");assign_reviewer(db,replacement.id,"checker","REVIEWER","assigner","Checker assigned to replacement review batch")
        with pytest.raises(PassageAdjudicationError,match="proposal's frozen review batch"):adjudicate_passage(db,candidate.id,"APPROVE_SUPPORT","checker","REVIEWER","A different assignment cannot approve the existing proposal","Example Capital LP",proposal["resulting_state"],replacement.id)
        with pytest.raises(PassageAdjudicationError):adjudicate_passage(db,candidate.id,"APPROVE_SUPPORT","maker","RESEARCHER","Attempting self approval of the passage","Example Capital LP",proposal["resulting_state"],batch.id)
        with pytest.raises(PassageAdjudicationError):adjudicate_passage(db,candidate.id,"APPROVE_SUPPORT","checker","REVIEWER","Independent review with altered value","Example Capital",proposal["resulting_state"],batch.id)
        result=adjudicate_passage(db,candidate.id,"APPROVE_SUPPORT","checker","REVIEWER","Independent review confirms the exact passage and scope","Example Capital LP",proposal["resulting_state"],batch.id);db.commit()
        claim=db.get(Claim,result["claim_id"])
        assert claim.verification_status=="SUPPORTED" and claim.value=="Example Capital LP"
        assert db.scalar(select(func.count()).select_from(ClaimEvidence).where(ClaimEvidence.claim_id==claim.id))==1
        assert result["routing_candidate_ids"] and db.scalar(select(func.count()).select_from(ClaimCheckRoutingCandidate))==1

def test_material_contradiction_must_be_recorded_as_conflict():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity,candidate=_fixture(db)
        prior=Claim(entity_id=entity.id,field="legal_identity",value="Different Capital LLC",source_url="https://registry.example",source_type="registry",confidence=1,verification_status="SUPPORTED",extractor="registry",evidence_hash="c"*64);db.add(prior);db.flush()
        batch=freeze_review_batch(db,"assigner","venture_capital");assign_reviewer(db,batch.id,"maker","RESEARCHER","assigner","Maker assigned for conflict assessment")
        with pytest.raises(PassageAdjudicationError):adjudicate_passage(db,candidate.id,"PROPOSE_SUPPORT","maker","RESEARCHER","Official sources present contradictory legal identities","Example Capital LP",candidate.status,review_batch_id=batch.id)
        result=adjudicate_passage(db,candidate.id,"MARK_CONFLICT","maker","RESEARCHER","Official sources present contradictory legal identities","Example Capital LP",candidate.status,review_batch_id=batch.id);db.commit()
        assert result["resulting_state"]=="CONFLICT" and db.get(Claim,result["claim_id"]).verification_status=="CONFLICT"
        conflict=db.scalar(select(ConflictCase));members=set(db.scalars(select(ConflictMember.claim_id).where(ConflictMember.conflict_id==conflict.id)))
        assert members=={prior.id,result["claim_id"]} and conflict.status=="HUMAN_REVIEW_REQUIRED"

def test_passage_support_fails_closed_when_snapshot_or_passage_integrity_breaks():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        _,candidate=_fixture(db);passage=db.get(EvidencePassage,candidate.evidence_passage_id);passage.passage_hash="0"*64;db.flush();batch=freeze_review_batch(db,"assigner","venture_capital");assign_reviewer(db,batch.id,"maker","RESEARCHER","assigner","Maker assigned for integrity assessment")
        with pytest.raises(PassageAdjudicationError,match="integrity"):
            adjudicate_passage(db,candidate.id,"PROPOSE_SUPPORT","maker","RESEARCHER","The passage would otherwise support identity","Example Capital LP",candidate.status,review_batch_id=batch.id)
        result=adjudicate_passage(db,candidate.id,"REJECT","maker","RESEARCHER","Evidence integrity failed and cannot support this assertion",expected_status=candidate.status,review_batch_id=batch.id)
        assert result["resulting_state"]=="REJECTED"
