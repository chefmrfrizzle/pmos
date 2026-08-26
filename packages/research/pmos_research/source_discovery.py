from __future__ import annotations

import json
import re
from collections import Counter
from urllib.parse import parse_qsl,urljoin,urlparse,urlunparse,urlencode

from bs4 import BeautifulSoup
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .db import Entity,ResearchSourceCandidate

TRACKING_PREFIXES=("utm_","mc_")
RULES=(
    ("REGULATORY_DISCLOSURE",("regulatory","regulation","disclosure","registration","licence","license"),("regulatory_status","legal_identity"),95),
    ("ANNUAL_REPORT",("annual report","annual-report","financial report","investor report"),("legal_status","governance","mandate","fund_manager"),90),
    ("GOVERNANCE",("governance","board","trustees","leadership","management team"),("governance",),80),
    ("FUND_STRUCTURE",("fund structure","funds","vehicles","investment vehicles","general partner","manager"),("fund_manager","fund_domicile"),75),
    ("INVESTMENT_STRATEGY",("strategy","investment approach","investment strategy","portfolio","asset classes","private markets"),("mandate",),70),
    ("PRIVATE_CLIENT",("private wealth","family office","private sales","fiduciary","trust and estate"),("mandate",),65),
    ("LEGAL_IDENTITY",("legal","terms","imprint","corporate information"),("legal_identity",),60),
    ("CONTACT_LOCATION",("contact","locations","offices"),("address",),40),
)

def canonical_public_url(base_url:str,href:str)->str|None:
    value=urljoin(base_url,href).split("#",1)[0];parsed=urlparse(value);base=urlparse(base_url)
    if parsed.scheme not in {"http","https"} or not parsed.hostname or not base.hostname or parsed.username or parsed.password:return None
    if parsed.hostname.casefold().removeprefix("www.")!=base.hostname.casefold().removeprefix("www."):return None
    if parsed.port not in {None,80 if parsed.scheme=="http" else 443}:return None
    query=[(k,v) for k,v in parse_qsl(parsed.query,keep_blank_values=True) if not k.casefold().startswith(TRACKING_PREFIXES)]
    path=re.sub(r"/{2,}","/",parsed.path or "/")
    return urlunparse((parsed.scheme,parsed.netloc.casefold(),path,"",urlencode(query),""))

def classify_link(label:str,url:str)->dict|None:
    haystack=" ".join(label.casefold().split())+" "+urlparse(url).path.casefold().replace("_"," ")
    matches=[]
    for document_type,terms,predicates,base_score in RULES:
        hits=sum(term in haystack for term in terms)
        if hits:matches.append((base_score+min(hits,3)*5,document_type,predicates))
    if not matches:return None
    score,document_type,predicates=max(matches,key=lambda x:(x[0],x[1]))
    if urlparse(url).path.casefold().endswith(".pdf"):score+=5
    return {"document_type":document_type,"target_predicates":list(predicates),"score":min(score,100)}

def discover_source_links(base_url:str,html:str,limit:int=20)->list[dict]:
    soup=BeautifulSoup(html or "","html.parser");found={}
    for anchor in soup.find_all("a",href=True):
        url=canonical_public_url(base_url,anchor.get("href",""))
        if not url or url==canonical_public_url(base_url,base_url):continue
        label=" ".join(anchor.stripped_strings)[:500];classification=classify_link(label,url)
        if not classification:continue
        candidate={"source_url":url,"link_label":label or None,**classification}
        prior=found.get(url)
        if prior is None or candidate["score"]>prior["score"]:found[url]=candidate
    return sorted(found.values(),key=lambda x:(-x["score"],x["source_url"]))[:max(1,min(limit,50))]

def persist_source_candidates(session,entity:Entity,base_url:str,html:str,actor:str="research-worker",limit:int=20)->Counter:
    counts=Counter();candidates=discover_source_links(base_url,html,limit);existing={x.source_url:x for x in session.scalars(select(ResearchSourceCandidate).where(ResearchSourceCandidate.entity_id==entity.id)).all()}
    for item in candidates:
        if item["source_url"] in existing:counts["existing"]+=1;continue
        host=urlparse(item["source_url"]).hostname.casefold().removeprefix("www.")
        session.add(ResearchSourceCandidate(entity_id=entity.id,source_url=item["source_url"],source_domain=host,document_type=item["document_type"],target_predicates_json=json.dumps(item["target_predicates"]),link_label=item["link_label"],discovered_from_url=base_url,discovery_score=item["score"]))
        counts[item["document_type"]]+=1;counts["queued"]+=1
    append_ledger_event(session,"SOURCE_DISCOVERY",entity.id,actor,"SYSTEM","CANDIDATES_DISCOVERED",{"base_url":base_url,"found":len(candidates),"queued":counts["queued"],"existing":counts["existing"],"document_types":{k:v for k,v in sorted(counts.items()) if k not in {"queued","existing"}}})
    session.flush();return counts
