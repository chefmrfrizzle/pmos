from __future__ import annotations

from datetime import datetime,timezone
from difflib import SequenceMatcher

from .audit_ledger import append_ledger_event
from .db import Entity,ResearchDocumentSnapshot,ResearchSourceCandidate,SourceChangeEvent,SourceChangeReviewEvent

class ChangeReviewError(ValueError):pass

def _preview(prior:str,resulting:str,limit:int=12)->list[dict]:
    before=prior.split();after=resulting.split();rows=[]
    for tag,i1,i2,j1,j2 in SequenceMatcher(None,before,after,autojunk=False).get_opcodes():
        if tag=="equal":continue
        rows.append({"operation":tag,"prior":" ".join(before[i1:i2])[:700],"resulting":" ".join(after[j1:j2])[:700]})
        if len(rows)>=limit:break
    return rows

def build_change_packet(session,event_id:int)->dict:
    event=session.get(SourceChangeEvent,event_id)
    if not event:raise ChangeReviewError("unknown source change event")
    candidate=session.get(ResearchSourceCandidate,event.source_candidate_id);entity=session.get(Entity,candidate.entity_id) if candidate else None
    prior=session.get(ResearchDocumentSnapshot,event.prior_snapshot_id);resulting=session.get(ResearchDocumentSnapshot,event.resulting_snapshot_id)
    if not candidate or not entity or not prior or not resulting:raise ChangeReviewError("source change chain is incomplete")
    return {"classification":"PRIVATE—AUTHORIZED CHANGE REVIEW ONLY","id":event.id,"status":event.status,"universe":entity.universe,"entity":{"id":entity.id,"name":entity.name,"entity_type":entity.entity_type,"country":entity.country},"source":{"candidate_id":candidate.id,"document_type":candidate.document_type,"source_url":candidate.source_url},"comparison":{"prior_snapshot_id":prior.id,"resulting_snapshot_id":resulting.id,"prior_hash":event.prior_hash,"resulting_hash":event.resulting_hash,"similarity":event.similarity,"added_token_count":event.added_token_count,"removed_token_count":event.removed_token_count,"changes":_preview(prior.normalized_text,resulting.normalized_text)},"detected_at":event.detected_at.isoformat()}

def adjudicate_change(session,event_id:int,action:str,reviewer:str,rationale:str,expected_status:str|None=None)->dict:
    event=session.get(SourceChangeEvent,event_id)
    if not event:raise ChangeReviewError("unknown source change event")
    if not reviewer.strip() or len(rationale.strip())<10:raise ChangeReviewError("reviewer and substantive rationale are required")
    if expected_status is not None and event.status!=expected_status:raise ChangeReviewError("change event changed; reload before deciding")
    action=action.upper();prior=event.status;transitions={"HUMAN_REVIEW_REQUIRED":{"ACKNOWLEDGE":"ACKNOWLEDGED","ESCALATE":"ESCALATED","DEFER":"DEFERRED"},"DEFERRED":{"ACKNOWLEDGE":"ACKNOWLEDGED","ESCALATE":"ESCALATED"}}
    if action not in transitions.get(prior,{}):raise ChangeReviewError(f"invalid transition {prior} -> {action}")
    result=transitions[prior][action];event.status=result
    session.add(SourceChangeReviewEvent(change_event_id=event.id,action=action,prior_state=prior,resulting_state=result,reviewer=reviewer,rationale=rationale.strip()))
    append_ledger_event(session,"SOURCE_CHANGE",event.id,reviewer,"REVIEWER",action,{"source_candidate_id":event.source_candidate_id,"prior_state":prior,"resulting_state":result,"prior_hash":event.prior_hash,"resulting_hash":event.resulting_hash,"rationale":rationale.strip()})
    session.flush();return {"change_event_id":event.id,"prior_state":prior,"resulting_state":result}
