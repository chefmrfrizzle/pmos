import httpx

BASE = "https://api.gleif.org/api/v1/lei-records"

def search_lei(name: str, country: str | None = None, limit: int = 5) -> list[dict]:
    params = {"filter[entity.legalName]": name, "page[size]": limit}
    if country:
        params["filter[entity.legalAddress.country]"] = country
    with httpx.Client(timeout=20) as c:
        r = c.get(BASE, params=params)
        if r.status_code >= 400:
            return []
        out=[]
        for item in r.json().get("data", []):
            attrs=item.get("attributes", {})
            entity=attrs.get("entity", {})
            out.append({
                "lei": attrs.get("lei"),
                "legal_name": ((entity.get("legalName") or {}).get("name")),
                "status": (entity.get("status")),
                "jurisdiction": entity.get("jurisdiction"),
            })
        return out
