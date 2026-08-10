"""Auditable ETF preview snapshots sourced from public Tiantian Fund pages."""
from __future__ import annotations

import hashlib
import html
import json
import math
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo

from .models import utcnow


CONFIG_PATH = Path("config/etf-preview.json")
CATEGORY_LABELS = {"sp500": "标普500", "exchange": "场内ETF", "active": "美股主动"}


def load_preview_config(path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class _TextAndTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        value = html.unescape(data).strip()
        if value:
            self.text.append(value)
            if self._cell is not None:
                self._cell.append(value)


def html_payload(source: str) -> tuple[str, list[list[str]]]:
    parser = _TextAndTableParser()
    parser.feed(source)
    return " ".join(parser.text), parser.rows


def parse_fund_catalog(source: str) -> list[dict[str, str]]:
    payload = source.lstrip("\ufeff").strip()
    payload = re.sub(r"^\s*var\s+r\s*=\s*", "", payload)
    payload = payload.rstrip("; \r\n")
    rows = json.loads(payload)
    return [
        {"code": str(row[0]), "pinyin": str(row[1]), "name": str(row[2]), "fund_type": str(row[3])}
        for row in rows if isinstance(row, list) and len(row) >= 4
    ]


def _js_value(source: str, name: str, fallback: Any = None) -> Any:
    match = re.search(rf"\bvar\s+{re.escape(name)}\s*=\s*(.*?);", source, re.S)
    if not match:
        return fallback
    raw = match.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        if len(raw) >= 2 and raw[0] == raw[-1] == '"':
            return raw[1:-1]
        return fallback


def _date_from_millis(value: int | float) -> str:
    return datetime.fromtimestamp(float(value) / 1000, tz=ZoneInfo("Asia/Shanghai")).date().isoformat()


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _return_between(
    series: list[tuple[str, float]], start_date: str, end_date: str, *,
    require_prior: bool, include_start_as_base: bool = False,
) -> float | None:
    before = [(day, value) for day, value in series if day <= start_date] if include_start_as_base else [(day, value) for day, value in series if day < start_date]
    within = [(day, value) for day, value in series if start_date <= day <= end_date]
    if not within or (require_prior and not before):
        return None
    start_value = before[-1][1] if before else within[0][1]
    end_value = within[-1][1]
    if not start_value:
        return None
    return round((end_value / start_value - 1) * 100, 2)


def parse_trend_script(source: str) -> dict[str, Any]:
    net = _js_value(source, "Data_netWorthTrend", []) or []
    adjusted = _js_value(source, "Data_ACWorthTrend", []) or []
    adjusted_series = [
        (_date_from_millis(row[0]), float(row[1]))
        for row in adjusted if isinstance(row, list) and len(row) >= 2 and _number(row[1]) is not None
    ]
    adjusted_series.sort(key=lambda row: row[0])
    latest_date = adjusted_series[-1][0] if adjusted_series else ""
    rolling_start = ""
    rolling_return = None
    if latest_date:
        rolling_start = (datetime.fromisoformat(latest_date) - timedelta(days=365)).date().isoformat()
        rolling_return = _return_between(
            adjusted_series, rolling_start, latest_date,
            require_prior=True, include_start_as_base=True,
        )
    latest_net = net[-1] if net else {}
    scale = _js_value(source, "Data_assetAllocation", {}) or {}
    scale_value = None
    scale_date = ""
    categories = scale.get("categories") or [] if isinstance(scale, dict) else []
    for item in scale.get("series", []) if isinstance(scale, dict) else []:
        if str(item.get("name") or "") == "净资产" and item.get("data"):
            scale_value = _number(item["data"][-1])
            scale_date = str(categories[-1]) if categories else ""
            break
    return {
        "latest_nav_date": latest_date or (_date_from_millis(latest_net["x"]) if latest_net.get("x") else ""),
        "return_2025": _return_between(adjusted_series, "2025-01-01", "2025-12-31", require_prior=True),
        "rolling_1y": rolling_return,
        "rolling_start": rolling_start,
        "yesterday_return": _number(latest_net.get("equityReturn")),
        "latest_unit_nav": _number(latest_net.get("y")),
        "scale_billion": scale_value,
        "scale_date": scale_date,
        "return_source": "复权累计净值" if adjusted_series else "未核验",
    }


def parse_profile_page(source: str) -> dict[str, Any]:
    text, _ = html_payload(source)
    management = re.search(r"管理费率\s*([0-9.]+)%", text)
    custody = re.search(r"托管费率\s*([0-9.]+)%", text)
    target = re.search(r"跟踪标的\s*([^◆]{2,80}?)(?:投资目标|业绩比较基准|风险收益特征|$)", text)
    management_fee = _number(management.group(1)) if management else None
    custody_fee = _number(custody.group(1)) if custody else None
    return {
        "management_fee": management_fee,
        "custody_fee": custody_fee,
        "operating_fee": round(management_fee + custody_fee, 4) if management_fee is not None and custody_fee is not None else None,
        "tracking_index": re.sub(r"\s+", " ", target.group(1)).strip(" ：:") if target else "未核验",
        "profile_text": text,
    }


def parse_tracking_page(source: str) -> dict[str, Any]:
    text, _ = html_payload(source)
    segment = text[text.find("指数基金指标"):]
    match = re.search(r"年化跟踪误差\s*同类平均跟踪误差\s*[^%]{0,120}?([0-9.]+)%", segment)
    as_of = re.search(r"截止至[：:]?\s*(20\d{2}-\d{2}-\d{2})", segment)
    return {"tracking_error": _number(match.group(1)) if match else None, "tracking_error_date": as_of.group(1) if as_of else ""}


def parse_purchase_page(source: str) -> dict[str, Any]:
    text, _ = html_payload(source)
    status_match = re.search(r"交易状态[：:]\s*(开放申购|限大额|暂停申购|封闭期|场内交易)", text)
    limit_match = re.search(r"单日累计购买上限\s*([0-9,.]+)\s*(万元|元)", text)
    status = status_match.group(1) if status_match else "未核验"
    daily_limit = None
    if limit_match:
        daily_limit = float(limit_match.group(1).replace(",", "")) * (10000 if limit_match.group(2) == "万元" else 1)
    elif status == "开放申购":
        daily_limit = "不限"
    return {"purchase_status": status, "daily_limit_yuan": daily_limit}


def parse_holdings_page(source: str) -> dict[str, Any]:
    """Parse the newest disclosed top-ten holdings block from Tiantian Fund."""
    decoded = html.unescape(source.replace(r'\"', '"'))
    date_match = re.search(r"截止至：?\s*<font[^>]*>\s*(20\d{2}-\d{2}-\d{2})", decoded)
    table_match = re.search(r"<tbody>(.*?)</tbody>", decoded, re.S | re.I)
    rows: list[dict[str, Any]] = []
    if table_match:
        for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), re.S | re.I):
            quote = re.search(r"quote\.eastmoney\.com/unify/r/(\d+)\.([^'\"/?<]+)", row_html, re.I)
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S | re.I)
            if not quote or len(cells) < 5:
                continue
            cell_text = [re.sub(r"\s+", " ", html_payload(cell)[0]).strip() for cell in cells]
            weight_match = re.search(r"([0-9.]+)%", cell_text[4])
            weight = _number(weight_match.group(1)) if weight_match else None
            rows.append({
                "market": quote.group(1),
                "ticker": quote.group(2),
                "name": cell_text[2] if len(cell_text) > 2 else "",
                "weight": weight,
                "is_us": quote.group(1) in {"105", "106"},
            })
    total_weight = round(sum(float(row["weight"]) for row in rows if row["weight"] is not None), 4)
    us_weight = round(sum(float(row["weight"]) for row in rows if row["is_us"] and row["weight"] is not None), 4)
    us_count = sum(bool(row["is_us"]) for row in rows)
    return {
        "holdings_as_of": date_match.group(1) if date_match else "",
        "top_holdings_count": len(rows),
        "top_holdings_weight": total_weight,
        "us_top_holdings_count": us_count,
        "us_top_holdings_weight": us_weight,
        "us_top_holdings_share": round(us_weight / total_weight, 4) if total_weight else None,
        "top_holdings": rows,
    }


