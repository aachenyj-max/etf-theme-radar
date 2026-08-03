from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from .models import ThemeMetrics

def _settings() -> dict[str, dict[str, float]]:
    result:dict[str,dict[str,float]]={}; section=""
    for raw in (Path(__file__).parents[1]/"config"/"defaults.yaml").read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"): continue
        if not raw.startswith(" ") and raw.rstrip().endswith(":"):
            section=raw.strip()[:-1]; result[section]={}; continue
        if section and ":" in raw:
            key,value=raw.strip().split(":",1)
            try: result[section][key]=float(value.strip())
            except ValueError: continue
    return result

SETTINGS=_settings()
DEFAULT_WEIGHTS=SETTINGS["theme_scoring"]
PENALTY_WEIGHTS=SETTINGS["penalties"]
MINIMUM_EVIDENCE=SETTINGS["minimum_evidence"]
def clamp(value: float) -> float: return max(0.0, min(100.0, value))
def opportunity_score(metrics: ThemeMetrics, weights: dict[str,float]=DEFAULT_WEIGHTS) -> dict:
    components={key: clamp(metrics.signals.get(key,0)) * weight for key,weight in weights.items()}
    penalties=sum(clamp(metrics.signals.get(key,0))*PENALTY_WEIGHTS.get(key,0) for key in PENALTY_WEIGHTS)
    evidence_gate=(len(set(metrics.source_types)) >= int(MINIMUM_EVIDENCE["independent_source_types"]) and metrics.official_evidence_count >= int(MINIMUM_EVIDENCE["official_sources"]))
    score=clamp(sum(components.values())-penalties)
    confidence="high" if evidence_gate and metrics.listed_company_count>=int(MINIMUM_EVIDENCE["listed_companies"]) else "medium" if evidence_gate else "low"
    return {"theme_id":metrics.theme_id,"opportunity_score":round(score,2),"confidence":confidence,"components":components,"penalties":round(penalties,2),"evidence_gate_passed":evidence_gate,"missing_data":[] if evidence_gate else [f"need {int(MINIMUM_EVIDENCE['independent_source_types'])} independent source types including {int(MINIMUM_EVIDENCE['official_sources'])} official source"]}
def white_space_score(similarities: list[float]) -> float:
    """One minus highest comparable-product similarity; input range 0..1."""
    return round(100*(1-max(similarities, default=0)),2)
