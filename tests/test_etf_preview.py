import json
from pathlib import Path

from fastapi.testclient import TestClient

from etf_theme_radar.api import app
from etf_theme_radar.etf_preview import (
    collect_etf_preview_snapshot,
    discover_preview_funds,
    load_preview_config,
    match_theme_preview_products,
    parse_fund_catalog,
    parse_holdings_page,
    parse_market_table,
    parse_profile_page,
    parse_purchase_page,
    parse_quote_history,
    parse_tracking_page,
    parse_trend_script,
)
from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.sync_worker import SyncDiscoveryWorker


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_tiantian_parsers_use_confirmed_field_definitions() -> None:
    trend = parse_trend_script(_fixture("tiantian_pingzhongdata.js"))
    profile = parse_profile_page(_fixture("tiantian_jbgk.html"))
    purchase = parse_purchase_page(_fixture("tiantian_fund.html"))
    tracking = parse_tracking_page(_fixture("tiantian_tracking.html"))
    market_date, market = parse_market_table(_fixture("tiantian_market.html"))
    turnover = parse_quote_history(_fixture("tiantian_quote.json"))

    assert trend["return_2025"] == 20.0
    assert trend["rolling_1y"] == 20.0
    assert trend["yesterday_return"] == 1.42
    assert trend["scale_billion"] == 5.5
    assert profile["operating_fee"] == 0.6
    assert profile["tracking_index"] == "标准普尔500指数"
    assert purchase == {"purchase_status": "暂停申购", "daily_limit_yuan": 100.0}
    assert tracking["tracking_error"] == 1.17
    assert market_date == "2026-08-04"
    assert market["513500"]["premium_rate"] == 2.0
    assert market["513100"]["premium_rate"] is None
    assert turnover["average_turnover_billion_20d"] == 2.0
    assert turnover["turnover_sample_days"] == 2
    assert turnover["closes_by_date"]["2026-07-07"] == 1.0


def test_catalog_classification_is_mutually_exclusive_and_pairs_c_share() -> None:
    catalog = parse_fund_catalog(_fixture("tiantian_fund_catalog.js"))
    discovered = discover_preview_funds(catalog, load_preview_config())

    assert [(item["code"], item["c_code"]) for item in discovered["sp500"]] == [("050025", "006075")]
    assert {item["code"] for item in discovered["exchange"]} == {"513100", "513500"}
    assert {item["code"] for item in discovered["active"]} == {"000043", "012535"}
    all_codes = [item["code"] for values in discovered.values() for item in values]
    assert len(all_codes) == len(set(all_codes))


def test_holdings_parser_identifies_us_market_and_latest_block() -> None:
    payload = '''var apidata={ content:"<label>截止至：<font>2025-12-31</font></label><table><tbody>
    <tr><td>1</td><td><a href='//quote.eastmoney.com/unify/r/105.NVDA'>NVDA</a></td><td>英伟达</td><td>行情</td><td>9.39%</td></tr>
    <tr><td>2</td><td><a href='//quote.eastmoney.com/unify/r/116.00700'>00700</a></td><td>腾讯</td><td>行情</td><td>5.00%</td></tr>
    </tbody></table>"};'''
    parsed = parse_holdings_page(payload)
    assert parsed["holdings_as_of"] == "2025-12-31"
    assert parsed["us_top_holdings_count"] == 1
    assert parsed["us_top_holdings_weight"] == 9.39
    assert parsed["top_holdings_count"] == 2


def test_currency_and_parenthetical_share_suffixes_do_not_become_main_rows() -> None:
    catalog = parse_fund_catalog(
        'var r = [["100001","A","示例标普500指数(QDII)A(人民币)","指数型-海外股票","A"],'
        '["100002","C","示例标普500指数(QDII)C(人民币)","指数型-海外股票","C"],'
        '["100003","USD","示例标普500指数美元汇A","指数型-海外股票","USD"],'
        '["100004","D","示例标普500指数(QDII)D","指数型-海外股票","D"]];'
    )
    discovered = discover_preview_funds(catalog, load_preview_config())
    assert [(item["code"], item["c_code"]) for item in discovered["sp500"]] == [("100001", "100002")]