def parse_market_table(source: str) -> tuple[str, dict[str, dict[str, Any]]]:
    text, rows = html_payload(source)
    date_match = re.search(r"数据日期\s*(20\d{2}-\d{2}-\d{2})", text)
    market_date = date_match.group(1) if date_match else ""
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        code_index = next((index for index, cell in enumerate(row) if re.fullmatch(r"\d{6}", cell)), None)
        if code_index is None or len(row) < code_index + 11:
            continue
        current_nav = _number(row[code_index + 3])
        price = _number(row[code_index + 9])
        premium = round((price / current_nav - 1) * 100, 2) if current_nav and price else None
        result[row[code_index]] = {
            "market_date": market_date,
            "market_price": price,
            "same_day_nav": current_nav,
            "premium_rate": premium,
        }
    return market_date, result


def parse_quote_history(source: str, window: int = 20) -> dict[str, Any]:
    payload = json.loads(source)
    rows = ((payload.get("data") or {}).get("klines") or [])[-window:]
    amounts: list[float] = []
    dates: list[str] = []
    closes_by_date: dict[str, float] = {}
    for raw in rows:
        fields = str(raw).split(",")
        if len(fields) > 6 and _number(fields[6]) is not None:
            dates.append(fields[0])
            amounts.append(float(fields[6]))
            if _number(fields[2]) is not None:
                closes_by_date[fields[0]] = float(fields[2])
    return {
        "average_turnover_billion_20d": round(sum(amounts) / len(amounts) / 100_000_000, 4) if amounts else None,
        "turnover_sample_days": len(amounts),
        "turnover_as_of": dates[-1] if dates else "",
        "closes_by_date": closes_by_date,
    }


