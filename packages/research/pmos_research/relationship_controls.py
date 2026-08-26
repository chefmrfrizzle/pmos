from __future__ import annotations

import hashlib,re,secrets
from datetime import datetime,timezone
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import Entity,EvidencePassage,RelationshipAdjudicationEvent,RelationshipAssertion,RelationshipAssertionEvidence,SourceDocument

ALLOWED_RELATIONSHIPS={"OWNS","MANAGES","ADVISES","ALLOCATES_TO","INVESTED_IN","CO_INVESTED_WITH","TRUSTEE_OF","BOARD_MEMBER_OF","REPRESENTS","FINANCES","INSURES","REINSURES","BROKERS_FOR","CUSTODIES","ADMINISTERS","INTRODUCED_BY","WORKS_FOR","FOUNDED","CONTROLS","BOUGHT_FROM","SOLD_TO","ADVISED_BY","RELATED_TO","PARTNERED_WITH","BENEFICIAL_OWNER_OF"}
SENSITIVE_RELATIONSHIPS={"OWNS","CONTROLS","BENEFICIAL_OWNER_OF","TRUSTEE_OF"}
QUALIFYING_CORROBORATION={"S0","S1","S2","S3"}
RELATIONSHIP_TERMS={
    "OWNS":("owns","owned by","ownership"),"CONTROLS":("controls","controlled by","control of"),"BENEFICIAL_OWNER_OF":("beneficial owner","beneficially owns"),"TRUSTEE_OF":("trustee of","serves as trustee"),
    "MANAGES":("manages","managed by","investment manager"),"ADVISES":("advises","advisor to","adviser to","advisory relationship"),"ADVISED_BY":("advised by","advisor is","adviser is"),
    "ALLOCATES_TO":("allocates to","allocation to","committed to"),"INVESTED_IN":("invested in","investment in"),"CO_INVESTED_WITH":("co-invested with","co-investment with"),
    "PARTNERED_WITH":("partnered with","partnership with"),"BOARD_MEMBER_OF":("board member of","director of"),"REPRESENTS":("represents","represented by"),
    "FINANCES":("finances","financed by","financing for"),"INSURES":("insures","insured by"),"REINSURES":("reinsures","reinsured by"),"BROKERS_FOR":("brokers for","broker for"),
    "CUSTODIES":("custodies","custodian for"),"ADMINISTERS":("administers","administrator for"),"INTRODUCED_BY":("introduced by","introduction by"),"WORKS_FOR":("works for","employed by"),
    "FOUNDED":("founded","founder of"),"BOUGHT_FROM":("bought from","purchased from"),"SOLD_TO":("sold to","sale to"),"RELATED_TO":("related to","affiliated with"),
}

def _utc(value):return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
def _norm(value):return " ".join(re.sub(r"[^a-z0-9]+"," ",value.casefold()).split())

def _evidence_rows(session,assertion_id:int):
    return session.execute(select(RelationshipAssertionEvidence,EvidencePassage,SourceDocument).join(EvidencePassage,RelationshipAssertionEvidence.evidence_passage_id==EvidencePassage.id).join(SourceDocument,RelationshipAssertionEvidence.source_document_id==SourceDocument.id).where(RelationshipAssertionEvidence.relationship_assertion_id==assertion_id).order_by(SourceDocument.id,EvidencePassage.id)).all()

def _package_hash(rows)->str:
    material="|".join(f"{document.id}:{document.content_hash}:{passage.id}:{passage.passage_hash}" for _,passage,document in rows)
    return hashlib.sha256(material.encode()).hexdigest()

