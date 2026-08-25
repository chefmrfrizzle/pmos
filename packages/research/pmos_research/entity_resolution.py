import re, unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from urllib.parse import urlparse
from typing import Optional

class MatchState(str, Enum):
    EXACT="EXACT_MATCH"; PROBABLE="PROBABLE_MATCH"; POSSIBLE="POSSIBLE_MATCH"; CONFLICT="CONFLICT"; REVIEW="REQUIRES_REVIEW"
@dataclass(frozen=True)
class Resolution:
    state: MatchState; confidence: float; reasons: tuple[str,...]
def canonicalize_name(name: str) -> str:
    x=unicodedata.normalize("NFKD",name or "").encode("ascii","ignore").decode().lower().replace("&"," and ")
    x=re.sub(r"\b(inc|llc|ltd|limited|plc|corp|corporation|company|co|ag|sa|se|group|holdings?)\b"," ",x)
    return re.sub(r"[^a-z0-9]+"," ",x).strip()
def domain(url: Optional[str]) -> str: return urlparse(url or "").netloc.lower().split(":")[0].removeprefix("www.")
def resolve(a: dict,b: dict) -> Resolution:
    an,bn=canonicalize_name(a.get("name","")),canonicalize_name(b.get("name",""))
    if not an or not bn:return Resolution(MatchState.REVIEW,0,("missing normalized name",))
    if a.get("email") and b.get("email") and a["email"].lower()!=b["email"].lower():return Resolution(MatchState.CONFLICT,.2,("conflicting email",))
    if an==bn and a.get("email") and str(a["email"]).lower()==str(b.get("email")).lower():return Resolution(MatchState.EXACT,.99,("same normalized name","same email"))
    sim=SequenceMatcher(None,an,bn).ratio(); same=bool(domain(a.get("url")) and domain(a.get("url"))==domain(b.get("url")))
    if an==bn or (sim>=.92 and same):return Resolution(MatchState.PROBABLE,round(max(.86,sim),2),("strong name match",)+(('same domain',) if same else ()))
    if sim>=.78:return Resolution(MatchState.POSSIBLE,round(sim,2),("similar name",))
    return Resolution(MatchState.REVIEW,round(sim,2),("insufficient deterministic evidence",))
