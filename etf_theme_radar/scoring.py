from __future__ import annotations
from datetime import datetime, timezone
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


def _independent_config() -> tuple[dict[str, str | float], dict[str, dict[str, float]]]:
    sections: dict[str, dict[str, str | float]] = {}
    section = ""
    for raw in (Path(__file__).parents[1] / "config" / "defaults.yaml").read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith(" ") and raw.rstrip().endswith(":"):
            section = raw.strip()[:-1]
            sections.setdefault(section, {})
            continue
        if section and ":" in raw:
            key, value = raw.strip().split(":", 1)
            scalar = value.strip()
            try:
                sections[section][key] = float(scalar)
            except ValueError:
                sections[section][key] = scalar
    settings = sections["independent_score_snapshot"]
    weights = {
        "theme_credibility": {key: float(value) for key, value in sections["score_theme_credibility"].items()},
        "industry_momentum": {key: float(value) for key, value in sections["score_industry_momentum"].items()},
        "etf_opportunity": {key: float(value) for key, value in sections["score_etf_opportunity"].items()},
    }
    return settings, weights


def independent_score_snapshots(
    theme_id: str,
    as_of: str,
    inputs: dict[str, dict],
    *,
    snapshot_scope: str = "",
) -> dict[str, dict]:
    """Calculate three independent dimensions; never calculate a cross-dimension aggregate."""
    settings, weight_sets = _independent_config()
    config_version = str(settings["config_version"])
    minimum_coverage = float(settings["minimum_input_coverage"])
    scope = snapshot_scope or f"{theme_id}:{as_of}"
    created_at = datetime.now(timezone.utc).isoformat()
    result: dict[str, dict] = {}
    for dimension, weights in weight_sets.items():
        dimension_input = inputs.get(dimension) or {}
        signals = dimension_input.get("signals") or {}
        available_weight = sum(weight for name, weight in weights.items() if signals.get(name) is not None)
        total_weight = sum(weights.values())
        coverage = round(available_weight / total_weight, 4) if total_weight else 0.0
        gate_reasons: list[str] = []
        if dimension == "theme_credibility":
            if int(dimension_input.get("source_type_count") or 0) < int(float(settings["credibility_min_source_types"])):
                gate_reasons.append("独立来源类型不足")
            if int(dimension_input.get("official_source_count") or 0) < int(float(settings["credibility_min_official_sources"])):
                gate_reasons.append("缺少权威来源")
        elif dimension == "industry_momentum":
            if int(dimension_input.get("comparable_snapshot_count") or 0) < int(float(settings["momentum_min_comparable_snapshots"])):
                gate_reasons.append("至少需要两个可比快照")
        elif int(dimension_input.get("verified_product_count") or 0) < int(float(settings["etf_min_verified_products"])):
            gate_reasons.append("已核验 ETF 数量不足")
        if not gate_reasons and coverage < minimum_coverage:
            gate_reasons.append(f"输入覆盖率低于 {minimum_coverage:.0%}")

        assessed = not gate_reasons
        value = None
        if assessed and available_weight:
            weighted = sum(max(0.0, min(1.0, float(signals[name]))) * weight for name, weight in weights.items() if signals.get(name) is not None)
            value = round(weighted / available_weight * 100, 2)
        components = {
            name: {"value": signals.get(name), "weight": weight, "available": signals.get(name) is not None}
            for name, weight in weights.items()
        }
        reasons = gate_reasons or ["由版本化配置和可用输入确定性计算"]
        result[dimension] = {
            "snapshot_id": f"{scope}:{dimension}", "snapshot_scope": scope,
            "theme_id": theme_id, "dimension": dimension, "value": value,
            "status": "assessed" if assessed else "not_assessed", "as_of": as_of,
            "input_coverage": coverage, "config_version": config_version,
            "reasons": reasons, "components": components, "created_at": created_at,
        }
    return result
