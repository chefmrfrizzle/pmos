from __future__ import annotations

import hashlib,json,re,secrets
from collections import Counter
from datetime import datetime,timezone
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import Entity,EvidencePassage,RelationshipMentionCandidate,RelationshipMentionCandidateEvent,RelationshipMentionResolution,RelationshipMentionResolutionEvent,RelationshipResearchCandidate,RelationshipResearchCandidateEvent,SourceDocument
from .relationship_controls import propose_relationship

RULE_VERSION="relationship_phrase_v1"
RULES={
    "PARTNERED_WITH":("partnered with","partnership with","strategic partnership"),
    "INVESTED_IN":("invested in","investment in"),
    "ADVISES":("advises","advisor to","adviser to"),
    "MANAGES":("manages","manager of"),
    "ALLOCATES_TO":("allocated to","allocation to"),
}
class RelationshipResearchError(ValueError):pass
def _norm(value):return " ".join(re.sub(r"[^a-z0-9]+"," ",value.casefold()).split())

def _named_object_after_phrase(text:str,phrase:str)->str|None:
    phrase_match=re.search(re.escape(phrase),text,re.I)
    if not phrase_match:return None
    remainder=text[phrase_match.end():].lstrip();match=re.match(r"(?:an?\s+|the\s+)?([A-Z][A-Za-z0-9&'’.-]*(?:\s+(?:[A-Z][A-Za-z0-9&'’.-]*|of|the|and)){0,7})",remainder)
    if not match:return None
    value=" ".join(match.group(1).split()).strip(" .,:;-")
    return value if 2<=len(value)<=300 and any(c.isalpha() for c in value) else None

def discover_relationship_candidates(session,limit:int=100)->dict:
    if not 1<=limit<=500:raise RelationshipResearchError("limit must be between 1 and 500")
    targets=session.scalars(select(Entity).where(Entity.universe!="imported_private").order_by(Entity.id)).all();target_names=[(x,_norm(x.name)) for x in targets if len(_norm(x.name))>=5]
    existing={(x.from_entity_id,x.to_entity_id,x.suggested_relation_type,x.evidence_passage_id) for x in session.scalars(select(RelationshipResearchCandidate)).all()};existing_mentions={(x.from_entity_id,x.suggested_relation_type,x.evidence_passage_id,x.mention_hash) for x in session.scalars(select(RelationshipMentionCandidate)).all()};passages=session.execute(select(EvidencePassage,SourceDocument).join(SourceDocument,SourceDocument.id==EvidencePassage.document_id).order_by(EvidencePassage.id)).all();counts=Counter()
    for passage,document in passages:
        source=session.get(Entity,document.entity_id);text=_norm(passage.passage)
        if not source or not text:continue
        for relation,phrases in RULES.items():
            matched=next((phrase for phrase in phrases if _norm(phrase) in text),None)
            if not matched:continue
            matched_target=False
            for target,target_name in target_names:
                if target.id==source.id or target_name not in text:continue
                matched_target=True
                key=(source.id,target.id,relation,passage.id)
                if key in existing:counts["existing"]+=1;continue
                reasons=["full normalized registered counterparty name appears in exact passage",f"controlled phrase: {matched}","candidate only; direction and context require specialist review"]
                session.add(RelationshipResearchCandidate(from_entity_id=source.id,to_entity_id=target.id,suggested_relation_type=relation,evidence_passage_id=passage.id,rule_version=RULE_VERSION,confidence=.6,reasons_json=json.dumps(reasons)));existing.add(key);counts[relation]+=1;counts["queued"]+=1
                if counts["queued"]>=limit:session.flush();append_ledger_event(session,"RELATIONSHIP_RESEARCH","DISCOVERY","relationship-research-worker","SYSTEM","CANDIDATES_DISCOVERED",{"queued":counts["queued"],"rule_version":RULE_VERSION});return dict(sorted(counts.items()))
            if not matched_target:
                mention=_named_object_after_phrase(passage.passage,matched);mention_hash=hashlib.sha256(_norm(mention or "").encode()).hexdigest() if mention else None;key=(source.id,relation,passage.id,mention_hash)
                if mention and key not in existing_mentions:
                    session.add(RelationshipMentionCandidate(from_entity_id=source.id,suggested_relation_type=relation,evidence_passage_id=passage.id,matched_phrase=matched,mention_text=mention,mention_hash=mention_hash,rule_version=RULE_VERSION));existing_mentions.add(key);counts["unresolved_mentions_queued"]+=1
    session.flush()
    if counts["queued"] or counts["unresolved_mentions_queued"]:append_ledger_event(session,"RELATIONSHIP_RESEARCH","DISCOVERY","relationship-research-worker","SYSTEM","CANDIDATES_DISCOVERED",{"queued":counts["queued"],"unresolved_mentions_queued":counts["unresolved_mentions_queued"],"rule_version":RULE_VERSION})
    return dict(sorted(counts.items()))