def test_collection_isolates_missing_same_day_nav_and_preserves_source_urls() -> None:
    config = load_preview_config()
    config["classification"]["active_target_minimum"] = 2

    def fetch(url: str) -> str:
        if "fundcode_search" in url:
            return _fixture("tiantian_fund_catalog.js")
        if "cnjy_zrljjz" in url:
            return _fixture("tiantian_market.html")
        if "pingzhongdata" in url:
            return _fixture("tiantian_pingzhongdata.js")
        if "jbgk_" in url:
            return _fixture("tiantian_jbgk.html")
        if "tsdata_" in url:
            return _fixture("tiantian_tracking.html")
        if "FundArchivesDatas" in url:
            return """var apidata={ content:\"<label>截止至：<font>2025-12-31</font></label><table><tbody>""" + "".join(
                f"<tr><td>{i}</td><td><a href='//quote.eastmoney.com/unify/r/105.US{i}'>US{i}</a></td><td>美股{i}</td><td>行情</td><td>5.00%</td></tr>"
                for i in range(1, 11)
            ) + "</tbody></table>\"};"
        if "push2his" in url:
            return _fixture("tiantian_quote.json")
        if url.endswith(".html"):
            return _fixture("tiantian_fund.html")
        raise AssertionError(url)

    snapshot = collect_etf_preview_snapshot(config, fetcher=fetch)
    assert snapshot["counts"] == {"sp500": 1, "exchange": 2, "active": 2}
    assert snapshot["total"] == 5
    assert snapshot["status"] == "available"
    sp500 = snapshot["categories"]["sp500"][0]
    assert sp500["c_share"]["code"] == "006075"
    assert sp500["operating_fee"] == 0.6
    exchange = {item["code"]: item for item in snapshot["categories"]["exchange"]}
    assert exchange["513500"]["premium_rate"] == 2.0
    assert exchange["513100"]["premium_rate"] is None
    assert exchange["513500"]["source_url"].startswith("https://fund.eastmoney.com/")


def test_preview_snapshot_store_is_immutable_and_latest_wins(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "preview.db")
    first = {"snapshot_id": "one", "collected_at": "2026-08-04T00:00:00+00:00", "market_as_of": "2026-08-03", "status": "available", "source": "天天基金网", "total": 1}
    second = {"snapshot_id": "two", "collected_at": "2026-08-05T00:00:00+00:00", "market_as_of": "2026-08-04", "status": "partial", "source": "天天基金网", "total": 2}
    store.save_etf_preview_snapshot(first)
    store.save_etf_preview_snapshot(second)
    assert store.latest_etf_preview_snapshot()["snapshot_id"] == "two"
    count = store.conn.execute("SELECT COUNT(*) FROM etf_preview_snapshots").fetchone()[0]
    assert count == 2
    store.close()


def test_preview_store_rejects_empty_snapshot_without_replacing_last_success(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "preview-empty.db")
    good = {
        "snapshot_id": "good", "collected_at": "2026-08-14T00:00:00+00:00",
        "market_as_of": "2026-08-13", "status": "available", "source": "天天基金网",
        "total": 1, "categories": {"exchange": [{"code": "513100"}]},
    }
    assert store.save_etf_preview_snapshot(good) is True
    assert store.save_etf_preview_snapshot({
        "snapshot_id": "empty", "collected_at": "2026-08-14T01:00:00+00:00",
        "market_as_of": "", "status": "unknown", "source": "天天基金网",
        "total": 0, "categories": {},
    }) is False
    assert store.latest_etf_preview_snapshot()["snapshot_id"] == "good"
    store.close()


def test_theme_link_uses_explicit_terms_and_preserves_snapshot_provenance() -> None:
    snapshot = {
        "snapshot_id": "preview-one", "collected_at": "2026-08-05T00:00:00+00:00",
        "market_as_of": "2026-08-04", "source": "Tiantian",
        "categories": {
            "exchange": [
                {"code": "100001", "name": "AI 基础设施 ETF", "tracking_index": "人工智能基础设施指数", "scale_billion": 10, "source_url": "https://fund.eastmoney.com/100001.html"},
                {"code": "100002", "name": "美国宽基 ETF", "pinyin": "HAITONGMEIGU", "tracking_index": "美国大盘指数", "scale_billion": 20, "source_url": "https://fund.eastmoney.com/100002.html"},
            ],
            "active": [{"code": "100003", "name": "美股主动基金", "tracking_index": "", "scale_billion": 30}],
        },
    }
    linked = match_theme_preview_products(
        snapshot, "ai-infrastructure", "AI 基础设施", ["人工智能基础设施", "美股"],
    )
    assert linked["snapshot_id"] == "preview-one"
    assert linked["market_as_of"] == "2026-08-04"
    assert [item["code"] for item in linked["products"]] == ["100001"]
    assert linked["products"][0]["matched_fields"]["name"] == ["AI 基础设施"]


