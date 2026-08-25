from pmos_research.entity_resolution import canonicalize_name, domain, resolve, MatchState
from pmos_research.scoring import strategic_score, explain_score

def test_canonicalize():
    assert canonicalize_name("Mubadala Investment Company PJSC") == "mubadala investment pjsc"

def test_domain():
    assert domain("https://www.adia.ae/about") == "adia.ae"

def test_score_bounds():
    w={"capital_access":.5,"network_leverage":.5}
    assert strategic_score({"capital_access":100,"network_leverage":100},w)==100

def test_score_is_explainable():
    result=explain_score({"capital_access":80,"network_leverage":40},{"capital_access":.75,"network_leverage":.25})
    assert result["score"]==70
    assert sum(x["contribution"] for x in result["factors"])==70

def test_resolution_does_not_merge_ambiguous_names():
    result=resolve({"name":"Northstar Capital"},{"name":"Northstar Collection"})
    assert result.state in {MatchState.POSSIBLE,MatchState.REVIEW}

def test_resolution_conflict():
    result=resolve({"name":"Jane Doe","email":"a@example.test"},{"name":"Jane Doe","email":"b@example.test"})
    assert result.state==MatchState.CONFLICT
