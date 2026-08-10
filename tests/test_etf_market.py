from pathlib import Path

from etf_theme_radar.etf_market import calculate_market_metrics, collect_dual_source_market_snapshot, collect_market_snapshot, match_competitors
from etf_theme_radar.etf_discovery import verify_etf_candidate
from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.workflow import execute_market_refresh


def _rows(count: int = 90, *, rising: bool = True) -> list[dict]:
    return [
        {
            "date": f"2026-04-{(index % 28) + 1:02d}T00:00:00+00:00",
            "close": 100 + index if rising else 190 - index,
            "volume": 1_000_000 + index * 10_000,
        }
        for index in range(count)
    ]


def test_market_metrics_are_deterministic_and_do_not_claim_buyers() -> None:
    metrics = calculate_market_metrics(_rows())
    assert metrics["returns"]["1w"] > 0
    assert metrics["returns"]["1m"] > 0
    assert metrics["max_drawdown_3m"] == 0
    assert metrics["average_dollar_volume_20d"] > 0
    assert metrics["buyer_count_status"] == "not_available"
    assert metrics["fund_flow_status"] == "not_assessed"


def test_market_collection_isolates_one_ticker_failure(tmp_path: Path) -> None:
    funds = [
        {"ticker": "BOTZ", "issuer": "Global X", "category": "机器人", "holdings_url": "https://issuer/BOTZ"},
        {"ticker": "ROBO", "issuer": "ROBO Global", "category": "机器人", "holdings_url": "https://issuer/ROBO"},
    ]

    def fetcher(ticker: str) -> list[dict]:
        if ticker == "ROBO":
            raise RuntimeError("rate limited")
        return _rows()

    snapshot = collect_market_snapshot(funds, tmp_path / "cache", fetcher)
    assert snapshot["status"] == "partial"
    assert snapshot["products"][0]["data_status"] == "available"
    assert snapshot["products"][1]["data_status"] == "unavailable"
    assert "买入人数" in snapshot["limitations"][1]


def test_global_market_uses_yahoo_symbol_and_local_currency(tmp_path: Path) -> None:
    requested: list[str] = []
    fund = {
        "ticker": "NUCG", "yahoo_symbol": "NUCG.L", "issuer": "Example Issuer",
        "category": "核能", "exchange": "London Stock Exchange",
        "listing_market": "United Kingdom", "currency": "GBP",
        "official_url": "https://issuer.example/nucg",
    }

    snapshot = collect_market_snapshot(
        [fund], tmp_path / "global-cache",
        lambda symbol: requested.append(symbol) or _rows(),
    )

    product = snapshot["products"][0]
    assert requested == ["NUCG.L"]
    assert product["currency"] == "GBP"
    assert product["listing_market"] == "United Kingdom"
    assert "不同币种" in snapshot["limitations"][-1]


def test_market_collection_treats_empty_yahoo_response_as_failure(tmp_path: Path) -> None:
    snapshot = collect_market_snapshot(
        [{"ticker": "BOTZ", "issuer": "Global X", "category": "机器人"}],
        tmp_path / "empty-cache", lambda _ticker: [],
    )

    assert snapshot["status"] == "unknown"
    assert snapshot["products"][0]["data_status"] == "unavailable"
    assert "未返回" in snapshot["products"][0]["error"]
    assert not (tmp_path / "empty-cache" / "botz-history.json").exists()


def test_empty_legacy_cache_is_replaced_by_one_live_attempt(tmp_path: Path) -> None:
    cache = tmp_path / "legacy-empty-cache"
    cache.mkdir()
    (cache / "botz-history.json").write_text("[]", encoding="utf-8")
    requests: list[str] = []

    snapshot = collect_market_snapshot(
        [{"ticker": "BOTZ", "issuer": "Global X", "category": "机器人"}],
        cache, lambda ticker: requests.append(ticker) or _rows(),
    )

    assert requests == ["BOTZ"]
    assert snapshot["products"][0]["data_status"] == "available"
    assert snapshot["products"][0]["cache_status"] == "miss"


def test_dynamic_candidate_requires_official_page_and_listing_metadata() -> None:
    valid = verify_etf_candidate({
        "ticker": "URA", "yahoo_symbol": "URA", "fund_name": "Uranium ETF",
        "issuer": "Global X", "category": "铀产业链", "exchange": "NYSE Arca",
        "listing_market": "United States", "currency": "USD",
        "official_url": "https://www.globalxetfs.com/funds/ura",
        "discovery_url": "https://example.com/lead", "relevance_reason": "核燃料子赛道",
    })
    invalid = verify_etf_candidate({
        "ticker": "FAKE", "yahoo_symbol": "FAKE", "fund_name": "Fake",
        "issuer": "Unknown", "category": "核能", "exchange": "Unknown",
        "listing_market": "United States", "currency": "USD",
        "official_url": "https://finance.yahoo.com/quote/FAKE",
        "relevance_reason": "聚合页",
    })
    assert valid and valid["verification_status"] == "official_url_verified"
    assert invalid is None


def test_robotics_competitors_use_explicit_theme_tags() -> None:
    tickers = {item["ticker"] for item in match_competitors("robotics", "机器人", ["robot"])}
    assert {"BOTZ", "ROBO", "IRBO", "ARKQ"}.issubset(tickers)


