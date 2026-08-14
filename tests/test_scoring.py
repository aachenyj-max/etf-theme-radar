from etf_theme_radar.models import ThemeMetrics
from etf_theme_radar.scoring import independent_score_snapshots, opportunity_score, white_space_score
from etf_theme_radar.store import EvidenceStore


def test_score_is_deterministic_and_gated():
    metrics = ThemeMetrics("t", {"research_momentum": 100}, ("official",), 1, 2, ())
    assert opportunity_score(metrics)["confidence"] == "low"
    assert opportunity_score(metrics)["opportunity_score"] == 20


def test_white_space():
    assert white_space_score([.2, .8]) == 20


def test_independent_scores_are_configured_versioned_and_never_aggregated():
    snapshots = independent_score_snapshots(
        "ai-infrastructure", "2026-08-14",
        {
            "theme_credibility": {
                "signals": {"authority": .9, "source_diversity": .8, "consistency": .7, "persistence": .6, "entity_coverage": .5},
                "source_type_count": 4, "official_source_count": 2,
            },
            "industry_momentum": {
                "signals": {"research": .8, "patents": .6, "hiring": .7, "capital_projects": .5, "commercial_adoption": .4, "chain_diffusion": .6},
                "comparable_snapshot_count": 2,
            },
            "etf_opportunity": {
                "signals": {"verified_products": .8, "purity": .7, "differentiation": .6, "holdings_coverage": .8, "fee_liquidity": .5, "tradability": .9},
                "verified_product_count": 3,
            },
        },
    )

    assert set(snapshots) == {"theme_credibility", "industry_momentum", "etf_opportunity"}
    assert all(item["status"] == "assessed" and 0 <= item["value"] <= 100 for item in snapshots.values())
    assert all(item["as_of"] == "2026-08-14" and item["config_version"] == "independent-scores-v1" for item in snapshots.values())
    assert all(0 <= item["input_coverage"] <= 1 and item["reasons"] for item in snapshots.values())
    assert not ({"overall_score", "composite_score", "weights_between_dimensions"} & snapshots.keys())


def test_independent_score_uses_not_assessed_when_dimension_gate_is_missing():
    snapshots = independent_score_snapshots(
        "new-theme", "2026-08-14",
        {
            "theme_credibility": {"signals": {"authority": .8}, "source_type_count": 1, "official_source_count": 1},
            "industry_momentum": {"signals": {"research": .9}, "comparable_snapshot_count": 1},
            "etf_opportunity": {"signals": {}, "verified_product_count": 0},
        },
    )

    assert all(item["status"] == "not_assessed" for item in snapshots.values())
    assert all(item["value"] is None for item in snapshots.values())
    assert snapshots["industry_momentum"]["reasons"] == ["至少需要两个可比快照"]


def test_independent_score_snapshots_round_trip_without_composite_field(tmp_path):
    store = EvidenceStore(tmp_path / "scores.db")
    snapshots = independent_score_snapshots(
        "theme-one", "2026-08-14",
        {
            "theme_credibility": {"signals": {}, "source_type_count": 0, "official_source_count": 0},
            "industry_momentum": {"signals": {}, "comparable_snapshot_count": 0},
            "etf_opportunity": {"signals": {}, "verified_product_count": 0},
        },
        snapshot_scope="run-one",
    )
    store.save_independent_score_snapshots(list(snapshots.values()))

    saved = store.independent_score_snapshots("theme-one")
    assert [item["dimension"] for item in saved] == ["etf_opportunity", "industry_momentum", "theme_credibility"]
    assert all("overall_score" not in item and "composite_score" not in item for item in saved)
    assert all(item["snapshot_scope"] == "run-one" for item in saved)
    store.close()