def relationship_evidence_controls(session,assertion:RelationshipAssertion)->dict:
    rows=_evidence_rows(session,assertion.id);now=datetime.now(timezone.utc);threshold=90 if assertion.sensitive else 365;bad_hash=0;out_of_scope=0;stale=0;semantic=0;duplicate=0;groups=set();ranks=set();factors=[];seen_content=set();source=session.get(Entity,assertion.from_entity_id);target=session.get(Entity,assertion.to_entity_id)
    for _,passage,document in rows:
        hash_valid=hashlib.sha256(passage.passage.encode()).hexdigest()==passage.passage_hash;scope_valid=document.entity_id in {assertion.from_entity_id,assertion.to_entity_id};text=_norm(passage.passage);names_valid=bool(source and target and _norm(source.name) in text and _norm(target.name) in text);terms=RELATIONSHIP_TERMS.get(assertion.relation_type,());relation_language=any(_norm(term) in text for term in terms);semantic_valid=names_valid and relation_language
        bad_hash+=not hash_valid;out_of_scope+=not scope_valid;semantic+=not semantic_valid
        age=max(0,(now-_utc(document.retrieved_at)).days);fresh=age<=threshold;stale+=not fresh;duplicate_content=document.content_hash in seen_content;duplicate+=duplicate_content
        eligible=hash_valid and scope_valid and fresh and semantic_valid and not duplicate_content
        if eligible:
            seen_content.add(document.content_hash);ranks.add(document.source_rank)
            if document.source_rank in QUALIFYING_CORROBORATION:groups.add(document.publisher_independence_group)
        factors.append({"source_document_id":document.id,"passage_id":passage.id,"source_rank":document.source_rank,"independence_group":document.publisher_independence_group,"age_days":age,"freshness_threshold_days":threshold,"passage_hash_valid":hash_valid,"entity_pair_named":names_valid,"relationship_language_present":relation_language,"duplicate_content":duplicate_content,"eligible":eligible})
    sufficient="S0" in ranks if assertion.sensitive else "S0" in ranks or (len(groups)>=2 and bool(ranks & {"S1","S2"}));evidence_integrity=bool(rows) and bad_hash==0 and out_of_scope==0 and stale==0;semantic_valid=bool(rows) and semantic==0;integrity=evidence_integrity and semantic_valid
    rank_score=max(({"S0":1.0,"S1":.9,"S2":.8,"S3":.65}.get(x,.3) for x in ranks),default=0);independence_bonus=min(.1,max(0,len(groups)-1)*.05);confidence=round(min(1,rank_score+independence_bonus) if integrity and sufficient else min(.49,rank_score*.5),2)
    gaps=[]
    if not rows:gaps.append("NO_EXACT_EVIDENCE")
    if bad_hash:gaps.append("PASSAGE_HASH_FAILURE")
    if out_of_scope:gaps.append("ENTITY_SCOPE_FAILURE")
    if stale:gaps.append("STALE_EVIDENCE")
    if semantic:gaps.append("RELATIONSHIP_LANGUAGE_OR_ENTITY_PAIR_MISSING")
    if duplicate:gaps.append("SYNDICATED_OR_DUPLICATE_CONTENT_EXCLUDED")
    if assertion.sensitive and "S0" not in ranks:gaps.append("DISPOSITIVE_S0_REQUIRED")
    if not assertion.sensitive and "S0" not in ranks:
        if not ranks & {"S1","S2"}:gaps.append("S1_OR_S2_REQUIRED")
        if len(groups)<2:gaps.append("SECOND_INDEPENDENT_PUBLISHER_REQUIRED")
    return {"evidence_count":len(rows),"eligible_evidence_count":sum(x["eligible"] for x in factors),"passage_hash_exceptions":bad_hash,"entity_scope_exceptions":out_of_scope,"semantic_scope_exceptions":semantic,"stale_source_count":stale,"duplicate_content_count":duplicate,"source_ranks":sorted(ranks),"independence_groups":sorted(groups),"independence_group_count":len(groups),"policy":"DISPOSITIVE_S0" if assertion.sensitive else "S0_OR_TWO_INDEPENDENT_S1_TO_S3_INCLUDING_S1_OR_S2","policy_sufficient":sufficient,"evidence_integrity_valid":evidence_integrity,"semantic_scope_valid":semantic_valid,"integrity_valid":integrity,"verification_eligible":integrity and sufficient,"corroboration_gaps":gaps,"evidence_confidence":confidence,"confidence_factors":factors,"evidence_package_hash":_package_hash(rows)}

