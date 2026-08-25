from pathlib import Path
import yaml
from typing import Optional

def load_weights(path="config/scoring.yaml"):
    return yaml.safe_load(Path(path).read_text())["weights"]

def explain_score(values: dict[str,float], weights: Optional[dict]=None) -> dict:
    weights=weights or load_weights(); factors=[]
    for key,weight in weights.items():
        value=max(0.0,min(100.0,float(values.get(key,0))))
        factors.append({"factor":key,"value":value,"weight":float(weight),"contribution":round(value*float(weight),2)})
    score=round(max(0,min(100,sum(x["contribution"] for x in factors))),2)
    return {"score":score,"factors":sorted(factors,key=lambda x:x["contribution"],reverse=True)}

def strategic_score(values,weights=None): return explain_score(values,weights)["score"]