def _base_name(name: str) -> str:
    value = re.sub(r"[（(]QDII[^）)]*[）)]", "", name, flags=re.I)
    value = re.sub(r"[（(]?(?:人民币(?:份额)?|美元(?:现汇|现钞|汇|钞)?|美钞|港币)[）)]?", "", value)
    value = re.sub(r"[（(]\s*[）)]", "", value)
    value = re.sub(r"(?:A|C|D|E|F|I)$", "", value, flags=re.I)
    return re.sub(r"\s+", "", value).casefold()


def _share_class(name: str) -> str:
    normalized = re.sub(r"[（(]?(?:人民币(?:份额)?|美元(?:现汇|现钞|汇|钞)?|美钞|港币)[）)]?", "", name)
    normalized = re.sub(r"[（(]QDII[^）)]*[）)]", "", normalized, flags=re.I)
    normalized = re.sub(r"[（(]\s*[）)]", "", normalized)
    match = re.search(r"([ACDEFI])$", normalized, re.I)
    return match.group(1).upper() if match else ""


def discover_preview_funds(catalog: list[dict[str, str]], config: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    rules = config["classification"]
    overrides = config.get("manual_overrides") or {}
    excluded = set(overrides.get("exclude_codes") or [])
    category_by_code = overrides.get("category_by_code") or {}
    exchange_prefixes = tuple(rules["exchange_code_prefixes"])
    excluded_terms = tuple(rules["excluded_share_terms"])
    groups: dict[str, list[dict[str, str]]] = {}
    for fund in catalog:
        groups.setdefault(_base_name(fund["name"]), []).append(fund)
    discovered = {key: [] for key in CATEGORY_LABELS}
    seen: set[str] = set()
    for fund in catalog + list(overrides.get("include") or []):
        code, name, fund_type = fund["code"], fund["name"], fund.get("fund_type", "")
        if code in excluded or code in seen or any(term in name for term in excluded_terms):
            continue
        is_exchange = code.startswith(exchange_prefixes) and "ETF" in name.upper() and "联接" not in name
        category = category_by_code.get(code)
        if not category and is_exchange and any(term in name for term in rules["exchange_us_terms"]):
            category = "exchange"
        elif not category and not is_exchange and any(term in name for term in rules["sp500_terms"]):
            category = "sp500"
        elif (
            not category
            and fund_type in set(rules["active_equity_types"])
            and "指数" not in fund_type
            and "ETF" not in name.upper()
            and any(term in name for term in rules["active_us_candidate_terms"])
            and not any(term in name for term in rules["active_excluded_region_terms"])
        ):
            category = "active"
        if category not in discovered:
            continue
        if category != "exchange" and _share_class(name) in {"C", "D", "E", "F", "I"}:
            continue
        item = dict(fund)
        if category != "exchange":
            paired = overrides.get("c_share_by_a_code", {}).get(code)
            if not paired:
                paired_item = next((row for row in groups.get(_base_name(name), []) if _share_class(row["name"]) == "C"), None)
                paired = paired_item["code"] if paired_item else ""
            item["c_code"] = paired
        item["category"] = category
        discovered[category].append(item)
        seen.add(code)
    for values in discovered.values():
        values.sort(key=lambda row: row["code"])
    return discovered


@dataclass
class CachedHttpClient:
    cache_dir: Path
    timeout_seconds: float
    throttle_seconds: float
    user_agent: str
    dynamic_ttl: int
    profile_ttl: int
    cancelled: Callable[[], bool] | None = None

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_request = 0.0

    def __call__(self, url: str) -> str:
        if self.cancelled and self.cancelled():
            raise RuntimeError("用户取消同步")
        path = self.cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
        cached: dict[str, Any] = {}
        if path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cached = {}
        ttl = self.profile_ttl if "jbgk_" in url or "fundcode_search" in url else self.dynamic_ttl
        if cached and time.time() - float(cached.get("fetched_at", 0)) <= ttl and cached.get("text"):
            return str(cached["text"])
        delay = self.throttle_seconds - (time.monotonic() - self._last_request)
        if delay > 0:
            time.sleep(delay)
        try:
            headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}
            if "FundArchivesDatas.aspx" in url:
                code_match = re.search(r"[?&]code=(\d{6})", url)
                headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/127 Safari/537.36",
                    "Referer": f"https://fundf10.eastmoney.com/ccmx_{code_match.group(1)}.html" if code_match else "https://fundf10.eastmoney.com/",
                })
            request = Request(url, headers=headers)
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - fixed public hosts come from config
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace").lstrip("\ufeff")
            if not text.strip():
                raise ValueError("公开页面返回空内容")
            envelope = {"url": url, "fetched_at": time.time(), "text": text}
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
            self._last_request = time.monotonic()
            return text
        except Exception:
            if cached.get("text"):
                return str(cached["text"])
            raise


