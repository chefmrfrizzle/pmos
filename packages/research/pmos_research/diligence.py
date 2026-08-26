from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from .audit_ledger import append_ledger_event

from .db import (
    CaseAuditEvent,
    CheckResult,
    ConflictCase,
    DiligenceCase,
    ReviewSignoff,
)

SOURCE_RANKS = {"S0", "S1", "S2", "S3", "S4", "S5"}
TIERS = {"T0", "T1", "T2", "T3", "T4", "T5"}
MATERIAL_FACTS = {
    "legal_identity", "legal_status", "regulatory_status", "ownership_control",
    "authority_to_transact", "sanctions", "fund_manager", "fund_domicile",
}
FRESHNESS_DAYS = {
    "sanctions": 1,
    "authority_to_transact": 30,
    "role": 30,
    "legal_status": 90,
    "regulatory_status": 90,
    "ownership_control": 90,
    "fund_manager": 90,
    "fund_domicile": 90,
    "mandate": 180,
    "identity": 365,
    "address": 365,
}

CASE_TEMPLATES = {
    "venture capital": ("legal_identity", "regulatory_status", "fund_manager", "mandate", "authority_to_transact"),
    "private equity": ("legal_identity", "regulatory_status", "fund_manager", "fund_domicile", "mandate", "authority_to_transact"),
    "hedge fund": ("legal_identity", "regulatory_status", "fund_manager", "fund_domicile", "authority_to_transact"),
    "corporate venture capital": ("legal_identity", "ownership_control", "mandate", "authority_to_transact"),
    "sovereign wealth": ("legal_identity", "legal_status", "governance", "mandate", "authority_to_transact"),
    "pension": ("legal_identity", "legal_status", "governance", "mandate", "authority_to_transact"),
    "fund of funds": ("legal_identity", "regulatory_status", "fund_manager", "fund_domicile", "mandate", "authority_to_transact"),
    "default": ("legal_identity", "legal_status", "regulatory_status", "ownership_control", "authority_to_transact"),
}


def open_case(session, entity_id: int, counterparty_type: str, purpose: str, permitted_use: str, owner: str, jurisdictions=()):
    case = DiligenceCase(
        entity_id=entity_id,
        purpose=purpose,
        permitted_use=permitted_use,
        jurisdiction_scope_json=json.dumps(sorted(set(jurisdictions))),
        owner=owner,
        status="SCOPE_FIT",
    )
    session.add(case)
    session.flush()
    checks = CASE_TEMPLATES.get(counterparty_type.casefold(), CASE_TEMPLATES["default"])
    now = datetime.now(timezone.utc)
    for code in checks:
        session.add(CheckResult(
            case_id=case.id,
            check_code=code,
            fact_class=code,
            mandatory=True,
            evidence_due_at=now + timedelta(days=FRESHNESS_DAYS.get(code, 180)),
        ))
    append_audit_event(session, case.id, owner, "CASE_OPENED", {}, {"status": case.status})
    return case


def append_audit_event(session, case_id: int, actor: str, action: str, prior: dict, resulting: dict, rationale: str | None = None):
    if not actor.strip():
        raise ValueError("authenticated actor is required")
    event = CaseAuditEvent(
        case_id=case_id,
        actor=actor.strip(),
        action=action,
        prior_state_json=json.dumps(prior, sort_keys=True),
        resulting_state_json=json.dumps(resulting, sort_keys=True),
        rationale=rationale,
    )
    session.add(event)
    append_ledger_event(session,"DILIGENCE_CASE",case_id,actor.strip(),"CASE_ACTOR",action,{"prior":prior,"resulting":resulting,"rationale":rationale})
    return event


def readiness(session, case_id: int) -> dict:
    checks = session.scalars(select(CheckResult).where(CheckResult.case_id == case_id)).all()
    conflicts = session.scalars(select(ConflictCase).where(
        ConflictCase.entity_id == session.get(DiligenceCase, case_id).entity_id,
        ConflictCase.status != "RESOLVED",
    )).all()
    missing = [x.check_code for x in checks if x.mandatory and x.status not in {"CORROBORATED", "SPECIALIST_VERIFIED", "EXCEPTED"}]
    material = [x.predicate for x in conflicts if x.materiality == "MATERIAL"]
    if material or any(x in missing for x in {"legal_identity", "authority_to_transact"}):
        state = "RED"
    elif missing:
        state = "AMBER"
    else:
        state = "GREEN"
    return {"state": state, "missing_checks": sorted(missing), "material_conflicts": sorted(material)}


def specialist_signoff(session, case_id: int, reviewer: str, role: str, decision: str, rationale: str, scope=()):
    case = session.get(DiligenceCase, case_id)
    if not case:
        raise ValueError("unknown case")
    if reviewer == case.owner and case.risk_tier == "HIGH":
        raise ValueError("high-risk cases require independent maker-checker review")
    if not rationale.strip():
        raise ValueError("sign-off rationale is required")
    record = ReviewSignoff(case_id=case_id, reviewer=reviewer, role=role, decision=decision, rationale=rationale, scope_json=json.dumps(list(scope)))
    session.add(record)
    append_audit_event(session, case_id, reviewer, "SPECIALIST_SIGNOFF", {"decision": case.decision}, {"decision": decision}, rationale)
    case.reviewer = reviewer
    case.decision = decision
    case.updated_at = datetime.now(timezone.utc)
    return record


def passage_hash(passage: str) -> str:
    return hashlib.sha256(passage.strip().encode("utf-8")).hexdigest()