def build_relationship_mention_packet(session,mention_id:int)->dict:
    mention=session.get(RelationshipMentionCandidate,mention_id)
    if not mention:raise RelationshipResearchError("unknown relationship mention")
    source=session.get(Entity,mention.from_entity_id);passage=session.get(EvidencePassage,mention.evidence_passage_id);document=session.get(SourceDocument,passage.document_id) if passage else None
    if not source or not passage or not document or document.entity_id!=source.id:raise RelationshipResearchError("relationship mention evidence chain is incomplete")
    resolution=session.scalar(select(RelationshipMentionResolution).where(RelationshipMentionResolution.mention_candidate_id==mention.id).order_by(RelationshipMentionResolution.version.desc()))
    target=session.get(Entity,resolution.target_entity_id) if resolution else None
    return {"classification":"PRIVATE—AUTHORIZED RELATIONSHIP ENTITY RESOLUTION","id":mention.id,"status":mention.status,"suggested_relation_type":mention.suggested_relation_type,"matched_phrase":mention.matched_phrase,"mention_text":mention.mention_text,"mention_hash":mention.mention_hash,"source_entity":{"id":source.id,"name":source.name,"universe":source.universe},"evidence":{"passage_id":passage.id,"passage":passage.passage,"passage_hash":passage.passage_hash,"document_hash":document.content_hash,"source_url":document.source_url},"resolution":{"id":resolution.id,"version":resolution.version,"status":resolution.status,"target_entity":{"id":target.id,"name":target.name,"universe":target.universe} if target else None,"proposed_by":resolution.proposed_by,"proposal_rationale":resolution.proposal_rationale,"identity_package_hash":resolution.identity_package_hash,"reviewed_by":resolution.reviewed_by,"review_rationale":resolution.review_rationale} if resolution else None,"resolved_entity_id":mention.resolved_entity_id,"resulting_candidate_id":mention.resulting_candidate_id}