def test_market_refresh_creates_independent_snapshot_without_changing_report(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "reports.db"
    store = EvidenceStore(database)
    created = "2026-07-31T00:00:00+00:00"
    store.create_research_run("parent", "robotics", created, {"sources": ["etf_news"]}, status="completed", stage="completed")
    result = {"detail": {"landscape": {"similar_etfs": [{"ticker": "BOTZ"}]}}}
    asset = {
        "report_id": "report:parent", "run_id": "parent", "title": "机器人报告", "kind": "theme_report",
        "theme_id": "robotics", "folder_id": "robotics", "status": "watch", "tags": ["机器人"],
        "summary": "摘要", "updated_at": created, "created_at": created, "version": 1,
        "source_count": 1, "evidence_count": 1, "audit_passed": True,
    }
    store.save_report_asset(asset)
    store.save_report_version("report:parent", 1, {"asset": asset, "result": result}, "v1", created)
    store.create_research_run(
        "refresh", "report-refresh:report:parent", created, {"report_id": "report:parent"},
        status="queued", stage="market_refresh", database_path=str(database),
    )
    store.close()
    monkeypatch.setattr(
        "etf_theme_radar.workflow.collect_dual_source_market_snapshot",
        lambda *_args, **_kwargs: {"status": "partial", "market_as_of": "2026-07-31", "products": [{"ticker": "BOTZ", "data_status": "available"}], "source_status": {"yfinance": {"status": "available"}, "tiantian": {"status": "not_assessed"}}},
    )

    execute_market_refresh(str(database), "refresh")

    store = EvidenceStore(database)
    versions = store.report_versions("report:parent")
    assert [item["version"] for item in versions] == [1]
    assert versions[0]["markdown"] == "v1"
    assert store.report_asset("report:parent")["version"] == 1
    snapshot = store.latest_etf_market_snapshot("report:parent")
    assert snapshot and snapshot["products"][0]["ticker"] == "BOTZ"
    assert store.research_run("refresh")["status"] == "completed"
    store.close()


def test_market_failure_uses_last_successful_cache(tmp_path: Path) -> None:
    fund = {"ticker": "BOTZ", "issuer": "Global X", "category": "机器人"}
    cache = tmp_path / "cache"
    first = collect_market_snapshot([fund], cache, lambda _ticker: _rows())
    assert first["products"][0]["data_status"] == "available"
    history = cache / "botz-history.json"
    history.touch()
    # Force the cache outside the normal TTL while retaining it as stale-if-error.
    import os, time
    old = time.time() - 7200
    os.utime(history, (old, old))
    second = collect_market_snapshot([fund], cache, lambda _ticker: (_ for _ in ()).throw(RuntimeError("429 rate limited")))
    assert second["products"][0]["data_status"] == "stale"
    assert second["products"][0]["cache_status"] == "stale_if_error"
    assert second["products"][0]["last_close"] == first["products"][0]["last_close"]


def test_dual_source_snapshot_preserves_field_provenance_and_conflicts(tmp_path: Path) -> None:
    snapshot = collect_dual_source_market_snapshot(
        [{"ticker": "513100", "yahoo_symbol": "513100.SS", "fund_name": "Nasdaq ETF", "currency": "CNY"}],
        {
            "snapshot_id": "tiantian-1", "status": "available", "market_as_of": "2026-08-04",
            "products": [{"code": "513100", "name": "纳指ETF", "scale_billion": 20, "operating_fee": .8, "source_url": "https://fund.eastmoney.com/513100.html"}],
        },
        tmp_path / "dual-cache", lambda _ticker: _rows(),
    )
    product = snapshot["products"][0]
    assert {item["name"] for item in product["sources"]} == {"Yahoo Finance via yfinance", "天天基金网"}
    assert product["field_provenance"]["last_close"] == "yfinance"
    assert product["field_provenance"]["operating_fee"] == "tiantian"
    assert product["cross_source_validation"]["status"] == "conflict"
    assert snapshot["validation_summary"]["conflict"] == 1


def test_failed_dual_refresh_does_not_overwrite_last_successful_snapshot(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "retain.db"
    store = EvidenceStore(database)
    created = "2026-07-31T00:00:00+00:00"
    asset = {"report_id":"report:retain","run_id":"parent","title":"报告","kind":"theme_report","theme_id":"robotics","folder_id":"robotics","status":"watch","tags":[],"summary":"摘要","updated_at":created,"created_at":created,"version":1,"source_count":1,"evidence_count":1,"audit_passed":True}
    store.save_report_asset(asset)
    store.save_report_version("report:retain",1,{"asset":asset,"result":{"detail":{"landscape":{"similar_etfs":[]}}}},"v1",created)
    store.save_etf_market_snapshot({"snapshot_id":"good","report_id":"report:retain","collected_at":created,"market_as_of":"2026-07-31","status":"available","products":[{"ticker":"BOTZ"}],"payload":{"products":[{"ticker":"BOTZ"}]}})
    store.create_research_run("failed-refresh","report-refresh:report:retain",created,{"report_id":"report:retain"},status="queued",stage="market_refresh",database_path=str(database))
    store.close()
    monkeypatch.setattr("etf_theme_radar.workflow.collect_dual_source_market_snapshot",lambda *_args,**_kwargs:{"status":"unknown","products":[],"source_status":{"yfinance":{"status":"unknown"},"tiantian":{"status":"not_assessed"}}})
    execute_market_refresh(str(database),"failed-refresh")
    store=EvidenceStore(database)
    assert store.latest_etf_market_snapshot("report:retain")["snapshot_id"] == "good"
    assert store.research_run("failed-refresh")["status"] == "failed"
    store.close()
