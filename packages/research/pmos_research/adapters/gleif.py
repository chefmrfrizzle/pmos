from __future__ import annotations

import hashlib
import json
from datetime import datetime,timezone
import httpx

BASE="https://api.gleif.org/api/v1/lei-records"

class GLEIFError(RuntimeError):pass

def _get_json(client,url,params,max_bytes=1000000):
    with client.stream("GET",url,params=params) as response:
        response.raise_for_status();body=bytearray()
        length=response.headers.get("content-length")
        if length and length.isdigit() and int(length)>max_bytes:raise GLEIFError("GLEIF response too large")
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body)>max_bytes or response.num_bytes_downloaded>max_bytes:raise GLEIFError("GLEIF response too large")
    try:return json.loads(body)
    except json.JSONDecodeError as exc:raise GLEIFError("GLEIF returned invalid JSON") from exc

def search_lei(name:str,country:str|None=None,limit:int=5)->list[dict]:
    limit=max(1,min(int(limit),10));params={"filter[entity.legalName]":name,"page[size]":limit}
    if country:params["filter[entity.legalAddress.country]"]=country.upper()
    timeout=httpx.Timeout(15,connect=8,read=15,write=8,pool=5)
    with httpx.Client(timeout=timeout,trust_env=False,headers={"Accept":"application/vnd.api+json","User-Agent":"PMOSResearch/0.3 (+public-evidence)"}) as client:data=_get_json(client,BASE,params)
    out=[]
    for item in data.get("data",[]):
        attrs=item.get("attributes") or {};entity=attrs.get("entity") or {};registration=attrs.get("registration") or {};legal_address=entity.get("legalAddress") or {};legal_form=entity.get("legalForm") or {};registered_at=entity.get("registeredAt") or {}
        lei=attrs.get("lei") or item.get("id");legal_name=(entity.get("legalName") or {}).get("name")
        if not lei or not legal_name:continue
        record={"lei":lei,"legal_name":legal_name,"entity_status":entity.get("status"),"jurisdiction":entity.get("jurisdiction"),"legal_address_country":legal_address.get("country"),"legal_form_id":legal_form.get("id"),"registration_authority_id":registered_at.get("id"),"registration_authority_entity_id":entity.get("registeredAs"),"lei_registration_status":registration.get("status"),"initial_registration_date":registration.get("initialRegistrationDate"),"last_update_date":registration.get("lastUpdateDate"),"next_renewal_date":registration.get("nextRenewalDate"),"record_url":f"{BASE}/{lei}","retrieved_at":datetime.now(timezone.utc).isoformat()}
        canonical=json.dumps({k:v for k,v in record.items() if k!="retrieved_at"},sort_keys=True,separators=(",",":"),ensure_ascii=False)
        record["content_hash"]=hashlib.sha256(canonical.encode()).hexdigest();out.append(record)
    return out
