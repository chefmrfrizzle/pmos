from __future__ import annotations

import hashlib,re
from collections import Counter
from difflib import SequenceMatcher

from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import ResearchDocumentSnapshot,ResearchSourceCandidate,SourceChangeEvent
from .source_retrieval import persist_retrieved_candidate

def _text_hash(snapshot:dict)->str:
    text=" ".join(snapshot.get("text","").split())[:50000]
    if not text:raise ValueError("reverification snapshot has no normalized text")
    return hashlib.sha256(text.encode()).hexdigest()

def _tokens(text:str)->set[str]:return set(re.findall(r"[a-z0-9][a-z0-9_-]{2,}",text.casefold()))

def persist_reverification(session,candidate:ResearchSourceCandidate,snapshot:dict,actor:str="reverification-worker")->dict:
    prior=session.scalar(select(ResearchDocumentSnapshot).where(ResearchDocumentSnapshot.source_candidate_id==candidate.id).order_by(ResearchDocumentSnapshot.retrieved_at.desc(),ResearchDocumentSnapshot.id.desc()))
    if not prior:raise ValueError("source candidate has no prior snapshot")
    digest=_text_hash(snapshot);persist_counts=persist_retrieved_candidate(session,candidate,snapshot,actor)
    resulting=session.scalar(select(ResearchDocumentSnapshot).where(ResearchDocumentSnapshot.source_candidate_id==candidate.id,ResearchDocumentSnapshot.text_hash==digest))
    if not resulting:raise ValueError("reverification snapshot was not persisted")
    unchanged=prior.text_hash==resulting.text_hash
    if unchanged:similarity=1.0;added=removed=0;status="UNCHANGED"
    else:
        similarity=round(SequenceMatcher(None,prior.normalized_text,resulting.normalized_text,autojunk=False).ratio(),6)
        old_tokens=_tokens(prior.normalized_text);new_tokens=_tokens(resulting.normalized_text);added=len(new_tokens-old_tokens);removed=len(old_tokens-new_tokens);status="HUMAN_REVIEW_REQUIRED"
    event=SourceChangeEvent(source_candidate_id=candidate.id,prior_snapshot_id=prior.id,resulting_snapshot_id=resulting.id,prior_hash=prior.text_hash,resulting_hash=resulting.text_hash,similarity=similarity,added_token_count=added,removed_token_count=removed,status=status);session.add(event);session.flush()
    append_ledger_event(session,"SOURCE_CHANGE",event.id,actor,"SYSTEM","REVERIFICATION_COMPLETED",{"source_candidate_id":candidate.id,"entity_id":candidate.entity_id,"prior_snapshot_id":prior.id,"resulting_snapshot_id":resulting.id,"prior_hash":prior.text_hash,"resulting_hash":resulting.text_hash,"similarity":similarity,"added_token_count":added,"removed_token_count":removed,"status":status})
    return {"change_event_id":event.id,"status":status,"similarity":similarity,"passages_queued":persist_counts.get("passages_queued",0)}

def record_reverification_failure(session,candidate:ResearchSourceCandidate,outcome:str,actor:str="reverification-worker")->None:
    append_ledger_event(session,"SOURCE_CANDIDATE",candidate.id,actor,"SYSTEM","REVERIFICATION_NOT_COMPLETED",{"entity_id":candidate.entity_id,"status_preserved":candidate.status,"outcome":outcome})
