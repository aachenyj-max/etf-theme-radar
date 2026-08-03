"""Public-source connectors for the ETF Theme Radar.

Each connector is independently configurable and failure-tolerant.  Search results
are discovery leads; primary/public-source connectors remain the evidence of record.
"""
from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .connectors import SourceConnector
from .models import ConnectorHealth, NormalizedEvent, RawDocument, utcnow
from .sec_parser import parse_sec_etf_filing


def _json_env(name: str, default: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    value = os.getenv(name, "")
    if not value:
        return default or []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError(f"{name} must be a JSON array")
    return parsed


def _themes(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    mappings = {
        "edge-ai-infrastructure": ("edge ai", "inference", "on-device ai"),
        "ai-infrastructure": ("ai infrastructure", "artificial intelligence", "generative ai", "accelerator"),
        "robotics": ("robot", "automation", "vision-language-action"),
        "semiconductors": ("semiconductor", "chip", "gpu", "asic"),
    }
    return tuple(theme for theme, terms in mappings.items() if any(term in lowered for term in terms)) or ("unclassified",)


class PublicHttpConnector(SourceConnector):
    """Small HTTP client with cache, timeout, retry, and no access-control bypass."""
    timeout_seconds = 20
    retries = 2
    min_interval_seconds = 0.25
    cache_ttl_seconds: int | None = None

    def __init__(self, cache_dir: Path, enabled: bool = True):
        self.cache_dir, self.enabled = cache_dir, enabled
        self.timeout_seconds = int(os.getenv("SOURCE_TIMEOUT_SECONDS", str(self.timeout_seconds)))
        self.retries = int(os.getenv("SOURCE_RETRIES", str(self.retries)))
        self.min_interval_seconds = float(os.getenv("SOURCE_MIN_INTERVAL_SECONDS", str(self.min_interval_seconds)))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_request = 0.0
        self.cache_hits = 0
        self.cache_misses = 0

    def _request(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        if not self.enabled:
            raise RuntimeError(f"{self.source_name} connector is disabled")
        key = sha256(url.encode("utf-8")).hexdigest()
        target = self.cache_dir / key
        if target.exists() and self.cache_ttl_seconds is not None and time.time() - target.stat().st_mtime > self.cache_ttl_seconds:
            target.unlink()
        if target.exists():
            self.cache_hits += 1
            return target.read_bytes()
        self.cache_misses += 1
        for attempt in range(self.retries + 1):
            try:
                delay = self.min_interval_seconds - (time.monotonic() - self._last_request)
                if delay > 0:
                    time.sleep(delay)
                request = Request(url, headers=headers or {"Accept": "application/json"})
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = response.read()
                self._last_request = time.monotonic()
                target.write_bytes(payload)
                return payload
            except Exception:
                if attempt == self.retries:
                    raise
                time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def _event(self, document: RawDocument, summary: str, themes: tuple[str, ...], *, companies: tuple[str, ...] = (), tickers: tuple[str, ...] = (), quality: float = 0.7) -> NormalizedEvent:
        return NormalizedEvent(
            event_id=document.content_hash[:24], source=document.source, source_url=document.source_url,
            source_type=document.source_type, title=document.title, summary=summary[:1200],
            published_at=document.published_at, observed_at=utcnow(), themes=themes,
            companies=companies, tickers=tickers, source_quality=quality,
            extraction_confidence=0.80, raw_content_hash=document.content_hash,
        )


class SecEtfFilingConnector(PublicHttpConnector):
    """Scans SEC daily form indexes for new ETF-related registrations and amendments."""
    source_name = "sec_edgar_etf"
    forms = ("N-1A", "485APOS", "485BPOS", "497", "N-CSR", "NPORT-P")

    def __init__(self, cache_dir: Path, user_agent: str | None = None, enabled: bool = True):
        super().__init__(cache_dir, enabled)
        self.user_agent = user_agent or os.getenv("SEC_USER_AGENT", "")

    def _headers(self) -> dict[str, str]:
        if not self.user_agent:
            raise RuntimeError("SEC_USER_AGENT with organisation and contact email is required")
        return {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}

    @staticmethod
    def _index_url(day: date) -> str:
        quarter = (day.month - 1) // 3 + 1
        return f"https://www.sec.gov/Archives/edgar/daily-index/{day.year}/QTR{quarter}/form.{day:%Y%m%d}.idx"

    def discover(self, since: date, until: date, cursor: str | None = None) -> list[str]:
        results: list[str] = []
        maximum = int(os.getenv("SEC_MAX_FILINGS", "100"))
        current = since
        while current <= until:
            try:
                body = self._request(self._index_url(current), self._headers()).decode("latin-1", "replace")
            except Exception:
                current += timedelta(days=1)
                continue  # weekends/holidays and transient failures are non-blocking
            for line in body.splitlines():
                pieces = line.split("|")
                if len(pieces) != 5 or pieces[2] not in self.forms:
                    continue
                filing_path = pieces[4].strip()
                results.append(f"https://www.sec.gov/Archives/{filing_path}")
                if len(results) >= maximum:
                    return results
            current += timedelta(days=1)
        return results

    def fetch(self, item_id: str) -> RawDocument:
        text = self._request(item_id, self._headers()).decode("utf-8", "replace")
        title = re.search(r"<TITLE>(.*?)</TITLE>", text, re.I | re.S)
        return RawDocument(self.source_name, item_id, re.sub(r"\s+", " ", title.group(1)).strip() if title else "SEC ETF filing", text, "official", access_note="SEC public filing")

    def normalize(self, document: RawDocument) -> list[NormalizedEvent]:
        parsed = parse_sec_etf_filing(document.text, document.source_url)
        event_type = parsed["filing_event_type"] or "unknown"
        fund_name = parsed["fund_name"] or document.title
        summary = json.dumps(parsed, ensure_ascii=False)
        event = self._event(
            document, summary, ("etf-registration",),
            companies=tuple(filter(None, (parsed["sponsor_or_adviser"], parsed["trust_name"]))),
            tickers=tuple(filter(None, (parsed["ticker_if_available"],))), quality=1.0,
        )
        return [replace(event, title=str(fund_name))]

    def healthcheck(self) -> ConnectorHealth:
        status = "disabled" if not self.enabled else ("healthy" if self.user_agent else "degraded")
        return ConnectorHealth(self.source_name, self.enabled, status, "扫描 SEC 每日表单索引：N-1A、485、497、N-CSR 和 NPORT-P")


class OpenAlexPapersConnector(PublicHttpConnector):
    source_name = "openalex"

    def __init__(self, cache_dir: Path, topics: list[str] | None = None, enabled: bool = True):
        super().__init__(cache_dir, enabled)
        self.topics = topics or ["edge AI", "AI inference", "robotics"]
        self.max_topics_per_run = int(os.getenv("OPENALEX_MAX_TOPICS_PER_RUN", "1"))
        self.mailto = os.getenv("OPENALEX_MAILTO", "")
        self.api_key = os.getenv("OPENALEX_API_KEY", "")
        self.records: dict[str, dict[str, Any]] = {}

    def discover(self, since: date, until: date, cursor: str | None = None) -> list[str]:
        ids: list[str] = []
        for topic in self.topics[:self.max_topics_per_run]:
            params = {"search": topic, "filter": f"from_publication_date:{since},to_publication_date:{until}", "per-page": "30", "sort": "publication_date:desc"}
            if self.mailto: params["mailto"] = self.mailto
            if self.api_key: params["api_key"] = self.api_key
            payload = json.loads(self._request("https://api.openalex.org/works?" + urlencode(params)).decode("utf-8"))
            for record in payload.get("results", []):
                item_id = record.get("id", "")
                if item_id:
                    self.records[item_id] = record
                    ids.append(item_id)
        return list(dict.fromkeys(ids))

    def fetch(self, item_id: str) -> RawDocument:
        record = self.records[item_id]
        inverted = record.get("abstract_inverted_index") or {}
        words = sorted(((position, word) for word, positions in inverted.items() for position in positions))
        abstract = " ".join(word for _, word in words)
        author_names = ", ".join(a.get("author", {}).get("display_name", "") for a in record.get("authorships", [])[:8])
        text = f"{record.get('title', '')}\n{abstract}\nAuthors: {author_names}\nCitations: {record.get('cited_by_count', 0)}"
        return RawDocument(self.source_name, record.get("doi") or item_id, record.get("title") or "OpenAlex work", text, "academic", published_at=record.get("publication_date"), access_note="OpenAlex public API")

    def normalize(self, document: RawDocument) -> list[NormalizedEvent]:
        return [self._event(document, document.text, _themes(document.text), quality=0.85)]

    def healthcheck(self) -> ConnectorHealth:
        note = "OpenAlex 论文检索；API Key 和联系邮箱可改善服务识别" if self.enabled else "已通过配置关闭"
        return ConnectorHealth(self.source_name, self.enabled, "healthy" if self.enabled else "disabled", note)


class PatentsViewConnector(PublicHttpConnector):
    source_name = "patentsview"

    def __init__(self, cache_dir: Path, topics: list[str] | None = None, enabled: bool = True):
        self.api_key = os.getenv("PATENTSVIEW_API_KEY", "")
        super().__init__(cache_dir, enabled and bool(self.api_key))
        self.configured = enabled
        self.topics = topics or ["edge artificial intelligence", "AI inference", "robotics"]
        self.records: dict[str, dict[str, Any]] = {}

    def discover(self, since: date, until: date, cursor: str | None = None) -> list[str]:
        ids: list[str] = []
        for topic in self.topics:
            query = {"_and": [{"_text_any": {"patent_title": topic}}, {"_gte": {"patent_date": since.isoformat()}}, {"_lte": {"patent_date": until.isoformat()}}]}
            params = urlencode({"q": json.dumps(query), "f": json.dumps(["patent_id", "patent_title", "patent_date"]), "o": json.dumps({"size": 100})})
            payload = json.loads(self._request("https://search.patentsview.org/api/v1/patent/?" + params, {"X-Api-Key": self.api_key, "Accept": "application/json"}).decode("utf-8"))
            for record in payload.get("patents", []):
                item_id = record.get("patent_id", "")
                if item_id:
                    self.records[item_id] = record
                    ids.append(item_id)
        return list(dict.fromkeys(ids))

    def fetch(self, item_id: str) -> RawDocument:
        record = self.records[item_id]
        url = f"https://patents.google.com/patent/US{item_id}"
        return RawDocument(self.source_name, url, record.get("patent_title", "Patent"), json.dumps(record), "patent", published_at=record.get("patent_date"), access_note="PatentsView public data; API key required")

    def normalize(self, document: RawDocument) -> list[NormalizedEvent]:
        return [self._event(document, document.title, _themes(document.title), quality=0.90)]

    def healthcheck(self) -> ConnectorHealth:
        if not self.configured: return ConnectorHealth(self.source_name, False, "disabled", "已通过配置关闭")
        if not self.api_key: return ConnectorHealth(self.source_name, False, "degraded", "旧 PatentsView 已迁移到 USPTO ODP；仍保留 Google Patents 公开发现")
        return ConnectorHealth(self.source_name, True, "healthy", "PatentSearch API，每分钟最多 45 次请求")


class PublicJobBoardsConnector(PublicHttpConnector):
    source_name = "public_job_boards"

    def __init__(self, cache_dir: Path, boards: list[dict[str, Any]] | None = None, enabled: bool = True):
        super().__init__(cache_dir, enabled)
        self.boards = boards if boards is not None else _json_env("JOB_BOARDS_JSON")
        self.max_boards_per_run = int(os.getenv("JOB_BOARDS_MAX_PER_RUN", "6"))
        self.records: dict[str, dict[str, Any]] = {}
        self.discovery_errors: list[str] = []

    @staticmethod
    def _url(board: dict[str, Any]) -> str:
        provider, token = board["provider"].lower(), board["board"]
        if provider == "greenhouse": return f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
        if provider == "lever": return f"https://api.lever.co/v0/postings/{token}?mode=json"
        if provider == "ashby": return f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"
        if provider == "career_page": return str(board["url"])
        raise ValueError(f"Unsupported public job-board provider: {provider}")

    def discover(self, since: date, until: date, cursor: str | None = None) -> list[str]:
        ids: list[str] = []
        self.discovery_errors = []
        start = until.toordinal() % len(self.boards) if self.boards else 0
        rotating = (self.boards[start:] + self.boards[:start])[:self.max_boards_per_run]
        for board in rotating:
            provider = board["provider"].lower(); company = board["company"]
            try:
                payload_bytes = self._request(self._url(board), {"Accept": "application/json,text/html"})
            except Exception as exc:
                self.discovery_errors.append(f"{company}: {exc}")
                continue
            if provider == "career_page":
                item_id = f"career_page:{company}:{sha256(payload_bytes).hexdigest()[:16]}"
                self.records[item_id] = {"company": company, "provider": provider, "url": self._url(board), "text": payload_bytes.decode("utf-8", "replace")}
                ids.append(item_id)
                continue
            try:
                payload = json.loads(payload_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self.discovery_errors.append(f"{company}: invalid JSON ({exc})")
                continue
            jobs = payload.get("jobs", payload) if isinstance(payload, dict) else payload
            for job in jobs:
                job_id = str(job.get("id") or job.get("jobUrl") or job.get("applyUrl") or job.get("hostedUrl", ""))
                if not job_id: continue
                item_id = f"{provider}:{company}:{job_id}"
                self.records[item_id] = {"company": company, "provider": provider, "job": job}
                ids.append(item_id)
        return ids

    def fetch(self, item_id: str) -> RawDocument:
        entry = self.records[item_id]
        if entry["provider"] == "career_page":
            return RawDocument(self.source_name, entry["url"], f"{entry['company']}: official careers snapshot", entry["text"], "jobs", access_note="Public official career page")
        job = entry["job"]
        title = job.get("title", "Untitled role")
        url = job.get("absolute_url") or job.get("hostedUrl") or job.get("jobUrl") or job.get("applyUrl") or ""
        text = json.dumps(job, ensure_ascii=False)
        published = job.get("updated_at") or job.get("updatedAt") or job.get("publishedAt")
        return RawDocument(self.source_name, url, f"{entry['company']}: {title}", text, "jobs", published_at=published, access_note=f"Public {entry['provider']} job-board API")

    def normalize(self, document: RawDocument) -> list[NormalizedEvent]:
        if document.access_note == "Public official career page":
            plain = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", document.text, flags=re.I | re.S)
            plain = re.sub(r"<[^>]+>", " ", plain)
            plain = re.sub(r"\s+", " ", html.unescape(plain)).strip()
            company = document.title.split(":", 1)[0]
            return [self._event(document, plain, _themes(plain), companies=(company,), quality=0.65)]
        return [self._event(document, document.title, _themes(document.text), quality=0.90)]

    def healthcheck(self) -> ConnectorHealth:
        return ConnectorHealth(self.source_name, self.enabled, "healthy" if self.enabled else "disabled", f"已配置 {len(self.boards)} 个公开招聘来源；每轮最多检查 {self.max_boards_per_run} 个")


class OfficialEtfHoldingsConnector(PublicHttpConnector):
    source_name = "official_etf_holdings"

    def __init__(self, cache_dir: Path, feeds: list[dict[str, Any]] | None = None, enabled: bool = True):
        super().__init__(cache_dir, enabled)
        self.cache_ttl_seconds = int(os.getenv("ETF_HOLDINGS_CACHE_TTL_SECONDS", "21600"))
        self.feeds = feeds if feeds is not None else _json_env("ETF_HOLDINGS_FEEDS_JSON")
        self.max_feeds_per_run = int(os.getenv("ETF_HOLDINGS_MAX_FEEDS_PER_RUN", "6"))
        self.records: dict[str, dict[str, Any]] = {}

    def discover(self, since: date, until: date, cursor: str | None = None) -> list[str]:
        start = until.toordinal() % len(self.feeds) if self.feeds else 0
        rotating = (self.feeds[start:] + self.feeds[:start])[:self.max_feeds_per_run]
        return [str(feed["url"]) for feed in rotating]

    def fetch(self, item_id: str) -> RawDocument:
        feed = next(item for item in self.feeds if item["url"] == item_id)
        text = self._request(item_id).decode("utf-8-sig", "replace")
        self.records[item_id] = feed
        return RawDocument(self.source_name, item_id, f"{feed['ticker']} official holdings", text, "etf", access_note="Issuer/sponsor official holdings feed")

    def normalize(self, document: RawDocument) -> list[NormalizedEvent]:
        feed = self.records[document.source_url]
        if feed.get("format") == "html":
            plain = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", document.text, flags=re.I | re.S)
            plain = re.sub(r"<[^>]+>", " ", plain)
            plain = re.sub(r"\s+", " ", html.unescape(plain)).strip()
            marker = plain.casefold().find("holdings")
            summary = plain[max(0, marker - 120):marker + 2200] if marker >= 0 else plain[:2200]
            return [self._event(document, summary, ("etf-holdings",), tickers=(feed["ticker"],), quality=0.70)]
        lines = document.text.splitlines()
        header_index = next((index for index, line in enumerate(lines) if ("Ticker" in line or "Symbol" in line) and ("Name" in line or "Security" in line)), 0)
        reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
        events: list[NormalizedEvent] = []
        for row in list(reader)[:500]:
            company = row.get("Name") or row.get("Company") or row.get("Security Name") or ""
            ticker = row.get("Ticker") or row.get("Symbol") or ""
            weight = row.get("Weight (%)") or row.get("Weight") or row.get("% Weight") or row.get("Market Value") or "unknown"
            if not company and not ticker: continue
            text = f"{feed['ticker']} holding: {company} {ticker}; reported weight/value: {weight}"
            event = self._event(document, text, ("etf-holdings",), companies=(company,) if company else (), tickers=(ticker,) if ticker else (), quality=0.95)
            events.append(NormalizedEvent(event_id=sha256((event.event_id + company + ticker).encode()).hexdigest()[:24], **{key: value for key, value in event.__dict__.items() if key != "event_id"}))
        return events or [self._event(document, "Holdings feed parsed with no recognised rows; map its column names before relying on it.", ("etf-holdings",), quality=0.50)]

    def healthcheck(self) -> ConnectorHealth:
        return ConnectorHealth(self.source_name, self.enabled, "healthy" if self.enabled else "disabled", f"已配置 {len(self.feeds)} 个发行人官方持仓来源；每轮最多检查 {self.max_feeds_per_run} 个")


class SpGlobalDjiConnector(PublicHttpConnector):
    """Reads S&P DJI's public RSS feeds; licensed ETF Intelligence data is out of scope."""

    source_name = "sp_global_dji"

    def __init__(self, cache_dir: Path, feeds: list[str] | None = None, enabled: bool = True):
        super().__init__(cache_dir, enabled)
        self.feeds = feeds if feeds is not None else _json_env("SP_GLOBAL_RSS_FEEDS_JSON")
        self.records: dict[str, dict[str, Any]] = {}
        self.discovery_errors: list[str] = []
        self.cache_ttl_seconds = int(os.getenv("SP_GLOBAL_CACHE_TTL_SECONDS", "300"))

    def _rss(self, url: str) -> bytes:
        target = self.cache_dir / sha256(url.encode("utf-8")).hexdigest()
        if target.exists() and time.time() - target.stat().st_mtime > self.cache_ttl_seconds:
            target.unlink()
        return self._request(url, {"Accept": "application/rss+xml,application/xml;q=0.9,text/xml;q=0.8"})

    def discover(self, since: date, until: date, cursor: str | None = None) -> list[str]:
        self.records = {}
        self.discovery_errors = []
        ids: list[str] = []
        for url in self.feeds:
            try:
                root = ET.fromstring(self._rss(url))
            except Exception as exc:
                self.discovery_errors.append(f"{url}: {exc}")
                continue
            channel_title = root.findtext("./channel/title", "S&P Dow Jones Indices")
            for item in root.findall("./channel/item"):
                title = (item.findtext("title") or "S&P DJI update").strip()
                link = (item.findtext("link") or "").strip()
                guid = (item.findtext("guid") or link or title).strip()
                published_text = (item.findtext("pubDate") or "").strip()
                published = None
                if published_text:
                    try:
                        published = parsedate_to_datetime(published_text)
                    except (TypeError, ValueError):
                        published = None
                if published and not (since <= published.date() <= until):
                    continue
                item_id = sha256(guid.encode("utf-8")).hexdigest()[:24]
                self.records[item_id] = {
                    "title": title,
                    "link": link or url,
                    "description": (item.findtext("description") or "").strip(),
                    "published_at": published.isoformat() if published else None,
                    "categories": [node.text.strip() for node in item.findall("category") if node.text and node.text.strip()],
                    "feed": channel_title,
                }
                ids.append(item_id)
        return list(dict.fromkeys(ids))

    def fetch(self, item_id: str) -> RawDocument:
        item = self.records[item_id]
        description = re.sub(r"<[^>]+>", " ", html.unescape(item["description"]))
        text = re.sub(r"\s+", " ", description).strip()
        categories = ", ".join(item["categories"])
        body = f"{text}\nCategories: {categories}\nFeed: {item['feed']}".strip()
        return RawDocument(
            self.source_name, item["link"], item["title"], body, "official",
            published_at=item["published_at"], access_note="S&P DJI public RSS; redistribution may be withdrawn by the publisher",
        )

    def normalize(self, document: RawDocument) -> list[NormalizedEvent]:
        text = f"{document.title}\n{document.text}"
        return [self._event(document, text, _themes(text), quality=0.90)]

    def healthcheck(self) -> ConnectorHealth:
        if not self.enabled:
            note = f"已预配置 {len(self.feeds)} 个 S&P DJI 公开 feed；后台访问返回 403，默认关闭并等待官方 API/授权；不含付费 ETF Intelligence 数据"
            return ConnectorHealth(self.source_name, False, "disabled", note)
        note = f"S&P DJI 公开 RSS：指数公告、发布、方法论、研究与表现报告；已配置 {len(self.feeds)} 个 feed；不含付费 ETF Intelligence 数据"
        return ConnectorHealth(self.source_name, True, "healthy" if self.feeds else "degraded", note)


class YahooEtfNewsConnector(PublicHttpConnector):
    """Discovers public ETF news metadata through yfinance for personal research."""

    source_name = "yahoo_etf_news"

    def __init__(self, cache_dir: Path, funds: list[dict[str, str]] | None = None, enabled: bool = True):
        super().__init__(cache_dir, enabled)
        self.funds = funds or []
        self.max_tickers_per_run = int(os.getenv("YAHOO_ETF_NEWS_MAX_TICKERS_PER_RUN", "4"))
        self.max_news_per_ticker = int(os.getenv("YAHOO_ETF_NEWS_MAX_ITEMS_PER_TICKER", "8"))
        self.cache_ttl_seconds = int(os.getenv("YAHOO_ETF_NEWS_CACHE_TTL_SECONDS", "1800"))
        self.records: dict[str, dict[str, Any]] = {}
        self.discovery_errors: list[str] = []

    @staticmethod
    def _published_at(content: dict[str, Any]) -> datetime | None:
        value = content.get("pubDate") or content.get("providerPublishTime")
        try:
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(value, tz=timezone.utc)
            if isinstance(value, str) and value:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (OSError, TypeError, ValueError):
            pass
        return None

    @staticmethod
    def _url(content: dict[str, Any]) -> str:
        for key in ("canonicalUrl", "clickThroughUrl"):
            value = content.get(key)
            if isinstance(value, dict) and str(value.get("url", "")).startswith(("http://", "https://")):
                return str(value["url"])
        value = content.get("link")
        return str(value) if str(value).startswith(("http://", "https://")) else ""

    def discover(self, since: date, until: date, cursor: str | None = None) -> list[str]:
        if not self.enabled:
            raise RuntimeError("yahoo_etf_news connector is disabled")
        import yfinance as yf

        self.records = {}
        self.discovery_errors = []
        start = until.toordinal() % len(self.funds) if self.funds else 0
        selected = (self.funds[start:] + self.funds[:start])[:self.max_tickers_per_run]
        for fund in selected:
            ticker = str(fund.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            cache_file = self.cache_dir / sha256(f"news:{ticker}".encode("utf-8")).hexdigest()
            try:
                if cache_file.exists() and time.time() - cache_file.stat().st_mtime <= self.cache_ttl_seconds:
                    self.cache_hits += 1
                    items = json.loads(cache_file.read_text(encoding="utf-8"))
                else:
                    self.cache_misses += 1
                    items = yf.Ticker(ticker).get_news(count=self.max_news_per_ticker, tab="news")
                    cache_file.write_text(json.dumps(items or [], ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                self.discovery_errors.append(f"{ticker}: {exc}")
                continue
            for item in items or []:
                content = item.get("content", item) if isinstance(item, dict) else {}
                if not isinstance(content, dict):
                    continue
                published = self._published_at(content)
                if published and not (since <= published.date() <= until):
                    continue
                url = self._url(content)
                title = str(content.get("title", "")).strip()
                if not url or not title:
                    continue
                item_id = sha256(url.encode("utf-8")).hexdigest()[:24]
                provider = content.get("provider") or {}
                record = self.records.setdefault(item_id, {
                    "url": url,
                    "title": title,
                    "summary": str(content.get("summary") or content.get("description") or "").strip(),
                    "publisher": str(provider.get("displayName", "Yahoo Finance")) if isinstance(provider, dict) else "Yahoo Finance",
                    "published_at": published.isoformat() if published else None,
                    "tickers": [],
                })
                if ticker not in record["tickers"]:
                    record["tickers"].append(ticker)
        return list(self.records)

    def fetch(self, item_id: str) -> RawDocument:
        item = self.records[item_id]
        text = f"Publisher: {item['publisher']}\nRelated ETFs: {', '.join(item['tickers'])}\n{item['summary']}".strip()
        return RawDocument(
            self.source_name,
            item["url"],
            item["title"],
            text,
            "social",
            published_at=item["published_at"],
            access_note="Yahoo Finance public news metadata via yfinance; personal research; secondary discovery only",
        )

    def normalize(self, document: RawDocument) -> list[NormalizedEvent]:
        item = next(value for value in self.records.values() if value["url"] == document.source_url)
        return [self._event(document, document.text, _themes(f"{document.title} {document.text}"), tickers=tuple(item["tickers"]), quality=0.45)]

    def healthcheck(self) -> ConnectorHealth:
        import importlib.util

        installed = importlib.util.find_spec("yfinance") is not None
        status = "healthy" if self.enabled and installed else ("disabled" if not self.enabled else "degraded")
        return ConnectorHealth(
            self.source_name,
            self.enabled,
            status,
            f"Yahoo Finance ETF 资讯发现；已配置 {len(self.funds)} 只 ETF；每轮最多检查 {self.max_tickers_per_run} 只；仅限个人研究并需交叉确认",
        )


class AnySearchDiscoveryConnector(PublicHttpConnector):
    """Optional public discovery layer; results must be corroborated by primary sources."""
    source_name = "anysearch_discovery"

    def __init__(self, cache_dir: Path, queries: list[str] | None = None, enabled: bool = True, skill_dir: Path | None = None):
        super().__init__(cache_dir, enabled)
        self.queries = queries or _json_env("ANYSEARCH_QUERIES_JSON") or ["new AI infrastructure product launch", "new ETF registration", "AI semiconductor hiring"]
        self.x_watchlist = [str(item).lstrip("@") for item in _json_env("X_WATCHLIST_JSON")]
        self.max_queries_per_run = int(os.getenv("ANYSEARCH_MAX_QUERIES_PER_RUN", "5"))
        self.command_timeout_seconds = int(os.getenv("ANYSEARCH_COMMAND_TIMEOUT_SECONDS", "15"))
        self.skill_dir = skill_dir or Path(os.getenv("ANYSEARCH_SKILL_DIR", "skills/anysearch"))
        self.records: dict[str, dict[str, str]] = {}

    def discover(self, since: date, until: date, cursor: str | None = None) -> list[str]:
        script = self.skill_dir / "scripts" / "anysearch_cli.js"
        if not script.exists(): raise RuntimeError("AnySearch skill is not installed at ANYSEARCH_SKILL_DIR")
        ids: list[str] = []
        generic_budget = min(2, self.max_queries_per_run, len(self.queries))
        query_start = until.toordinal() % len(self.queries) if self.queries else 0
        rotating_queries = (self.queries[query_start:] + self.queries[:query_start])[:generic_budget]
        commands = [(["search", query, "--max_results", "10"], query) for query in rotating_queries]
        watch_budget = max(0, self.max_queries_per_run - generic_budget)
        start = until.toordinal() % len(self.x_watchlist) if self.x_watchlist else 0
        rotating_watchlist = (self.x_watchlist[start:] + self.x_watchlist[:start])[:watch_budget]
        commands.extend(([
            "search", handle, "--domain", "social_media", "--sub_domain", "social_media.social_media",
            "--sdp", f"type=x_latest,keyword={handle}", "--max_results", "10",
        ], f"X @{handle}") for handle in rotating_watchlist)
        for arguments, query in commands:
            try:
                completed = subprocess.run(
                    ["node", str(script), *arguments], check=True, capture_output=True,
                    text=True, encoding="utf-8", errors="replace", timeout=self.command_timeout_seconds,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                continue
            # The local AnySearch CLI emits Markdown headings followed by a
            # URL field, rather than Markdown links in the heading.
            pattern = r"### \d+\. (.*?)\n- \*\*URL\*\*: (https?://\S+)\n- (.*?)(?=\n###|\Z)"
            for title, url, snippet in re.findall(pattern, completed.stdout or "", re.S):
                item_id = sha256(url.encode()).hexdigest()[:24]
                self.records[item_id] = {"title": title, "url": url, "snippet": f"发现查询：{query}\n" + re.sub(r"\s+", " ", snippet)}
                ids.append(item_id)
        return list(dict.fromkeys(ids))

    def fetch(self, item_id: str) -> RawDocument:
        item = self.records[item_id]
        return RawDocument(self.source_name, item["url"], item["title"], item["snippet"], "social", access_note="AnySearch public discovery result; corroboration required")

    def normalize(self, document: RawDocument) -> list[NormalizedEvent]:
        return [self._event(document, document.text, _themes(document.text), quality=0.35)]

    def healthcheck(self) -> ConnectorHealth:
        present = (self.skill_dir / "scripts" / "anysearch_cli.js").exists()
        status = "healthy" if self.enabled and present else ("disabled" if not self.enabled else "degraded")
        return ConnectorHealth(self.source_name, self.enabled, status, f"可选公开信息发现；已配置 {len(self.x_watchlist)} 个 X 账号；每轮最多 {self.max_queries_per_run} 个查询；结果需要交叉验证")


class GooglePatentsDiscoveryConnector(AnySearchDiscoveryConnector):
    """Find public Google Patents records through the installed search skill."""

    source_name = "google_patents"

    def __init__(self, cache_dir: Path, queries: list[str] | None = None, enabled: bool = True, skill_dir: Path | None = None):
        configured_queries = queries or _json_env("GOOGLE_PATENTS_QUERIES_JSON") or [
            "site:patents.google.com/patent artificial intelligence accelerator",
            "site:patents.google.com/patent robotics semiconductor",
        ]
        super().__init__(cache_dir, queries=[str(item) for item in configured_queries], enabled=enabled, skill_dir=skill_dir)
        self.x_watchlist = []

    def discover(self, since: date, until: date, cursor: str | None = None) -> list[str]:
        ids = super().discover(since, until, cursor)
        return [
            item_id for item_id in ids
            if urlparse(self.records[item_id]["url"]).netloc.lower().removeprefix("www.") == "patents.google.com"
        ]

    def fetch(self, item_id: str) -> RawDocument:
        item = self.records[item_id]
        return RawDocument(
            self.source_name,
            item["url"],
            item["title"],
            item["snippet"],
            "patent",
            access_note="Google Patents public discovery result; verify against the linked patent record",
        )

    def healthcheck(self) -> ConnectorHealth:
        present = (self.skill_dir / "scripts" / "anysearch_cli.js").exists()
        status = "healthy" if self.enabled and present else ("disabled" if not self.enabled else "degraded")
        return ConnectorHealth(
            self.source_name,
            self.enabled,
            status,
            f"Google Patents 公开发现；已配置 {len(self.queries)} 个查询；结果作为专利线索并保留原始链接",
        )