def test_preview_api_search_sort_and_refresh_are_auditable(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "api.db"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("STARTUP_SYNC_ENABLED", "false")

    class _Worker:
        def wake(self) -> None:
            return None

    monkeypatch.setattr("etf_theme_radar.api.sync_worker_for", lambda _path: _Worker())
    store = EvidenceStore(database)
    store.save_etf_preview_snapshot({
        "snapshot_id": "sample", "collected_at": "2026-08-05T00:00:00+00:00",
        "market_as_of": "2026-08-04", "status": "available", "source": "天天基金网",
        "categories": {
            "sp500": [
                {"code": "000001", "c_code": "000002", "name": "低费率基金", "operating_fee": 0.2, "scale_billion": 2},
                {"code": "000003", "c_code": "000004", "name": "大规模基金", "operating_fee": 0.8, "scale_billion": 10},
            ],
            "exchange": [], "active": [],
        },
        "counts": {"sp500": 2, "exchange": 0, "active": 0}, "total": 2,
        "errors": [], "premium_thresholds": {"attention": 1, "elevated": 2, "high": 3},
    })
    store.close()
    with TestClient(app) as client:
        response = client.get("/api/etf-preview", params={"category": "sp500", "q": "000002", "sort_by": "operating_fee", "order": "asc"})
        assert response.status_code == 200
        payload = response.json()
        assert [item["code"] for item in payload["items"]] == ["000001"]
        assert payload["filtered_count"] == 1
        refresh = client.post("/api/etf-preview/refresh")
        assert refresh.status_code == 202
        assert refresh.json()["poll_url"].startswith("/api/sync-runs/")


def test_preview_sync_has_priority_and_persists_without_mutating_old_snapshot(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "worker.db"
    store = EvidenceStore(database)
    store.save_etf_preview_snapshot({
        "snapshot_id": "old", "collected_at": "2026-08-04T00:00:00+00:00",
        "market_as_of": "2026-08-03", "status": "available", "source": "天天基金网",
        "categories": {"sp500": [{"code": "513500"}], "exchange": [], "active": []},
        "counts": {"sp500": 1}, "total": 1, "errors": [],
    })
    store.create_sync_run("normal", "2026-08-05T00:00:00+00:00", days=7, idempotency_key="manual:normal")
    store.create_sync_run("preview", "2026-08-05T00:01:00+00:00", days=0, idempotency_key="etf-preview:manual:preview")
    claimed = store.claim_next_sync_run("owner", "2026-08-05T00:02:00+00:00", "2026-08-05T00:03:00+00:00")
    assert claimed and claimed["sync_run_id"] == "preview"
    store.update_sync_run("preview", status="queued", progress=0, updated_at="2026-08-05T00:02:00+00:00")
    store.conn.execute("UPDATE sync_runs SET lease_owner='',lease_expires_at='',heartbeat_at='' WHERE sync_run_id='preview'")
    store.commit()
    store.close()

    monkeypatch.setattr("etf_theme_radar.sync_worker.collect_etf_preview_snapshot", lambda **_kwargs: {
        "snapshot_id": "new", "collected_at": "2026-08-05T00:03:00+00:00",
        "market_as_of": "2026-08-04", "status": "available", "source": "天天基金网",
        "categories": {"sp500": [{"code": "513500"}], "exchange": [], "active": []},
        "counts": {"sp500": 1}, "total": 1, "errors": [],
    })
    worker = SyncDiscoveryWorker(database)
    assert worker.run_once() is True
    store = EvidenceStore(database)
    assert store.sync_run("preview")["status"] == "completed"
    assert store.latest_etf_preview_snapshot()["snapshot_id"] == "new"
    assert store.conn.execute("SELECT COUNT(*) FROM etf_preview_snapshots").fetchone()[0] == 2
    store.close()
