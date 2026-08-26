import pytest
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Claim,ClaimCheckRoutingCandidate,ClaimEvidence,ConflictCase,ConflictMember,Entity,EvidencePassage,ResearchPassageCandidate,ResearchSourceCandidate,SourceDocument
from pmos_research.diligence import open_case
from pmos_research.passage_adjudication import PassageAdjudicationError,adjudicate_passage

def _fixture(db,predicate="legal_identity",passage_text="The legal name is Example Capital LP."):
    entity=Entity(name="Example Capital",canonical_name="example capital",universe="venture_capital");db.add(entity);db.flush()
    source=ResearchSourceCandidate(entity_id=entity.id,source_url="https://official.example/legal",source_domain="official.example",document_type="LEGAL_IDENTITY",target_predicates_json=f'["{predicate}"]',discovered_from_url="https://official.example",discovery_score=80,status="RETRIEVED_REVIEW_REQUIRED");db.add(source);db.flush()
    document=SourceDocument(entity_id=entity.id,publisher="official.example",publisher_independence_group="official.example",source_rank="S1",source_type="official_website",source_url=source.source_url,content_hash="a"*64);db.add(document);db.flush()
    passage=EvidencePassage(document_id=document.id,section="candidate",passage=passage_text,passage_hash="b"*64);db.add(passage);db.flush()
    candidate=ResearchPassageCandidate(source_candidate_id=source.id,evidence_passage_id=passage.id,predicate=predicate,confidence=.75);db.add(candidate);db.flush();return entity,candidate

def test_passage_support_requires_exact_value_and_independent_approval():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity,candidate=_fixture(db)
        open_case(db,entity.id,"default","counterparty assessment","internal diligence","case-owner")
        with pytest.raises(PassageAdjudicationError):adjudicate_passage(db,candidate.id,"PROPOSE_SUPPORT","maker","The passage establishes the legal identity","Invented Holdings LP",candidate.status)
        proposal=adjudicate_passage(db,candidate.id,"PROPOSE_SUPPORT","maker","The passage explicitly states the legal identity","Example Capital LP",candidate.status)
        with pytest.raises(PassageAdjudicationError):adjudicate_passage(db,candidate.id,"APPROVE_SUPPORT","maker","Attempting self approval of the passage","Example Capital LP",proposal["resulting_state"])
        with pytest.raises(PassageAdjudicationError):adjudicate_passage(db,candidate.id,"APPROVE_SUPPORT","checker","Independent review with altered value","Example Capital",proposal["resulting_state"])
        result=adjudicate_passage(db,candidate.id,"APPROVE_SUPPORT","checker","Independent review confirms the exact passage and scope","Example Capital LP",proposal["resulting_state"]);db.commit()
        claim=db.get(Claim,result["claim_id"])
        assert claim.verification_status=="SUPPORTED" and claim.value=="Example Capital LP"
        assert db.scalar(select(func.count()).select_from(ClaimEvidence).where(ClaimEvidence.claim_id==claim.id))==1
        assert result["routing_candidate_ids"] and db.scalar(select(func.count()).select_from(ClaimCheckRoutingCandidate))==1

def test_material_contradiction_must_be_recorded_as_conflict():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity,candidate=_fixture(db)
        prior=Claim(entity_id=entity.id,field="legal_identity",value="Different Capital LLC",source_url="https://registry.example",source_type="registry",confidence=1,verification_status="SUPPORTED",extractor="registry",evidence_hash="c"*64);db.add(prior);db.flush()
        with pytest.raises(PassageAdjudicationError):adjudicate_passage(db,candidate.id,"PROPOSE_SUPPORT","maker","Official sources present contradictory legal identities","Example Capital LP",candidate.status)
        result=adjudicate_passage(db,candidate.id,"MARK_CONFLICT","maker","Official sources present contradictory legal identities","Example Capital LP",candidate.status);db.commit()
        assert result["resulting_state"]=="CONFLICT" and db.get(Claim,result["claim_id"]).verification_status=="CONFLICT"
        conflict=db.scalar(select(ConflictCase));members=set(db.scalars(select(ConflictMember.claim_id).where(ConflictMember.conflict_id==conflict.id)))
        assert members=={prior.id,result["claim_id"]} and conflict.status=="HUMAN_REVIEW_REQUIRED"
