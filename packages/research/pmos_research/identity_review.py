from __future__ import annotations

import json
from urllib.parse import urlparse

from sqlalchemy import select

from .adjudication import AdjudicationInputError,_exact_pair_cluster,_identity_pair,_version
from .db import Contact,Entity,Evidence,IdentityCluster,IdentityMembership,RawImportRow,ResolutionDecision,ReviewQueueItem

def _domain(value:str|None)->str|None:
    parsed=urlparse(value or "");return parsed.hostname.removeprefix("www.") if parsed.hostname else None

def _identity(entity:Entity|None,contact:Contact|None)->dict|None:
    if entity:return {"kind":"ENTITY","id":entity.id,"label":entity.name,"universe":entity.universe,"entity_type":entity.entity_type,"country":entity.country,"city":entity.city,"official_domain":_domain(entity.official_url)}
    if contact:return {"kind":"PERSON","id":contact.id,"label":contact.name,"title":contact.title,"entity_id":contact.entity_id}
    return None

def build_review_packet(session,item_id:int,include_excerpt:bool=False)->dict:
    item=session.get(ReviewQueueItem,item_id)
    if not item:raise ValueError("unknown review item")
    decision=session.get(ResolutionDecision,item.resolution_decision_id);raw=session.get(RawImportRow,decision.raw_row_id)
    source_entity=session.get(Entity,raw.entity_id) if raw and raw.entity_id else None
    candidate_entity=session.get(Entity,decision.candidate_entity_id) if decision.candidate_entity_id else None
    source_contact=session.get(Contact,raw.contact_id) if raw and raw.contact_id else None
    candidate_contact=session.get(Contact,decision.candidate_contact_id) if decision.candidate_contact_id else None
    entity_ids={x for x in (source_entity.id if source_entity else None,candidate_entity.id if candidate_entity else None,source_contact.entity_id if source_contact else None,candidate_contact.entity_id if candidate_contact else None) if x}
    evidence=session.scalars(select(Evidence).where(Evidence.entity_id.in_(entity_ids)).order_by(Evidence.retrieved_at.desc(),Evidence.id).limit(25)).all() if entity_ids else []
    evidence_rows=[]
    for row in evidence:
        value={"id":row.id,"entity_id":row.entity_id,"source_url":row.source_url,"source_type":row.source_type,"retrieved_at":row.retrieved_at.isoformat(),"content_hash":row.content_hash,"title":row.title,"confidence":row.confidence}
        if include_excerpt:value["text_excerpt"]=row.text_excerpt
        evidence_rows.append(value)
    universe=(candidate_entity.universe if candidate_entity else source_entity.universe if source_entity else "imported_private")
    blockers=[];active_cluster_count=0;exact_proposal=False;distinct_pair=False
    try:
        kind,ids=_identity_pair(session,item,decision);distinct_pair=True;column=IdentityMembership.entity_id if kind=="ENTITY" else IdentityMembership.contact_id
        active_cluster_count=len(set(session.scalars(select(IdentityCluster.id).join(IdentityMembership).where(IdentityCluster.identity_type==kind,IdentityCluster.status.in_(("PROPOSED","ACCEPTED")),column.in_(ids))).all()))
        exact_proposal=_exact_pair_cluster(session,item,decision,"PROPOSED") is not None
        if item.status in {"PENDING","DEFERRED"} and active_cluster_count:blockers.append("IDENTITY_ALREADY_IN_ACTIVE_CLUSTER")
        if item.status=="PROPOSED" and not exact_proposal:blockers.append("EXACT_PAIR_PROPOSAL_MISSING")
    except AdjudicationInputError:blockers.append("DISTINCT_IDENTITY_PAIR_REQUIRED")
    controls={"distinct_pair":distinct_pair,"active_cluster_count":active_cluster_count,"exact_pair_proposal_present":exact_proposal,"can_propose":item.status in {"PENDING","DEFERRED"} and distinct_pair and active_cluster_count==0,"can_approve":item.status=="PROPOSED" and exact_proposal,"blockers":blockers}
    return {"classification":"PRIVATE—AUTHORIZED REVIEW ONLY","id":item.id,"version":_version(item),"queue_type":item.queue_type,"priority":item.priority,"status":item.status,"universe":universe,"resolution":{"state":decision.state,"confidence":decision.confidence,"reasons":json.loads(decision.reasons_json)},"source_identity":_identity(source_entity,source_contact),"candidate_identity":_identity(candidate_entity,candidate_contact),"adjudication_controls":controls,"evidence":evidence_rows,"raw_row_exposed":False}
