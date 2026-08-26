from __future__ import annotations

import hashlib,secrets
from datetime import datetime,timezone
from urllib.parse import urlparse
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import EvidencePassage,PublisherIndependenceAssessment,PublisherIndependenceEvidence,PublisherIndependenceEvent,SourceDocument

class PublisherIndependenceError(ValueError):pass

def normalized_source_domain(value:str)->str:
    candidate=value.strip().casefold().rstrip(".")
    if "://" in candidate:candidate=(urlparse(candidate).hostname or "").casefold().rstrip(".")
    candidate=candidate.removeprefix("www.")
    if not candidate or len(candidate)>300 or "/" in candidate or "@" in candidate or "." not in candidate:raise PublisherIndependenceError("a valid source domain is required")
    return candidate

def _rows(session,assessment_id:int):
    return session.execute(select(PublisherIndependenceEvidence,EvidencePassage,SourceDocument).join(EvidencePassage,PublisherIndependenceEvidence.evidence_passage_id==EvidencePassage.id).join(SourceDocument,EvidencePassage.document_id==SourceDocument.id).where(PublisherIndependenceEvidence.assessment_id==assessment_id).order_by(SourceDocument.id,EvidencePassage.id)).all()

def _package_hash(rows)->str:
    material="|".join(f"{document.id}:{document.content_hash}:{passage.id}:{passage.passage_hash}" for _,passage,document in rows)
    return hashlib.sha256(material.encode()).hexdigest()

def propose_publisher_independence(session,source_domain:str,independence_group:str,proposer:str,rationale:str,evidence_passage_ids:list[int]):
    domain=normalized_source_domain(source_domain);group=independence_group.strip().casefold()
    if not group or len(group)>300:raise PublisherIndependenceError("a bounded independence group is required")
    if not proposer.strip() or len(rationale.strip())<10:raise PublisherIndependenceError("proposer and substantive rationale are required")
    existing=session.scalars(select(PublisherIndependenceAssessment).where(PublisherIndependenceAssessment.source_domain==domain,PublisherIndependenceAssessment.independence_group==group).order_by(PublisherIndependenceAssessment.version)).all()
    if any(x.status in {"HUMAN_REVIEW_REQUIRED","DEFERRED","APPROVED"} for x in existing):raise PublisherIndependenceError("an active publisher independence assessment already exists")
    version=max((x.version for x in existing),default=0)+1
    ids=sorted(set(int(x) for x in evidence_passage_ids));passages=session.scalars(select(EvidencePassage).where(EvidencePassage.id.in_(ids))).all() if ids else []
    if not passages or len(passages)!=len(ids):raise PublisherIndependenceError("exact publisher-control evidence is required")
    documents={x.id:x for x in session.scalars(select(SourceDocument).where(SourceDocument.id.in_({x.document_id for x in passages}))).all()}
    if len(documents)!=len({x.document_id for x in passages}) or any(hashlib.sha256(x.passage.encode()).hexdigest()!=x.passage_hash for x in passages):raise PublisherIndependenceError("publisher evidence chain failed integrity validation")
    observed=next((document.id for document in session.scalars(select(SourceDocument).order_by(SourceDocument.id)) if normalized_source_domain(document.source_url)==domain),None)
    if not observed:raise PublisherIndependenceError("source domain has not been observed in the evidence store")
    assessment=PublisherIndependenceAssessment(source_domain=domain,independence_group=group,version=version,status="HUMAN_REVIEW_REQUIRED",proposed_by=proposer.strip(),proposal_rationale=rationale.strip(),evidence_package_hash="");session.add(assessment);session.flush()
    for passage in passages:session.add(PublisherIndependenceEvidence(assessment_id=assessment.id,evidence_passage_id=passage.id))
    session.flush();assessment.evidence_package_hash=_package_hash(_rows(session,assessment.id));session.add(PublisherIndependenceEvent(assessment_id=assessment.id,action="PROPOSE",prior_state=None,resulting_state=assessment.status,actor=proposer.strip(),rationale=rationale.strip(),evidence_package_hash=assessment.evidence_package_hash));append_ledger_event(session,"PUBLISHER_INDEPENDENCE",assessment.id,proposer.strip(),"RESEARCHER","PROPOSED",{"source_domain":domain,"independence_group":group,"evidence_package_hash":assessment.evidence_package_hash});session.flush();return assessment