def propose_relationship(session,from_entity_id:int,to_entity_id:int,relation_type:str,proposer:str,evidence_passage_ids,jurisdiction:str|None=None):
    relation_type=relation_type.upper().strip()
    if relation_type not in ALLOWED_RELATIONSHIPS:raise ValueError("unsupported relationship type")
    if from_entity_id==to_entity_id:raise ValueError("self-relationships require a separate specialist workflow")
    if not proposer.strip():raise ValueError("proposer is required")
    if not session.get(Entity,from_entity_id) or not session.get(Entity,to_entity_id):raise ValueError("both entities must exist")
    ids=sorted(set(int(x) for x in evidence_passage_ids));passages=session.scalars(select(EvidencePassage).where(EvidencePassage.id.in_(ids))).all() if ids else []
    if not passages or len(passages)!=len(ids):raise ValueError("all exact evidence passages must exist")
    documents={x.id:x for x in session.scalars(select(SourceDocument).where(SourceDocument.id.in_({x.document_id for x in passages}))).all()}
    if len(documents)!=len({x.document_id for x in passages}):raise ValueError("evidence document chain is incomplete")
    if any(hashlib.sha256(x.passage.encode()).hexdigest()!=x.passage_hash for x in passages):raise ValueError("relationship evidence passage hash failed")
    if any(documents[x.document_id].entity_id not in {from_entity_id,to_entity_id} for x in passages):raise ValueError("relationship evidence is outside the reviewed entity pair")
    assertion=RelationshipAssertion(from_entity_id=from_entity_id,to_entity_id=to_entity_id,relation_type=relation_type,jurisdiction=jurisdiction,sensitive=relation_type in SENSITIVE_RELATIONSHIPS,status="HUMAN_REVIEW_REQUIRED",proposed_by=proposer);session.add(assertion);session.flush()
    for passage in passages:session.add(RelationshipAssertionEvidence(relationship_assertion_id=assertion.id,source_document_id=passage.document_id,evidence_passage_id=passage.id))
    session.flush();controls=relationship_evidence_controls(session,assertion);session.add(RelationshipAdjudicationEvent(relationship_assertion_id=assertion.id,action="PROPOSE",prior_state=None,resulting_state=assertion.status,actor=proposer,rationale="Relationship proposed for independent specialist review",evidence_package_hash=controls["evidence_package_hash"]))
    append_ledger_event(session,"RELATIONSHIP_ASSERTION",assertion.id,proposer,"RESEARCHER","PROPOSED",{"relation_type":relation_type,"evidence_passage_ids":ids,"sensitive":assertion.sensitive,"evidence_package_hash":controls["evidence_package_hash"],"evidence_confidence":controls["evidence_confidence"]});return assertion

def adjudicate_relationship(session,assertion_id:int,action:str,reviewer:str,rationale:str,expected_status:str|None=None):
    assertion=session.get(RelationshipAssertion,assertion_id)
    if not assertion:raise ValueError("unknown relationship assertion")
    if expected_status is not None and assertion.status!=expected_status:raise ValueError("relationship assertion changed; reload before deciding")
    if reviewer==assertion.proposed_by:raise ValueError("independent reviewer required")
    if len(rationale.strip())<10:raise ValueError("substantive review rationale is required")
    action=action.upper();transitions={"HUMAN_REVIEW_REQUIRED":{"APPROVE":"SPECIALIST_VERIFIED","REJECT":"REJECTED","DEFER":"DEFERRED"},"DEFERRED":{"APPROVE":"SPECIALIST_VERIFIED","REJECT":"REJECTED"}}
    if action not in transitions.get(assertion.status,{}):raise ValueError(f"invalid transition {assertion.status} -> {action}")
    controls=relationship_evidence_controls(session,assertion);proposal=session.scalar(select(RelationshipAdjudicationEvent).where(RelationshipAdjudicationEvent.relationship_assertion_id==assertion.id,RelationshipAdjudicationEvent.action=="PROPOSE").order_by(RelationshipAdjudicationEvent.id))
    if not proposal or not secrets.compare_digest(proposal.evidence_package_hash,controls["evidence_package_hash"]):raise ValueError("relationship evidence package changed after proposal")
    if action=="APPROVE" and not controls["verification_eligible"]:raise ValueError("evidence does not meet relationship verification policy")
    prior=assertion.status;result=transitions[prior][action];assertion.status=result
    if action=="APPROVE":assertion.reviewed_by=reviewer;assertion.review_rationale=rationale.strip();assertion.reviewed_at=datetime.now(timezone.utc)
    session.add(RelationshipAdjudicationEvent(relationship_assertion_id=assertion.id,action=action,prior_state=prior,resulting_state=result,actor=reviewer,rationale=rationale.strip(),evidence_package_hash=controls["evidence_package_hash"]))
    append_ledger_event(session,"RELATIONSHIP_ASSERTION",assertion.id,reviewer,"REVIEWER",action,{"prior_state":prior,"resulting_state":result,"rationale":rationale.strip(),"evidence_package_hash":controls["evidence_package_hash"],"evidence_confidence":controls["evidence_confidence"]});session.flush();return assertion

def verify_relationship(session,assertion_id:int,reviewer:str,rationale:str):return adjudicate_relationship(session,assertion_id,"APPROVE",reviewer,rationale)