def mention_identity_package_hash(session,mention:RelationshipMentionCandidate,target:Entity)->str:
    source=session.get(Entity,mention.from_entity_id);passage=session.get(EvidencePassage,mention.evidence_passage_id);document=session.get(SourceDocument,passage.document_id) if passage else None
    if not source or not passage or not document or document.entity_id!=source.id or hashlib.sha256(passage.passage.encode()).hexdigest()!=passage.passage_hash:raise RelationshipResearchError("relationship mention identity package failed evidence integrity")
    material={"mention_id":mention.id,"mention_hash":mention.mention_hash,"relation_type":mention.suggested_relation_type,"rule_version":mention.rule_version,"source":{"id":source.id,"canonical_name":source.canonical_name,"universe":source.universe,"country":source.country,"official_url":source.official_url},"target":{"id":target.id,"canonical_name":target.canonical_name,"universe":target.universe,"country":target.country,"official_url":target.official_url},"document_hash":document.content_hash,"passage_hash":passage.passage_hash}
    return hashlib.sha256(json.dumps(material,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def adjudicate_relationship_mention(session,mention_id:int,action:str,actor:str,rationale:str,expected_status:str,target_entity_id:int|None=None,review_batch_id:int|None=None,reviewer_role:str="RESEARCHER"):
    mention=session.get(RelationshipMentionCandidate,mention_id)
    if not mention or mention.status!=expected_status:raise RelationshipResearchError("relationship mention changed; reload before deciding")
    if len(rationale.strip())<10:raise RelationshipResearchError("substantive rationale is required")
    action=action.upper();prior=mention.status;approval=action in {"APPROVE_TARGET","REJECT_TARGET"}
    from .relationship_mention_review import RelationshipMentionReviewError,bind_mention_review_decision,validate_mention_review_decision
    try:batch_item,assignment=validate_mention_review_decision(session,review_batch_id or 0,mention,actor,reviewer_role,approval)
    except RelationshipMentionReviewError as exc:raise RelationshipResearchError(str(exc)) from exc
    resolution_event=None
    if prior=="ENTITY_RESOLUTION_REQUIRED" and action=="PROPOSE_TARGET":
        target=session.get(Entity,target_entity_id) if target_entity_id else None
        if not target or target.id==mention.from_entity_id:raise RelationshipResearchError("a distinct registered target entity is required")
        versions=session.scalars(select(RelationshipMentionResolution).where(RelationshipMentionResolution.mention_candidate_id==mention.id).order_by(RelationshipMentionResolution.version)).all()
        if any(x.status in {"HUMAN_REVIEW_REQUIRED","DEFERRED","APPROVED"} for x in versions):raise RelationshipResearchError("an active mention resolution already exists")
        package=mention_identity_package_hash(session,mention,target);resolution=RelationshipMentionResolution(mention_candidate_id=mention.id,target_entity_id=target.id,version=max((x.version for x in versions),default=0)+1,status="HUMAN_REVIEW_REQUIRED",proposed_by=actor,proposal_rationale=rationale.strip(),identity_package_hash=package);session.add(resolution);session.flush();resolution_event=RelationshipMentionResolutionEvent(resolution_id=resolution.id,action=action,prior_state=None,resulting_state=resolution.status,actor=actor,rationale=rationale.strip(),identity_package_hash=package);session.add(resolution_event);result="TARGET_PROPOSED"
    elif prior=="TARGET_PROPOSED" and action in {"APPROVE_TARGET","REJECT_TARGET"}:
        resolution=session.scalar(select(RelationshipMentionResolution).where(RelationshipMentionResolution.mention_candidate_id==mention.id,RelationshipMentionResolution.status=="HUMAN_REVIEW_REQUIRED").order_by(RelationshipMentionResolution.version.desc()))
        if not resolution or resolution.proposed_by==actor:raise RelationshipResearchError("independent mention-resolution reviewer required")
        target=session.get(Entity,resolution.target_entity_id)
        if not target or not secrets.compare_digest(resolution.identity_package_hash,mention_identity_package_hash(session,mention,target)):raise RelationshipResearchError("mention identity package changed after proposal")
        if action=="REJECT_TARGET":resolution.status="REJECTED";resolution.reviewed_by=actor;resolution.review_rationale=rationale.strip();resolution.reviewed_at=datetime.now(timezone.utc);result="ENTITY_RESOLUTION_REQUIRED"
        else:
            resolution.status="APPROVED";resolution.reviewed_by=actor;resolution.review_rationale=rationale.strip();resolution.reviewed_at=datetime.now(timezone.utc)
            candidate=session.scalar(select(RelationshipResearchCandidate).where(RelationshipResearchCandidate.from_entity_id==mention.from_entity_id,RelationshipResearchCandidate.to_entity_id==target.id,RelationshipResearchCandidate.suggested_relation_type==mention.suggested_relation_type,RelationshipResearchCandidate.evidence_passage_id==mention.evidence_passage_id))
            if not candidate:
                candidate=RelationshipResearchCandidate(from_entity_id=mention.from_entity_id,to_entity_id=target.id,suggested_relation_type=mention.suggested_relation_type,evidence_passage_id=mention.evidence_passage_id,rule_version=mention.rule_version,confidence=.6,reasons_json=json.dumps(["maker-checker resolved exact mention to registered entity","identity package and exact passage hash preserved","relationship direction and verification remain review required"]));session.add(candidate);session.flush()
            mention.resolved_entity_id=target.id;mention.resulting_candidate_id=candidate.id;result="TARGET_LINKED"
        resolution_event=RelationshipMentionResolutionEvent(resolution_id=resolution.id,action=action,prior_state="HUMAN_REVIEW_REQUIRED",resulting_state=resolution.status,actor=actor,rationale=rationale.strip(),identity_package_hash=resolution.identity_package_hash);session.add(resolution_event)
    elif prior=="ENTITY_RESOLUTION_REQUIRED" and action in {"REJECT","DEFER"}:result="REJECTED" if action=="REJECT" else "DEFERRED"
    else:raise RelationshipResearchError("unsupported relationship mention transition")
    mention.status=result;mention_event=RelationshipMentionCandidateEvent(mention_candidate_id=mention.id,action=action,prior_state=prior,resulting_state=result,actor=actor,rationale=rationale.strip());session.add(mention_event);session.flush();bind_mention_review_decision(session,batch_item.id,assignment.id,resolution_event_id=resolution_event.id if resolution_event else None,mention_event_id=None if resolution_event else mention_event.id);append_ledger_event(session,"RELATIONSHIP_MENTION",mention.id,actor,"REVIEWER" if action in {"APPROVE_TARGET","REJECT_TARGET"} else "RESEARCHER",action,{"resulting_state":result,"resolved_entity_id":mention.resolved_entity_id,"resulting_candidate_id":mention.resulting_candidate_id,"mention_hash":mention.mention_hash,"review_batch_id":review_batch_id,"assignment_id":assignment.id,"resolution_id":resolution.id if action in {"PROPOSE_TARGET","APPROVE_TARGET","REJECT_TARGET"} else None,"identity_package_hash":resolution.identity_package_hash if action in {"PROPOSE_TARGET","APPROVE_TARGET","REJECT_TARGET"} else None});session.flush();return mention

def build_relationship_candidate_packet(session,candidate_id:int)->dict:
    candidate=session.get(RelationshipResearchCandidate,candidate_id)
    if not candidate:raise RelationshipResearchError("unknown relationship research candidate")
    source=session.get(Entity,candidate.from_entity_id);target=session.get(Entity,candidate.to_entity_id);passage=session.get(EvidencePassage,candidate.evidence_passage_id);document=session.get(SourceDocument,passage.document_id) if passage else None
    if not source or not target or not passage or not document or document.entity_id!=source.id:raise RelationshipResearchError("relationship candidate evidence chain is incomplete")
    return {"classification":"PRIVATE—AUTHORIZED RELATIONSHIP CANDIDATE REVIEW","id":candidate.id,"status":candidate.status,"suggested_relation_type":candidate.suggested_relation_type,"confidence":candidate.confidence,"rule_version":candidate.rule_version,"reasons":json.loads(candidate.reasons_json),"source_entity":{"id":source.id,"name":source.name,"universe":source.universe},"target_entity":{"id":target.id,"name":target.name,"universe":target.universe},"evidence":{"passage_id":passage.id,"passage":passage.passage,"passage_hash":passage.passage_hash,"document_hash":document.content_hash,"source_url":document.source_url,"source_rank":document.source_rank},"resulting_assertion_id":candidate.resulting_assertion_id}

def adjudicate_relationship_candidate(session,candidate_id:int,action:str,actor:str,rationale:str,expected_status:str):
    candidate=session.get(RelationshipResearchCandidate,candidate_id)
    if not candidate or candidate.status!=expected_status:raise RelationshipResearchError("candidate changed; reload before deciding")
    if len(rationale.strip())<10:raise RelationshipResearchError("substantive rationale is required")
    action=action.upper();prior=candidate.status
    if prior!="HUMAN_REVIEW_REQUIRED" or action not in {"PROPOSE_ASSERTION","REJECT","DEFER"}:raise RelationshipResearchError("unsupported relationship candidate transition")
    if action=="PROPOSE_ASSERTION":
        assertion=propose_relationship(session,candidate.from_entity_id,candidate.to_entity_id,candidate.suggested_relation_type,actor,[candidate.evidence_passage_id]);candidate.resulting_assertion_id=assertion.id;result="ASSERTION_PROPOSED"
    else:result="REJECTED" if action=="REJECT" else "DEFERRED"
    candidate.status=result;session.add(RelationshipResearchCandidateEvent(candidate_id=candidate.id,action=action,prior_state=prior,resulting_state=result,actor=actor,rationale=rationale.strip()));append_ledger_event(session,"RELATIONSHIP_RESEARCH_CANDIDATE",candidate.id,actor,"RESEARCHER",action,{"resulting_state":result,"resulting_assertion_id":candidate.resulting_assertion_id});session.flush();return candidate
