from __future__ import annotations

import json
import os
from pathlib import Path

from .official_connectors import (AnySearchDiscoveryConnector, GooglePatentsDiscoveryConnector, OfficialEtfHoldingsConnector, OpenAlexPapersConnector, PublicJobBoardsConnector, SecEtfFilingConnector, SpGlobalDjiConnector, YahooEtfNewsConnector)

def load_project_env(path: Path = Path(".env")) -> None:
    """Load simple KEY=value settings without printing or overriding process secrets."""
    if not path.exists(): return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _enabled(name: str, default: bool = True) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def configured_connectors(cache_root: Path):
    """Create all connectors; unconfigured optional sources report degraded/disabled health."""
    load_project_env()
    holdings_env = os.getenv("ETF_HOLDINGS_FEEDS_JSON", "").strip()
    if holdings_env:
        holdings_feeds = json.loads(holdings_env)
        news_funds = [{"ticker": str(item.get("ticker", "")), "issuer": str(item.get("issuer", ""))} for item in holdings_feeds]
    else:
        universe_path = Path(__file__).parents[1] / "config" / "etf-competitor-universe.json"
        universe = json.loads(universe_path.read_text(encoding="utf-8")) if universe_path.exists() else []
        holdings_feeds = [
            {"ticker": item["ticker"], "url": item["holdings_url"], "format": item.get("holdings_format", "html")}
            for item in universe if item.get("holdings_url")
        ]
        news_funds = [{"ticker": item["ticker"], "issuer": item.get("issuer", "")} for item in universe if item.get("ticker")]
    sp_global_env = os.getenv("SP_GLOBAL_RSS_FEEDS_JSON", "").strip()
    if sp_global_env:
        sp_global_feeds = json.loads(sp_global_env)
    else:
        sp_global_path = Path(__file__).parents[1] / "config" / "sp-global-public-feeds.json"
        sp_global_feeds = json.loads(sp_global_path.read_text(encoding="utf-8")) if sp_global_path.exists() else []
    return [
        SecEtfFilingConnector(cache_root / "sec", enabled=_enabled("SEC_ENABLED")),
        OpenAlexPapersConnector(cache_root / "openalex", enabled=_enabled("OPENALEX_ENABLED")),
        GooglePatentsDiscoveryConnector(cache_root / "google-patents", enabled=_enabled("GOOGLE_PATENTS_ENABLED")),
        PublicJobBoardsConnector(cache_root / "jobs", enabled=_enabled("JOB_BOARDS_ENABLED")),
        OfficialEtfHoldingsConnector(cache_root / "holdings", feeds=holdings_feeds, enabled=_enabled("ETF_HOLDINGS_ENABLED")),
        YahooEtfNewsConnector(cache_root / "yahoo-etf-news", funds=news_funds, enabled=_enabled("YAHOO_ETF_NEWS_ENABLED")),
        SpGlobalDjiConnector(cache_root / "sp-global", feeds=sp_global_feeds, enabled=_enabled("SP_GLOBAL_ENABLED", False)),
        AnySearchDiscoveryConnector(cache_root / "anysearch", enabled=_enabled("ANYSEARCH_ENABLED", False)),
    ]
