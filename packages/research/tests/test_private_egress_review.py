from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

from pmos_research.db import Base,CorroborationJob,Entity,PrivateEgressReviewCase
from pmos_research.private_egress_review import PrivateEgressReviewError,adjudicate_private_egress,build_private_egress_packet

def test_private_egress_review_is_redacted_and_requires_independent_unchanged_approval():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Confidential Name",canonical_name="confidential name",universe="imported_private");db.add(entity);db.flush();job=CorroborationJob(entity_id=entity.id,source_url="https://example.test/team",source_domain="example.test",status="SUPPORTED",attempts=1,checkpoint_json="{}");db.add(job);db.flush();case=PrivateEgressReviewCase(corroboration_job_id=job.id,prior_status="SUPPORTED",attempts_observed=1,status="OPEN",reason="Legacy attempt requires review");db.add(case);db.flush();packet=build_private_egress_packet(db,case.id);serialized=str(packet);assert "Confidential Name" not in serialized and "https://" not in serialized and packet["evidence"]["request_method"]=="GET"
        adjudicate_private_egress(db,case.id,"PROPOSE_NO_MATERIAL_DISCLOSURE","maker","ADMIN","Review of the request metadata found no query values","OPEN")
        with pytest.raises(PrivateEgressReviewError,match="independent approval"):adjudicate_private_egress(db,case.id,"APPROVE_NO_MATERIAL_DISCLOSURE","maker","ADMIN","Maker cannot approve the same assessment package","NO_MATERIAL_DISCLOSURE_PROPOSED")
        adjudicate_private_egress(db,case.id,"APPROVE_NO_MATERIAL_DISCLOSURE","checker","COUNSEL","Independent counsel reviewed the unchanged metadata package","NO_MATERIAL_DISCLOSURE_PROPOSED");assert case.status=="RESOLVED_NO_MATERIAL_DISCLOSURE"

def test_query_metadata_forces_escalation():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        entity=Entity(name="Private",canonical_name="private",universe="imported_private");db.add(entity);db.flush();job=CorroborationJob(entity_id=entity.id,source_url="https://example.test/?name=value",source_domain="example.test",status="FAILED",attempts=1,checkpoint_json="{}");db.add(job);db.flush();case=PrivateEgressReviewCase(corroboration_job_id=job.id,prior_status="FAILED",attempts_observed=1,status="OPEN",reason="Legacy attempt requires review");db.add(case);db.flush();adjudicate_private_egress(db,case.id,"PROPOSE_NO_MATERIAL_DISCLOSURE","maker","ADMIN","Initial assessment proposes no material disclosure","OPEN")
        with pytest.raises(PrivateEgressReviewError,match="requires escalation"):adjudicate_private_egress(db,case.id,"APPROVE_NO_MATERIAL_DISCLOSURE","checker","COUNSEL","Independent reviewer cannot close query-bearing request","NO_MATERIAL_DISCLOSURE_PROPOSED")
