from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Claim,ClaimCheckRoutingCandidate,CheckResult,DiligenceCheckEvidence,Entity
from pmos_research.diligence import open_case
from pmos_research.evidence_route_review import build_route_packet
from pmos_research.evidence_routing import adjudicate_route,queue_claim_routes

def test_supported_claim_routes_to_matching_open_check_without_completing_it():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        entity=Entity(name="Example Fund",canonical_name="example fund",universe="private_equity");db.add(entity);db.flush();case=open_case(db,entity.id,"private equity","assessment","internal","owner")
        claim=Claim(entity_id=entity.id,field="fund_domicile",value="Luxembourg",source_url="https://official.example",source_type="official_website",confidence=.8,verification_status="SUPPORTED",extractor="review",evidence_hash="a"*64);db.add(claim);db.flush()
        route_ids=queue_claim_routes(db,claim);assert len(route_ids)==1
        packet=build_route_packet(db,route_ids[0]);assert packet["check"]["fact_class"]=="fund_domicile" and packet["status"]=="PENDING_REVIEW"
        result=adjudicate_route(db,route_ids[0],"ATTACH","researcher","Attach the supported domicile claim to the matching procedure","PENDING_REVIEW");db.commit()
        assert result["resulting_state"]=="ATTACHED" and result["check_status"]=="EVIDENCE_COLLECTED"
        assert db.scalar(select(func.count()).select_from(DiligenceCheckEvidence))==1
        assert db.get(CheckResult,result["check_id"]).status!="SPECIALIST_VERIFIED"
        assert queue_claim_routes(db,claim)==route_ids and db.scalar(select(func.count()).select_from(ClaimCheckRoutingCandidate))==1
