import hashlib
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Entity,EvidencePassage,RelationshipAssertion,RelationshipMentionCandidate,RelationshipResearchCandidate,SourceDocument
from pmos_research.relationship_controls import adjudicate_relationship,relationship_evidence_controls
from pmos_research.relationship_research import adjudicate_relationship_candidate,adjudicate_relationship_mention,discover_relationship_candidates
from pmos_research.source_retrieval import extract_predicate_passages

def test_deterministic_relationship_candidate_stays_review_only_and_exact_evidence_bound():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        source=Entity(name="Alpha Capital",canonical_name="alpha capital",universe="venture_capital");target=Entity(name="Beta Ventures",canonical_name="beta ventures",universe="venture_capital");db.add_all([source,target]);db.flush();text="Alpha Capital entered a strategic partnership with Beta Ventures.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=source.id,publisher="alpha.example",publisher_independence_group="alpha.example",source_rank="S1",source_type="official_website",source_url="https://alpha.example/news",content_hash=digest);db.add(document);db.flush();passage=EvidencePassage(document_id=document.id,passage=text,passage_hash=digest);db.add(passage);db.flush();result=discover_relationship_candidates(db)
        assert result["queued"]==1;candidate=db.scalar(select(RelationshipResearchCandidate));assert candidate.status=="HUMAN_REVIEW_REQUIRED" and candidate.suggested_relation_type=="PARTNERED_WITH" and db.scalar(select(RelationshipAssertion)) is None
        adjudicate_relationship_candidate(db,candidate.id,"PROPOSE_ASSERTION","maker","Exact passage supports specialist relationship review","HUMAN_REVIEW_REQUIRED");assert candidate.status=="ASSERTION_PROPOSED";assertion=db.get(RelationshipAssertion,candidate.resulting_assertion_id);controls=relationship_evidence_controls(db,assertion);assert controls["evidence_count"]==1 and controls["verification_eligible"] is False
        with pytest.raises(ValueError,match="does not meet"):adjudicate_relationship(db,assertion.id,"APPROVE","checker","Independent review cannot override insufficient evidence")

def test_relationship_discovery_rejects_name_only_mentions_without_controlled_phrase():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        source=Entity(name="Alpha Capital",canonical_name="alpha capital",universe="venture_capital");target=Entity(name="Beta Ventures",canonical_name="beta ventures",universe="venture_capital");db.add_all([source,target]);db.flush();text="Alpha Capital and Beta Ventures attended the conference.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=source.id,publisher="alpha.example",publisher_independence_group="alpha.example",source_rank="S1",source_type="official_website",source_url="https://alpha.example/news",content_hash=digest);db.add(document);db.flush();db.add(EvidencePassage(document_id=document.id,passage=text,passage_hash=digest));db.flush();assert discover_relationship_candidates(db).get("queued",0)==0

def test_relationship_passage_extraction_requires_controlled_phrase():
    assert extract_predicate_passages("Alpha Capital partnered with Beta Ventures.",["relationship"])[0]["matched_term"]=="partnered with"
    assert extract_predicate_passages("Alpha Capital met Beta Ventures.",["relationship"])==[]

def test_unresolved_named_relationship_mention_requires_human_target_linkage():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        source=Entity(name="Alpha Capital",canonical_name="alpha capital",universe="venture_capital");db.add(source);db.flush();text="Alpha Capital partnered with Gamma Partners.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=source.id,publisher="alpha.example",publisher_independence_group="alpha.example",source_rank="S1",source_type="official_website",source_url="https://alpha.example/news",content_hash=digest);db.add(document);db.flush();db.add(EvidencePassage(document_id=document.id,passage=text,passage_hash=digest));db.flush();result=discover_relationship_candidates(db);mention=db.scalar(select(RelationshipMentionCandidate));assert result["unresolved_mentions_queued"]==1 and mention.mention_text=="Gamma Partners" and db.scalar(select(RelationshipResearchCandidate)) is None
        target=Entity(name="Gamma Partners",canonical_name="gamma partners",universe="private_equity");db.add(target);db.flush();adjudicate_relationship_mention(db,mention.id,"LINK_TARGET","resolver","Official identity review links the exact named mention","ENTITY_RESOLUTION_REQUIRED",target.id);candidate=db.get(RelationshipResearchCandidate,mention.resulting_candidate_id);assert mention.status=="TARGET_LINKED" and candidate.to_entity_id==target.id and candidate.status=="HUMAN_REVIEW_REQUIRED"
