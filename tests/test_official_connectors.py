from pathlib import Path
from etf_theme_radar.official_connectors import AnySearchDiscoveryConnector, GooglePatentsDiscoveryConnector, OfficialEtfHoldingsConnector, PublicJobBoardsConnector, SpGlobalDjiConnector, YahooEtfNewsConnector
from etf_theme_radar.models import RawDocument

def test_holdings_csv_normalizes_constituents_without_network(tmp_path: Path):
    url = "https://issuer.test/holdings.csv"; connector = OfficialEtfHoldingsConnector(tmp_path, feeds=[{"ticker": "TEST", "url": url}]); connector.records[url] = {"ticker": "TEST", "url": url}
    raw = RawDocument("official_etf_holdings", url, "TEST official holdings", "Ticker,Name,Weight (%)\nABC,Example Corp,7.5\n", "etf")
    events = connector.normalize(raw)
    assert len(events) == 1 and events[0].tickers == ("ABC",) and events[0].companies == ("Example Corp",)

def test_job_board_health_is_configurable(tmp_path: Path):
    health = PublicJobBoardsConnector(tmp_path, boards=[{"company": "Example", "provider": "greenhouse", "board": "example"}]).healthcheck()
    assert health.status == "healthy" and "已配置 1 个" in health.coverage_note

def test_job_board_failure_does_not_hide_healthy_board(tmp_path: Path, monkeypatch):
    connector = PublicJobBoardsConnector(tmp_path, boards=[
        {"company": "Broken", "provider": "greenhouse", "board": "broken"},
        {"company": "Healthy", "provider": "greenhouse", "board": "healthy"},
    ])
    def request(url: str, headers=None) -> bytes:
        if "broken" in url:
            raise TimeoutError("temporary timeout")
        return b'{"jobs":[{"id":1,"title":"AI Engineer","absolute_url":"https://healthy.test/jobs/1"}]}'
    monkeypatch.setattr(connector, "_request", request)
    ids = connector.discover(__import__("datetime").date(2026, 7, 1), __import__("datetime").date(2026, 7, 2))
    assert len(ids) == 1
    assert connector.discovery_errors and "Broken" in connector.discovery_errors[0]

def test_holdings_html_snapshot_normalizes(tmp_path: Path):
    url = "https://issuer.test/fund"
    connector = OfficialEtfHoldingsConnector(tmp_path, feeds=[{"ticker": "TEST", "url": url, "format": "html"}])
    connector.records[url] = {"ticker": "TEST", "url": url, "format": "html"}
    raw = RawDocument("official_etf_holdings", url, "TEST official holdings", "<html><h2>Holdings</h2><table><tr><td>ABC</td><td>Example Corp</td><td>7.5%</td></tr></table></html>", "etf")
    events = connector.normalize(raw)
    assert len(events) == 1 and events[0].tickers == ("TEST",)
    assert "Example Corp" in events[0].summary

def test_sp_global_public_rss_discovers_and_normalizes_without_network(tmp_path: Path, monkeypatch):
    feed = "https://www.spglobal.com/spdji/en/rss/rss-details/?rssFeedName=index-news-announcements"
    connector = SpGlobalDjiConnector(tmp_path, feeds=[feed])
    fixture = Path("tests/fixtures/sp_global_rss.xml").read_bytes()
    monkeypatch.setattr(connector, "_rss", lambda _url: fixture)
    ids = connector.discover(__import__("datetime").date(2026, 7, 28), __import__("datetime").date(2026, 7, 30))
    assert len(ids) == 1
    raw = connector.fetch(ids[0])
    events = connector.normalize(raw)
    assert raw.source_url.endswith("example.pdf")
    assert events[0].source_quality == 0.90
    assert "ai-infrastructure" in events[0].themes

def test_sp_global_public_rss_health_requires_a_feed(tmp_path: Path):
    assert SpGlobalDjiConnector(tmp_path, feeds=[]).healthcheck().status == "degraded"

def test_google_patents_filters_non_patent_results_and_marks_patent_type(tmp_path: Path, monkeypatch):
    connector = GooglePatentsDiscoveryConnector(tmp_path, queries=["robotics"], skill_dir=Path("skills/anysearch"))
    connector.records = {
        "patent": {"title": "Robot patent", "url": "https://patents.google.com/patent/US123", "snippet": "robotics"},
        "news": {"title": "Robot news", "url": "https://example.com/news", "snippet": "robotics"},
    }
    monkeypatch.setattr(AnySearchDiscoveryConnector, "discover", lambda self, since, until, cursor=None: list(self.records))
    ids = connector.discover(__import__("datetime").date(2026, 7, 1), __import__("datetime").date(2026, 7, 2))
    raw = connector.fetch(ids[0])
    assert ids == ["patent"]
    assert raw.source == "google_patents" and raw.source_type == "patent"
    assert connector.healthcheck().status == "healthy"

def test_yahoo_etf_news_isolates_ticker_failure_and_preserves_metadata(tmp_path: Path, monkeypatch):
    class FakeTicker:
        def __init__(self, ticker: str): self.ticker = ticker
        def get_news(self, count: int, tab: str):
            if self.ticker == "BROKEN": raise TimeoutError("temporary timeout")
            return [{"content": {
                "title": "AI ETF launch update",
                "summary": "Public ETF news summary.",
                "pubDate": "2026-07-29T12:00:00Z",
                "canonicalUrl": {"url": "https://news.example/ai-etf"},
                "provider": {"displayName": "Example News"},
            }}]
    monkeypatch.setitem(__import__("sys").modules, "yfinance", __import__("types").SimpleNamespace(Ticker=FakeTicker))
    connector = YahooEtfNewsConnector(tmp_path, funds=[{"ticker": "AIQ"}, {"ticker": "BROKEN"}])
    connector.max_tickers_per_run = 2
    ids = connector.discover(__import__("datetime").date(2026, 7, 28), __import__("datetime").date(2026, 7, 30))
    raw = connector.fetch(ids[0])
    event = connector.normalize(raw)[0]
    assert len(ids) == 1 and connector.discovery_errors == ["BROKEN: temporary timeout"]
    assert raw.source_url == "https://news.example/ai-etf" and raw.published_at == "2026-07-29T12:00:00+00:00"
    assert raw.source_type == "social" and event.tickers == ("AIQ",)

def test_etf_source_cache_ttls_and_yahoo_cache_hit(tmp_path: Path, monkeypatch):
    calls = {"count": 0}
    class FakeTicker:
        def __init__(self, ticker: str): self.ticker = ticker
        def get_news(self, count: int, tab: str):
            calls["count"] += 1
            return [{"content": {"title": "Cached ETF news", "pubDate": "2026-07-29T12:00:00Z", "canonicalUrl": {"url": "https://news.example/cached"}}}]
    monkeypatch.setitem(__import__("sys").modules, "yfinance", __import__("types").SimpleNamespace(Ticker=FakeTicker))
    yahoo = YahooEtfNewsConnector(tmp_path / "news", funds=[{"ticker": "AIQ"}])
    holdings = OfficialEtfHoldingsConnector(tmp_path / "holdings", feeds=[])
    since = __import__("datetime").date(2026, 7, 28)
    until = __import__("datetime").date(2026, 7, 30)
    assert yahoo.discover(since, until)
    assert yahoo.discover(since, until)
    assert calls["count"] == 1
    assert yahoo.cache_ttl_seconds == 1800
    assert holdings.cache_ttl_seconds == 21600
