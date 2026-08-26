#!/usr/bin/env python3
from pathlib import Path
import argparse, sys
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/research"))
from pmos_research.db import init_db, SessionLocal, Entity, Evidence, Claim
from pmos_research.adapters.official_web import OfficialWebAdapter
from pmos_research.adapters.gleif import search_lei
from pmos_research.fact_extraction import discover_same_domain_links, extract_claims, identity_supported

ap=argparse.ArgumentParser()
ap.add_argument("--universe")
ap.add_argument("--max-pages",type=int,default=6,help="Max official pages fetched per entity")
ap.add_argument("--limit",type=int,default=0,help="Optional entity limit for test runs")
args=ap.parse_args()
init_db(); web=OfficialWebAdapter()
with SessionLocal() as s:
    q=s.query(Entity)
    if args.universe: q=q.filter(Entity.universe==args.universe)
    entities=q.all()
    if args.limit: entities=entities[:args.limit]
    for i,e in enumerate(entities,1):
        print(f"[{i}/{len(entities)}] {e.name}")
        confidence=0.0; identity_corroborated=False; queue=[e.official_url] if e.official_url else []; seen=set(); fetched=0
        while queue and fetched<args.max_pages:
            url=queue.pop(0)
            if not url or url in seen: continue
            seen.add(url)
            try:
                snap=web.fetch(url)
                if snap.get("status")!="ok": continue
                fetched+=1
                actual=snap["url"]
                duplicate=s.query(Evidence).filter_by(entity_id=e.id,source_url=actual,content_hash=snap["hash"]).first()
                if not duplicate:
                    s.add(Evidence(entity_id=e.id,source_url=actual,source_type="official",content_hash=snap["hash"],title=snap["title"],text_excerpt=snap["text"][:5000],confidence=1.0))
                for claim in extract_claims(snap["text"],actual):
                    exists=s.query(Claim).filter_by(entity_id=e.id,field=claim["field"],value=claim["value"],source_url=actual).first()
                    if not exists: s.add(Claim(entity_id=e.id,**claim))
                if identity_supported(e.name,snap["title"]+" "+snap["text"][:10000]):
                    identity_corroborated=True
                    exists=s.query(Claim).filter_by(entity_id=e.id,field="official_identity",value=e.name,source_url=actual).first()
                    if not exists:s.add(Claim(entity_id=e.id,field="official_identity",value=e.name,source_url=actual,source_type="official",confidence=.9,verification_status="SUPPORTED",extractor="deterministic_identity_v1",evidence_hash=snap["hash"]))
                if fetched==1:
                    queue.extend(discover_same_domain_links(actual,snap.get("html","") ,limit=max(args.max_pages*2,10)))
                confidence=max(confidence,.9 if identity_corroborated else .35)
                print("  fetched",actual)
            except Exception as ex:
                print("  official fetch failed:",url,ex)
        try:
            leis=search_lei(e.name,e.country)
            if leis:
                confidence=max(confidence,0.75)
                candidate=leis[0]
                s.add(Claim(entity_id=e.id,field="lei_candidate",value=str(candidate),source_url="https://api.gleif.org/",confidence=0.95))
                print("  LEI candidate:",candidate)
        except Exception as ex:
            print("  LEI lookup failed:",ex)
        e.evidence_confidence=confidence*100
        e.last_verified=datetime.now(timezone.utc)
        e.verification_status="SUPPORTED" if identity_corroborated else "EVIDENCE_COLLECTED" if fetched else "NEEDS_VERIFICATION"
        s.commit()
