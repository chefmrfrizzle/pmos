from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"packages/research"))
from fastapi import FastAPI, Query
from pmos_research.db import init_db, SessionLocal, Entity

app=FastAPI(title="PMOS API",version="0.1.0")

@app.on_event("startup")
def startup(): init_db()

@app.get("/health")
def health(): return {"ok":True,"service":"pmos-api"}

@app.get("/entities")
def entities(universe: str|None=None, q: str|None=None, limit:int=Query(100,ge=1,le=500)):
    with SessionLocal() as s:
        query=s.query(Entity)
        if universe: query=query.filter(Entity.universe==universe)
        if q: query=query.filter(Entity.name.ilike(f"%{q}%"))
        rows=query.order_by(Entity.strategic_priority.desc(),Entity.name).limit(limit).all()
        return [{"id":e.id,"name":e.name,"universe":e.universe,"country":e.country,"city":e.city,"official_url":e.official_url,"verification_status":e.verification_status,"evidence_confidence":e.evidence_confidence,"strategic_priority":e.strategic_priority,"useful_wedge":e.useful_wedge} for e in rows]

@app.get("/entities/{entity_id}")
def entity(entity_id:int):
    with SessionLocal() as s:
        e=s.get(Entity,entity_id)
        if not e: return {"error":"not_found"}
        return {c.name:getattr(e,c.name) for c in e.__table__.columns}

@app.get("/entities/{entity_id}/claims")
def claims(entity_id:int):
    from pmos_research.db import Claim
    with SessionLocal() as s:
        rows=s.query(Claim).filter(Claim.entity_id==entity_id).order_by(Claim.confidence.desc()).limit(500).all()
        return [{"field":x.field,"value":x.value,"source_url":x.source_url,"confidence":x.confidence,"verification_status":x.verification_status,"observed_at":x.observed_at} for x in rows]
