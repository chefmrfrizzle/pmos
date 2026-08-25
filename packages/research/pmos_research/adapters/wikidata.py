import httpx

ENDPOINT = "https://query.wikidata.org/sparql"

def search_entity(name: str, limit: int = 5) -> list[dict]:
    safe = name.replace('"', '\\"')
    query = f'''SELECT ?item ?itemLabel ?countryLabel WHERE {{
      ?item rdfs:label "{safe}"@en .
      OPTIONAL {{ ?item wdt:P17 ?country. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT {int(limit)}'''
    headers={"User-Agent":"PMOSResearch/0.1","Accept":"application/sparql-results+json"}
    try:
        r=httpx.get(ENDPOINT, params={"query":query,"format":"json"}, headers=headers, timeout=20)
        r.raise_for_status()
        return [{k:v.get("value") for k,v in row.items()} for row in r.json()["results"]["bindings"]]
    except Exception:
        return []
