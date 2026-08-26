from __future__ import annotations

import json
from collections import Counter
from urllib.parse import urlparse

from sqlalchemy import select

from .db import Contact, Entity, RawImportRow, ResolutionDecision
from .entity_resolution import canonicalize_name
from .importers import CONTACT_HEADERS, COUNTRY_HEADERS, EMAIL_HEADERS, FIRM_HEADERS, URL_HEADERS

def _first(row,aliases):return next((str(row.get(key,"" )).strip() for key in aliases if row.get(key)),"")
def _domain(url):return urlparse(url or "").netloc.casefold().removeprefix("www.")

def audit_exact_decision(session,decision:ResolutionDecision)->tuple[bool,str]:
    raw=session.get(RawImportRow,decision.raw_row_id)
    if not raw:return False,"missing_raw_row"
    try:row=json.loads(raw.normalized_row_json)
    except json.JSONDecodeError:return False,"invalid_normalized_row"
    if decision.candidate_entity_id:
        candidate=session.get(Entity,decision.candidate_entity_id)
        if not candidate:return False,"missing_entity_candidate"
        name=_first(row,FIRM_HEADERS);country=_first(row,COUNTRY_HEADERS);incoming_domain=_domain(_first(row,URL_HEADERS))
        if canonicalize_name(name)!=candidate.canonical_name:return False,"name_mismatch"
        if not country or not candidate.country or country.casefold()!=candidate.country.casefold():return False,"jurisdiction_missing_or_mismatch"
        if not incoming_domain or incoming_domain!=_domain(candidate.official_url):return False,"official_domain_missing_or_mismatch"
        return True,"institutional_exact"
    if decision.candidate_contact_id:
        candidate=session.get(Contact,decision.candidate_contact_id)
        if not candidate:return False,"missing_contact_candidate"
        name=_first(row,CONTACT_HEADERS);email=_first(row,EMAIL_HEADERS).casefold()
        if canonicalize_name(name)!=canonicalize_name(candidate.name):return False,"person_name_mismatch"
        if not email or email!=str(candidate.email or "").casefold():return False,"person_email_missing_or_mismatch"
        if candidate.entity_id is None:return False,"employment_context_missing"
        employer=session.get(Entity,candidate.entity_id);incoming_employer=_first(row,FIRM_HEADERS)
        if not incoming_employer:return False,"employment_input_missing"
        if not employer or canonicalize_name(incoming_employer)!=employer.canonical_name:return False,"employment_context_mismatch"
        return True,"person_exact"
    return False,"no_candidate"

def shadow_audit(session)->dict:
    counts=Counter();total=0
    decisions=session.scalars(select(ResolutionDecision).where(ResolutionDecision.state=="EXACT_MATCH").order_by(ResolutionDecision.id)).all()
    for decision in decisions:
        passed,reason=audit_exact_decision(session,decision);total+=1
        counts[("pass" if passed else "review")+":"+reason]+=1
    passed=sum(value for key,value in counts.items() if key.startswith("pass:"))
    return {"total_prior_exact":total,"still_exact":passed,"requires_review":total-passed,"reasons":dict(sorted(counts.items()))}
