import hashlib,pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker

from pmos_research.db import Base,Claim,ClaimEvidence,Entity,EvidencePassage,PrivateSaleGate,SourceDocument
from pmos_research.private_sale import PrivateSaleError,adjudicate_gate,gate_sufficiency,open_private_sale,private_sale_readiness,submit_gate_evidence

def _claim(db,entity,field,value,rank="S0",group="registry"):
    text=f"The reviewed record states: {value}.";digest=hashlib.sha256(text.encode()).hexdigest();document=SourceDocument(entity_id=entity.id,publisher=group,publisher_independence_group=group,source_rank=rank,source_type="registry",source_url=f"https://{group}.example/{field}",content_hash=digest);db.add(document);db.flush();passage=EvidencePassage(document_id=document.id,section=field,passage=text,passage_hash=digest);db.add(passage);db.flush();claim=Claim(entity_id=entity.id,field=field,value=value,source_url=document.source_url,source_type=document.source_type,confidence=.9,verification_status="SUPPORTED",extractor="test",evidence_hash=digest);db.add(claim);db.flush();db.add(ClaimEvidence(claim_id=claim.id,passage_id=passage.id,directness=.9,supports=True));db.flush();return claim

def test_private_sale_gates_require_exact_evidence_maker_checker_and_counsel():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        asset=Entity(name="Artwork A",canonical_name="artwork a",universe="asset",entity_type="ASSET");seller=Entity(name="Seller",canonical_name="seller",universe="private_client");db.add_all([asset,seller]);db.flush();case=open_private_sale(db,asset.id,seller.id,"private sale assessment","transaction diligence","owner","GB")
        gates={x.gate_code:x for x in db.scalars(select(PrivateSaleGate).where(PrivateSaleGate.case_id==case.id))};assert len(gates)==9 and private_sale_readiness(db,case.id)["state"]=="RED"
        authority=_claim(db,seller,"authority_to_transact","Seller has authority to sell");submit_gate_evidence(db,gates["authority_to_sell"].id,[authority.id],"researcher");assert gate_sufficiency(db,gates["authority_to_sell"].id)["sufficient"]
        adjudicate_gate(db,gates["authority_to_sell"].id,"PROPOSE_PASS","maker","RESEARCHER","Dispositive authority evidence is attached","EVIDENCE_COLLECTED")
        with pytest.raises(PrivateSaleError):adjudicate_gate(db,gates["authority_to_sell"].id,"APPROVE","maker","REVIEWER","Self approval is prohibited","REVIEW_PROPOSED")
        adjudicate_gate(db,gates["authority_to_sell"].id,"APPROVE","checker","REVIEWER","Independent review confirms authority evidence","REVIEW_PROPOSED");assert gates["authority_to_sell"].status=="PASS"
        one=_claim(db,asset,"restitution_review","No identified restitution claim","S1","specialist-one");two=_claim(db,asset,"restitution_review","No identified restitution claim","S2","specialist-two");submit_gate_evidence(db,gates["restitution"].id,[one.id,two.id],"researcher");adjudicate_gate(db,gates["restitution"].id,"PROPOSE_PASS","maker","RESEARCHER","Independent restitution evidence is attached","EVIDENCE_COLLECTED")
        with pytest.raises(PrivateSaleError,match="counsel"):adjudicate_gate(db,gates["restitution"].id,"APPROVE","checker","REVIEWER","Reviewer lacks counsel authority for this gate","REVIEW_PROPOSED")
        adjudicate_gate(db,gates["restitution"].id,"APPROVE","counsel","COUNSEL","Counsel confirms the scoped restitution review","REVIEW_PROPOSED");assert gates["restitution"].status=="PASS"

def test_private_sale_approval_rejects_changed_evidence_package():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        asset=Entity(name="Artwork A",canonical_name="artwork a",universe="asset");seller=Entity(name="Seller",canonical_name="seller",universe="private_client");db.add_all([asset,seller]);db.flush();case=open_private_sale(db,asset.id,seller.id,"assessment","diligence","owner");gate=db.scalar(select(PrivateSaleGate).where(PrivateSaleGate.case_id==case.id,PrivateSaleGate.gate_code=="authority_to_sell"));claim=_claim(db,seller,"authority_to_transact","Seller has authority to sell");submit_gate_evidence(db,gate.id,[claim.id],"researcher");adjudicate_gate(db,gate.id,"PROPOSE_PASS","maker","RESEARCHER","Authority evidence is proposed for review","EVIDENCE_COLLECTED");claim.value="Altered after proposal";db.flush()
        with pytest.raises(PrivateSaleError,match="evidence package changed"):adjudicate_gate(db,gate.id,"APPROVE","checker","REVIEWER","Approval must use the maker evidence package","REVIEW_PROPOSED")
