from __future__ import annotations
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

MONEY = r"(?:US\$|USD|\$|€|EUR|£|GBP|A\$|AUD|C\$|CAD|CHF|S\$|SGD)?\s*([0-9]+(?:\.[0-9]+)?)\s*(trillion|tn|billion|bn|million|mn)"
AUM_RE = re.compile(rf"(?i)(?:assets under management|AUM|assets managed|manage(?:s|d)?(?: approximately| over| more than)?)[^.!?]{{0,100}}?{MONEY}")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s().-]*)?(?:\d[\s().-]*){7,14}")
KEY_LINK_TERMS = ("about","team","leadership","people","management","investment","portfolio","strategy","annual report","report","governance","contact","private wealth","family office","private sales","fiduciary")

def identity_supported(name:str,text:str)->bool:
    stop={"the","and","of","capital","group","company","management","investment","investments","partners"}
    tokens=[x for x in re.findall(r"[a-z0-9]+",(name or "").lower()) if len(x)>2 and x not in stop]
    haystack=set(re.findall(r"[a-z0-9]+",(text or "").lower()))
    required=1 if len(tokens)==1 else min(2,len(tokens))
    return bool(tokens) and sum(token in haystack for token in set(tokens))>=required

def discover_same_domain_links(base_url: str, html: str, limit: int = 12) -> list[str]:
    soup=BeautifulSoup(html,"html.parser")
    base_host=urlparse(base_url).netloc.lower().removeprefix("www.")
    scored=[]
    for a in soup.find_all("a",href=True):
        label=" ".join(a.stripped_strings).lower()
        href=urljoin(base_url,a["href"])
        p=urlparse(href)
        host=p.netloc.lower().removeprefix("www.")
        if p.scheme not in {"http","https"} or host!=base_host: continue
        score=sum(1 for t in KEY_LINK_TERMS if t in label or t.replace(" ","-") in p.path.lower())
        if score: scored.append((score,href.split("#")[0]))
    out=[]
    for _,u in sorted(scored,key=lambda x:(-x[0],x[1])):
        if u not in out: out.append(u)
        if len(out)>=limit: break
    return out

def extract_claims(text: str, source_url: str) -> list[dict]:
    claims=[]
    compact=" ".join((text or "").split())
    for m in AUM_RE.finditer(compact):
        raw=m.group(0)[:240]
        claims.append({"field":"aum_candidate","value":raw,"source_url":source_url,"confidence":0.72})
    emails=sorted(set(EMAIL_RE.findall(compact)))[:30]
    for e in emails:
        claims.append({"field":"public_email_candidate","value":e,"source_url":source_url,"confidence":0.65})
    # phones are deliberately lower confidence: pages often contain IDs/dates that resemble phones.
    for p in sorted(set(x.strip() for x in PHONE_RE.findall(compact)))[:20]:
        digits=re.sub(r"\D","",p)
        if 8<=len(digits)<=15:
            claims.append({"field":"public_phone_candidate","value":p,"source_url":source_url,"confidence":0.45})
    return claims
