from __future__ import annotations

import hashlib,json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import Claim,ClaimEvidence,CheckResult,DiligenceCase,Entity,UniverseCoverageRun

REQUIRED_UNIVERSES={"sovereign_wealth","pensions","private_banks","multifamily_offices","family_office_networks","fiduciary","endowments_foundations","auction_private_sales","art_fairs","mega_galleries","insurance","reinsurance","brokers","asset_servicing","venture_capital","private_equity","hedge_funds","corporate_venture_capital"}
REQUIRED_REGIONS={"NORTH_AMERICA","LATIN_AMERICA","UK_IRELAND","CONTINENTAL_EUROPE","SWITZERLAND_LIECHTENSTEIN_MONACO","NORDICS","GCC_MIDDLE_EAST","AFRICA","INDIA","GREATER_CHINA","JAPAN","SOUTH_KOREA","SOUTHEAST_ASIA","AUSTRALIA_NEW_ZEALAND"}
REGION_COUNTRIES={
    "NORTH_AMERICA":{"US","CA"},"LATIN_AMERICA":{"MX","BR","AR","CL","CO","PE","UY","PA","CR"},"UK_IRELAND":{"GB","IE"},
    "SWITZERLAND_LIECHTENSTEIN_MONACO":{"CH","LI","MC"},"NORDICS":{"NO","SE","DK","FI","IS"},
    "GCC_MIDDLE_EAST":{"AE","SA","QA","KW","BH","OM","IL","JO","LB"},"AFRICA":{"ZA","NG","KE","EG","MA","GH","RW","MU"},"INDIA":{"IN"},
    "GREATER_CHINA":{"CN","HK","MO","TW"},"JAPAN":{"JP"},"SOUTH_KOREA":{"KR"},"SOUTHEAST_ASIA":{"SG","MY","ID","TH","VN","PH","BN","KH"},"AUSTRALIA_NEW_ZEALAND":{"AU","NZ"},
    "CARIBBEAN":{"BM","KY","VG","BS","BB","TT","JM"},
    "CONTINENTAL_EUROPE":{"FR","DE","NL","BE","LU","AT","IT","ES","PT","GR","PL","CZ","HU","RO","BG","HR","SI","SK","EE","LV","LT","CY","MT","JE","GG"},
}
QUALIFYING={"SUPPORTED","CORROBORATED","SPECIALIST_VERIFIED"}

def region_for(country:str|None)->str:
    code=(country or "").upper()
    return next((region for region,countries in REGION_COUNTRIES.items() if code in countries),"UNMAPPED")

def build_universe_coverage(session)->dict:
    entities=session.scalars(select(Entity).where(Entity.universe!="imported_private").order_by(Entity.universe,Entity.id)).all();by_universe=defaultdict(list);by_region=Counter()
    qualifying=set(session.scalars(select(Claim.entity_id).join(ClaimEvidence,ClaimEvidence.claim_id==Claim.id).where(Claim.field.in_({"official_identity","legal_identity"}),Claim.verification_status.in_(QUALIFYING))).all())
    cases=defaultdict(list)
    for case in session.scalars(select(DiligenceCase)):cases[case.entity_id].append(case)
    ready=set()
    for entity_id,entity_cases in cases.items():
        for case in entity_cases:
            checks=session.scalars(select(CheckResult).where(CheckResult.case_id==case.id,CheckResult.mandatory.is_(True))).all()
            if checks and all(x.status in {"CORROBORATED","SPECIALIST_VERIFIED","EXCEPTED"} for x in checks):ready.add(entity_id);break
    for entity in entities:by_universe[entity.universe].append(entity);by_region[region_for(entity.country)]+=1
    universes=[]
    for universe in sorted(set(by_universe)|REQUIRED_UNIVERSES):
        rows=by_universe.get(universe,[]);n=len(rows);jur=sum(bool(x.country) for x in rows);urls=sum(bool(x.official_url) for x in rows);identity=sum(x.id in qualifying for x in rows);case_count=sum(x.id in cases for x in rows);ready_count=sum(x.id in ready for x in rows)
        universes.append({"universe":universe,"required":universe in REQUIRED_UNIVERSES,"registered":n,"jurisdiction_complete":jur,"official_url_complete":urls,"identity_evidence_backed":identity,"diligence_case_open":case_count,"decision_ready":ready_count,"rates":{"jurisdiction":round(jur/n,3) if n else 0,"official_url":round(urls/n,3) if n else 0,"identity_evidence":round(identity/n,3) if n else 0,"diligence_case":round(case_count/n,3) if n else 0,"decision_ready":round(ready_count/n,3) if n else 0}})
    region_rows=[{"region":region,"required":region in REQUIRED_REGIONS,"registered":by_region.get(region,0)} for region in sorted(REQUIRED_REGIONS|set(by_region))]
    missing_universes=sorted(x for x in REQUIRED_UNIVERSES if not by_universe.get(x));missing_regions=sorted(x for x in REQUIRED_REGIONS if not by_region.get(x));unmapped=by_region.get("UNMAPPED",0)
    totals={"registered":len(entities),"jurisdiction_complete":sum(bool(x.country) for x in entities),"official_url_complete":sum(bool(x.official_url) for x in entities),"identity_evidence_backed":sum(x.id in qualifying for x in entities),"diligence_case_open":sum(x.id in cases for x in entities),"decision_ready":sum(x.id in ready for x in entities)}
    status="COMPLETE" if not missing_universes and not missing_regions and unmapped==0 and totals["identity_evidence_backed"]==totals["registered"] and totals["decision_ready"]==totals["registered"] else "INCOMPLETE"
    return {"classification":"PMOS PRIVATE AGGREGATE COVERAGE — NO ENTITY NAMES","generated_at":datetime.now(timezone.utc).isoformat(),"status":status,"definitions":{"registered":"Real public-registry identity row; not a verified counterparty.","identity_evidence_backed":"Qualifying identity claim with exact evidence.","decision_ready":"At least one diligence case whose mandatory checks are completed or explicitly excepted."},"totals":totals,"missing_required_universes":missing_universes,"missing_required_regions":missing_regions,"unmapped_country_count":unmapped,"universes":universes,"regions":region_rows}

def persist_coverage(session,report:dict,actor:str="coverage-worker")->UniverseCoverageRun:
    canonical=json.dumps(report,sort_keys=True,separators=(",",":"));digest=hashlib.sha256(canonical.encode()).hexdigest();existing=session.scalar(select(UniverseCoverageRun).where(UniverseCoverageRun.report_hash==digest))
    if existing:return existing
    run=UniverseCoverageRun(status=report["status"],report_hash=digest,report_json=canonical,actor=actor);session.add(run);session.flush();append_ledger_event(session,"UNIVERSE_COVERAGE",run.id,actor,"SYSTEM","COVERAGE_RECORDED",{"status":run.status,"report_hash":digest,"totals":report["totals"],"missing_required_universe_count":len(report["missing_required_universes"]),"missing_required_region_count":len(report["missing_required_regions"])});return run