def adjudicate_publisher_independence(session,assessment_id:int,action:str,reviewer:str,rationale:str,expected_status:str):
    assessment=session.get(PublisherIndependenceAssessment,assessment_id)
    if not assessment or assessment.status!=expected_status:raise PublisherIndependenceError("publisher assessment changed; reload before deciding")
    if reviewer.strip()==assessment.proposed_by:raise PublisherIndependenceError("independent reviewer required")
    if len(rationale.strip())<10:raise PublisherIndependenceError("substantive review rationale is required")
    action=action.upper();transitions={"HUMAN_REVIEW_REQUIRED":{"APPROVE":"APPROVED","REJECT":"REJECTED","DEFER":"DEFERRED"},"DEFERRED":{"APPROVE":"APPROVED","REJECT":"REJECTED"}}
    if action not in transitions.get(assessment.status,{}):raise PublisherIndependenceError("unsupported publisher assessment transition")
    package=_package_hash(_rows(session,assessment.id))
    if not secrets.compare_digest(package,assessment.evidence_package_hash):raise PublisherIndependenceError("publisher evidence package changed after proposal")
    if action=="APPROVE":
        conflicting=session.scalar(select(PublisherIndependenceAssessment).where(PublisherIndependenceAssessment.source_domain==assessment.source_domain,PublisherIndependenceAssessment.status=="APPROVED",PublisherIndependenceAssessment.id!=assessment.id))
        if conflicting:raise PublisherIndependenceError("source domain already has a different approved independence assessment")
    prior=assessment.status;assessment.status=transitions[prior][action]
    if action=="APPROVE":assessment.reviewed_by=reviewer.strip();assessment.review_rationale=rationale.strip();assessment.reviewed_at=datetime.now(timezone.utc)
    session.add(PublisherIndependenceEvent(assessment_id=assessment.id,action=action,prior_state=prior,resulting_state=assessment.status,actor=reviewer.strip(),rationale=rationale.strip(),evidence_package_hash=package));append_ledger_event(session,"PUBLISHER_INDEPENDENCE",assessment.id,reviewer.strip(),"REVIEWER",action,{"prior_state":prior,"resulting_state":assessment.status,"evidence_package_hash":package});session.flush();return assessment

def approved_independence_group(session,document:SourceDocument)->str|None:
    domain=normalized_source_domain(document.source_url)
    assessment=session.scalar(select(PublisherIndependenceAssessment).where(PublisherIndependenceAssessment.source_domain==domain,PublisherIndependenceAssessment.independence_group==document.publisher_independence_group.casefold(),PublisherIndependenceAssessment.status=="APPROVED"))
    return assessment.independence_group if assessment else None

def build_publisher_independence_packet(session,assessment_id:int)->dict:
    assessment=session.get(PublisherIndependenceAssessment,assessment_id)
    if not assessment:raise PublisherIndependenceError("unknown publisher independence assessment")
    rows=_rows(session,assessment.id);events=session.scalars(select(PublisherIndependenceEvent).where(PublisherIndependenceEvent.assessment_id==assessment.id).order_by(PublisherIndependenceEvent.id)).all()
    return {"classification":"PRIVATE—AUTHORIZED SOURCE GOVERNANCE","id":assessment.id,"source_domain":assessment.source_domain,"independence_group":assessment.independence_group,"version":assessment.version,"status":assessment.status,"proposed_by":assessment.proposed_by,"proposal_rationale":assessment.proposal_rationale,"reviewed_by":assessment.reviewed_by,"review_rationale":assessment.review_rationale,"evidence_package_hash":assessment.evidence_package_hash,"evidence":[{"passage_id":passage.id,"document_id":document.id,"source_url":document.source_url,"source_rank":document.source_rank,"document_hash":document.content_hash,"passage_hash":passage.passage_hash,"passage":passage.passage} for _,passage,document in rows],"history":[{"action":x.action,"prior_state":x.prior_state,"resulting_state":x.resulting_state,"actor":x.actor,"rationale":x.rationale,"evidence_package_hash":x.evidence_package_hash,"occurred_at":x.occurred_at.isoformat()} for x in events]}