def _market_number(code: str) -> str:
    return "1" if code.startswith(("5", "6", "9")) else "0"


def _enrich_share(fund: dict[str, str], config: dict[str, Any], fetch: Callable[[str], str]) -> dict[str, Any]:
    code = fund["code"]
    urls = {
        "fund": config["fund_page_template"].format(code=code),
        "profile": config["profile_template"].format(code=code),
        "trend": config["trend_template"].format(code=code),
    }
    trend = parse_trend_script(fetch(urls["trend"]))
    profile = parse_profile_page(fetch(urls["profile"]))
    purchase = parse_purchase_page(fetch(urls["fund"]))
    return {**fund, **trend, **profile, **purchase, "source_url": urls["fund"], "source_urls": list(urls.values())}


def collect_etf_preview_snapshot(
    config: dict[str, Any] | None = None,
    *,
    fetcher: Callable[[str], str] | None = None,
    cache_dir: str | Path = "data/cache/tiantian-etf-preview",
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    config = config or load_preview_config()
    network = config["network"]
    fetch = fetcher or CachedHttpClient(
        Path(cache_dir), float(network["timeout_seconds"]), float(network["throttle_seconds"]),
        str(network["user_agent"]), int(network["dynamic_cache_ttl_seconds"]), int(network["profile_cache_ttl_seconds"]), cancelled,
    )
    errors: list[dict[str, str]] = []
    catalog = parse_fund_catalog(fetch(config["catalog_url"]))
    discovered = discover_preview_funds(catalog, config)
    try:
        market_date, market_rows = parse_market_table(fetch(config["market_table_url"]))
    except Exception as exc:
        market_date, market_rows = "", {}
        errors.append({"scope": "market_table", "error": str(exc)})
    products: dict[str, list[dict[str, Any]]] = {key: [] for key in CATEGORY_LABELS}
    for category, funds in discovered.items():
        for fund in funds:
            if cancelled and cancelled():
                raise RuntimeError("用户取消同步")
            try:
                item = _enrich_share(fund, config, fetch)
                if category == "active":
                    profile_text = str(item.pop("profile_text", ""))
                    profile_terms = config["classification"]["active_profile_us_terms"]
                    explicit_name = any(term in fund["name"] for term in ("美国", "美股", "纳斯达克"))
                    explicit_profile = any(term.casefold() in profile_text.casefold() for term in profile_terms)
                    explicit_us = explicit_name or explicit_profile
                    if explicit_us:
                        item["classification_evidence"] = {"method": "name_or_profile", "matched_scope": "美国主要暴露"}
                    else:
                        holdings_url = config["holdings_template"].format(
                            code=fund["code"], year=datetime.now(ZoneInfo("Asia/Shanghai")).year - 1,
                        )
                        holdings = parse_holdings_page(fetch(holdings_url))
                        min_count = int(config["classification"]["active_holdings_min_us_count"])
                        min_share = float(config["classification"]["active_holdings_min_us_share"])
                        if holdings["us_top_holdings_count"] < min_count or (holdings["us_top_holdings_share"] or 0) < min_share:
                            continue
                        item["classification_evidence"] = {
                            "method": "latest_top10_us_majority",
                            "holdings_as_of": holdings["holdings_as_of"],
                            "us_count": holdings["us_top_holdings_count"],
                            "total_count": holdings["top_holdings_count"],
                            "us_weight": holdings["us_top_holdings_weight"],
                            "total_weight": holdings["top_holdings_weight"],
                            "us_share": holdings["us_top_holdings_share"],
                        }
                        item["source_urls"].append(holdings_url)
                else:
                    item.pop("profile_text", None)
                item["category_label"] = CATEGORY_LABELS[category]
                if category == "sp500":
                    tracking_url = config["tracking_template"].format(code=fund["code"])
                    try:
                        item.update(parse_tracking_page(fetch(tracking_url)))
                        item["source_urls"].append(tracking_url)
                    except Exception as exc:
                        errors.append({"code": fund["code"], "field": "tracking_error", "error": str(exc)})
                    if fund.get("c_code"):
                        c_fund = next((row for row in catalog if row["code"] == fund["c_code"]), None)
                        if c_fund:
                            try:
                                item["c_share"] = _enrich_share(c_fund, config, fetch)
                                item["c_share"].pop("profile_text", None)
                            except Exception as exc:
                                errors.append({"code": fund["c_code"], "field": "c_share", "error": str(exc)})
                elif category == "active" and fund.get("c_code"):
                    c_fund = next((row for row in catalog if row["code"] == fund["c_code"]), None)
                    if c_fund:
                        try:
                            item["c_share"] = _enrich_share(c_fund, config, fetch)
                            item["c_share"].pop("profile_text", None)
                        except Exception as exc:
                            errors.append({"code": fund["c_code"], "field": "c_share", "error": str(exc)})
                if category == "exchange":
                    item.update(market_rows.get(fund["code"], {"market_date": market_date, "premium_rate": None}))
                    quote_url = config["quote_template"].format(market=_market_number(fund["code"]), code=fund["code"])
                    try:
                        quote = parse_quote_history(fetch(quote_url))
                        closes_by_date = quote.pop("closes_by_date", {})
                        item.update(quote)
                        nav_date = str(item.get("latest_nav_date") or "")
                        same_day_price = _number(closes_by_date.get(nav_date))
                        same_day_nav = _number(item.get("latest_unit_nav"))
                        if item.get("premium_rate") is None and same_day_price is not None and same_day_nav:
                            item.update({
                                "market_date": nav_date,
                                "market_price": same_day_price,
                                "same_day_nav": same_day_nav,
                                "premium_rate": round((same_day_price / same_day_nav - 1) * 100, 2),
                                "premium_source": "历史收盘价/同日单位净值",
                            })
                        elif item.get("premium_rate") is not None:
                            item["premium_source"] = "天天基金场内净值表"
                        item["source_urls"].append(quote_url)
                    except Exception as exc:
                        errors.append({"code": fund["code"], "field": "turnover", "error": str(exc)})
                products[category].append(item)
            except Exception as exc:
                errors.append({"code": fund["code"], "category": category, "error": str(exc)})
    all_products = [item for values in products.values() for item in values]
    active_target = int(config["classification"].get("active_target_minimum", 0))
    if len(products["active"]) < active_target:
        errors.append({
            "scope": "active_classification",
            "error": f"美股主动通过验证 {len(products['active'])} 只，低于配置目标 {active_target} 只",
        })
    as_of_values = [str(item.get("latest_nav_date") or item.get("market_date") or "") for item in all_products]
    status = "available" if all_products and not errors else "partial" if all_products else "unknown"
    return {
        "snapshot_id": str(uuid4()),
        "source": config["source_name"],
        "source_homepage": "https://1234567.com.cn/",
        "collected_at": utcnow(),
        "market_as_of": max(as_of_values, default=""),
        "status": status,
        "categories": products,
        "counts": {key: len(values) for key, values in products.items()},
        "total": len(all_products),
        "errors": errors,
        "premium_thresholds": config["premium_thresholds"],
        "methodology": {
            "operating_fee": "管理费率与托管费率之和（年化），不含申购、赎回及销售服务费",
            "return_2025": "2025自然年度复权累计净值涨幅；统计期不足显示未核验",
            "rolling_1y": "截至最新有效净值日向前一年的复权累计净值涨幅",
            "premium_rate": "同一数据日场内收盘价相对基金单位净值的溢价；净值缺失时不估算",
            "turnover": "最近20个可用交易日平均成交额",
            "active_us": "主动权益QDII中，名称/概况明确以美国为主要市场，或最新前十大持仓至少5只美股且美股占前十大披露权重不低于50%",
        },
    }


def _theme_match_text(value: Any) -> str:
    """Normalize public fund text without translating or inventing aliases."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(character for character in normalized if character.isalnum())


def match_theme_preview_products(
    snapshot: dict[str, Any] | None,
    theme_id: str,
    theme_name: str,
    aliases: list[str],
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Select theme-related products from one immutable ETF preview snapshot."""
    if not snapshot:
        return {
            "snapshot_id": "", "collected_at": "", "market_as_of": "",
            "status": "not_assessed", "products": [], "matched_count": 0,
            "limitations": ["ETF preview has not completed a successful snapshot."],
        }
    ignored = {
        "etf", "fund", "theme", "index", "equity", "stock", "qdii",
        "美股", "美国", "基金", "指数", "主题", "股票", "海外",
    }
    terms: dict[str, str] = {}
    for raw in [theme_name, theme_id, *aliases]:
        display = str(raw or "").strip()
        normalized = _theme_match_text(display)
        if len(normalized) >= 2 and normalized not in ignored:
            terms.setdefault(normalized, display)
    matches: list[dict[str, Any]] = []
    for category, products in (snapshot.get("categories") or {}).items():
        for product in products or []:
            fields = {
                "name": _theme_match_text(product.get("name")),
                "tracking_index": _theme_match_text(product.get("tracking_index")),
                "pinyin": _theme_match_text(product.get("pinyin")),
            }
            matched_fields: dict[str, list[str]] = {}
            score = 0
            for field, text in fields.items():
                found = [
                    display for normalized, display in terms.items()
                    if normalized in text and not (field == "pinyin" and normalized.isascii() and len(normalized) < 3)
                ]
                if found:
                    matched_fields[field] = found
                    score += {"name": 3, "tracking_index": 2, "pinyin": 1}[field] * len(found)
            if not matched_fields:
                continue
            matches.append({
                **{key: product.get(key) for key in (
                    "code", "c_code", "name", "fund_type", "category_label",
                    "latest_nav_date", "return_2025", "rolling_1y", "yesterday_return",
                    "scale_billion", "scale_date", "operating_fee", "tracking_index",
                    "tracking_error", "purchase_status", "daily_limit_yuan", "market_date",
                    "market_price", "same_day_nav", "premium_rate",
                    "average_turnover_billion_20d", "source_url", "source_urls",
                )},
                "category": category,
                "relevance_score": score,
                "matched_fields": matched_fields,
            })
    matches.sort(key=lambda item: (-int(item["relevance_score"]), -(float(item.get("scale_billion") or 0)), str(item.get("code") or "")))
    selected = matches[:max(1, min(limit, 50))]
    return {
        "snapshot_id": str(snapshot.get("snapshot_id") or ""),
        "source": str(snapshot.get("source") or ""),
        "collected_at": str(snapshot.get("collected_at") or ""),
        "market_as_of": str(snapshot.get("market_as_of") or ""),
        "status": "available" if selected else "insufficient_data",
        "matched_count": len(matches),
        "products": selected,
        "match_terms": list(terms.values()),
        "limitations": [
            "Products are linked by explicit deterministic name/index terms from the frozen preview snapshot; holdings-based thematic exposure is not inferred."
        ],
    }


def audit_etf_preview_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    categories = snapshot.get("categories") or {}
    fields = {
        "sp500": ["operating_fee", "scale_billion", "return_2025", "rolling_1y", "yesterday_return", "tracking_error", "daily_limit_yuan", "purchase_status"],
        "exchange": ["tracking_index", "operating_fee", "scale_billion", "return_2025", "rolling_1y", "yesterday_return", "premium_rate", "average_turnover_billion_20d"],
        "active": ["operating_fee", "scale_billion", "return_2025", "rolling_1y", "yesterday_return", "daily_limit_yuan", "purchase_status"],
    }
    coverage: dict[str, dict[str, dict[str, float | int]]] = {}
    issues: list[dict[str, str]] = []
    all_codes: list[str] = []
    for category, required in fields.items():
        items = list(categories.get(category) or [])
        all_codes.extend(str(item.get("code") or "") for item in items)
        coverage[category] = {}
        for field in required:
            available = sum(item.get(field) not in (None, "", "未核验") for item in items)
            coverage[category][field] = {
                "available": available,
                "total": len(items),
                "ratio": round(available / len(items), 4) if items else 0,
            }
        for item in items:
            code = str(item.get("code") or "")
            fee = _number(item.get("operating_fee"))
            scale = _number(item.get("scale_billion"))
            if fee is not None and not 0 <= fee <= 5:
                issues.append({"code": code, "field": "operating_fee", "issue": "费率超出0%至5%的审计范围"})
            if scale is not None and scale < 0:
                issues.append({"code": code, "field": "scale_billion", "issue": "规模为负数"})
            if not str(item.get("source_url") or "").startswith(("https://fund.eastmoney.com/", "https://fundf10.eastmoney.com/")):
                issues.append({"code": code, "field": "source_url", "issue": "来源不是允许的天天基金公开域名"})
    duplicates = sorted({code for code in all_codes if code and all_codes.count(code) > 1})
    for code in duplicates:
        issues.append({"code": code, "field": "category", "issue": "基金代码跨分类重复"})
    exchange_items = list(categories.get("exchange") or [])
    premium_values = [float(item["premium_rate"]) for item in exchange_items if _number(item.get("premium_rate")) is not None]
    thresholds = snapshot.get("premium_thresholds") or {"attention": 1, "elevated": 2, "high": 3}

    def premium_level(value: float) -> str:
        if value > float(thresholds["high"]):
            return "high"
        if value > float(thresholds["elevated"]):
            return "elevated"
        if value > float(thresholds["attention"]):
            return "attention"
        return "normal"

    risk_counts = {level: 0 for level in ("normal", "attention", "elevated", "high")}
    for value in premium_values:
        risk_counts[premium_level(value)] += 1
    return {
        "snapshot_id": snapshot.get("snapshot_id", ""),
        "status": snapshot.get("status", "unknown"),
        "counts": snapshot.get("counts") or {},
        "coverage": coverage,
        "issues": issues,
        "issue_count": len(issues),
        "source_error_count": len(snapshot.get("errors") or []),
        "premium_audit": {
            "minimum": min(premium_values) if premium_values else None,
            "maximum": max(premium_values) if premium_values else None,
            "risk_counts": risk_counts,
            "highest": [
                {
                    "code": item.get("code"), "name": item.get("name"),
                    "premium_rate": item.get("premium_rate"), "market_date": item.get("market_date"),
                    "market_price": item.get("market_price"), "same_day_nav": item.get("same_day_nav"),
                    "premium_source": item.get("premium_source", ""),
                }
                for item in sorted(exchange_items, key=lambda row: _number(row.get("premium_rate")) or -9999, reverse=True)[:5]
            ],
        },
        "category_samples": {
            category: [{"code": item.get("code"), "c_code": item.get("c_code", ""), "name": item.get("name")} for item in list(categories.get(category) or [])[:10]]
            for category in CATEGORY_LABELS
        },
    }
