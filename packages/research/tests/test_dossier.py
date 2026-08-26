from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Claim,ClaimEvidence,ConflictCase,ConflictMember,Entity,EvidencePassage,ResearchPassageCandidate,ResearchSourceCandidate,SourceDocument
from pmos_research.diligence import open_case
from pmos_research.dossier import build_dossier

def test_dossier_traces_claims_to_exact_passages_and_surfaces_conflicts():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Example Capital",canonical_name="example capital",universe="venture_capital",country="US");db.add(entity);db.flush()
        case=open_case(db,entity.id,"venture capital","counterparty assessment","internal diligence","maker")
        document=SourceDocument(entity_id=entity.id,publisher="Official Registry",publisher_independence_group="registry",source_rank="S0",source_type="registry",source_url="https://registry.example/entity",content_hash="a"*64);db.add(document);db.flush()
        passage=EvidencePassage(document_id=document.id,section="legal name",passage="The legal name is Example Capital LLC.",passage_hash="b"*64);db.add(passage);db.flush()
        first=Claim(entity_id=entity.id,field="legal_name",value="Example Capital LLC",source_url=document.source_url,source_type="registry",confidence=1,verification_status="SUPPORTED",extractor="registry",evidence_hash=document.content_hash)
        second=Claim(entity_id=entity.id,field="legal_name",value="Example Capital LP",source_url="https://other.example",source_type="official",confidence=.7,verification_status="CANDIDATE",extractor="deterministic")
        db.add_all([first,second]);db.flush();db.add(ClaimEvidence(claim_id=first.id,passage_id=passage.id,directness=1,supports=True))
        conflict=ConflictCase(entity_id=entity.id,predicate="legal_identity",materiality="MATERIAL");db.add(conflict);db.flush();db.add_all([ConflictMember(conflict_id=conflict.id,claim_id=first.id),ConflictMember(conflict_id=conflict.id,claim_id=second.id)]);db.commit()
        source_candidate=ResearchSourceCandidate(entity_id=entity.id,source_url=document.source_url,source_domain="registry.example",document_type="LEGAL_IDENTITY",target_predicates_json='["legal_identity"]',discovered_from_url="https://registry.example",discovery_score=95,status="RETRIEVED_REVIEW_REQUIRED");db.add(source_candidate);db.flush();db.add(ResearchPassageCandidate(source_candidate_id=source_candidate.id,evidence_passage_id=passage.id,predicate="legal_identity",confidence=.75));db.commit()
        result=build_dossier(db,case.id)
        assert result["classification"]=="PRIVATE—AUTHORIZED USE ONLY"
        assert result["evidence_coverage"]=={"claim_count":2,"exact_passage_linked":1,"unlinked":1}
        assert result["claims"][0]["evidence"][0]["passage"]=="The legal name is Example Capital LLC."
        assert result["recorded_conflicts"][0]["claim_ids"]==[first.id,second.id]
        assert result["potential_conflicts"][0]["state"]=="HUMAN_REVIEW_REQUIRED"
        assert result["research_queue"]["passages"][0]["status"]=="HUMAN_REVIEW_REQUIRED"
        assert result["readiness"]["state"]=="RED"
