"""Deterministic, auditable ETF market snapshots backed by cached Yahoo data."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _numeric_config() -> dict[str, float]:
    values: dict[str, float] = {}
    section = ""
    path = Path(__file__).parents[1] / "config" / "defaults.yaml"
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith(" ") and raw.rstrip().endswith(":"):
            section = raw.strip()[:-1]
            continue
        if section == "etf_market" and ":" in raw:
            key, value = raw.strip().split(":", 1)
            try:
                values[key] = float(value.strip())
            except ValueError:
                pass
    return values


SETTINGS = _numeric_config()


def minimum_verified_etfs() -> int:
    return max(1, int(SETTINGS.get("minimum_verified_etfs", 2)))


def load_universe() -> list[dict[str, Any]]:
    path = Path(__file__).parents[1] / "config" / "etf-competitor-universe.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def match_competitors(theme_id: str, theme_name: str, aliases: list[str]) -> list[dict[str, Any]]:
    terms = {
        str(value).casefold().strip()
        for value in (theme_id, theme_name, *aliases)
        if len(str(value).strip()) >= 2
    }
    tokens = {
        token
        for term in terms
        for token in term.replace("-", " ").split()
        if len(token) >= 2 and token not in {"theme", "analysis", "etf", "主题", "研究", "新兴", "发现"}
    }
    matched = []
    for fund in load_universe():
        tags = {str(value).casefold() for value in fund.get("theme_tags", [])}
        haystack = " ".join((str(fund.get("category", "")), *tags)).casefold()
        if terms & tags or any(token in haystack for token in tokens):
            matched.append(fund)
    return matched


def _history_from_yahoo(ticker: str) -> list[dict[str, Any]]:
    import yfinance as yf

    frame = yf.Ticker(ticker).history(
        period="6mo", interval="1d", auto_adjust=True,
        timeout=max(1, int(SETTINGS.get("request_timeout_seconds", 8))),
    )
    rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        close = row.get("Close")
        volume = row.get("Volume")
        if close is None or volume is None or math.isnan(float(close)):
            continue
        rows.append({"date": index.isoformat(), "close": float(close), "volume": float(volume)})
    return rows


def _return(prices: list[float], days: int) -> float | None:
    return round(prices[-1] / prices[-days - 1] - 1, 6) if len(prices) > days and prices[-days - 1] else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def calculate_market_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    prices = [float(row["close"]) for row in rows]
    volumes = [float(row["volume"]) for row in rows]
    if len(prices) < 6:
        return {"data_status": "insufficient_data"}
    daily_returns = [prices[index] / prices[index - 1] - 1 for index in range(1, len(prices))]
    volatility_window = int(SETTINGS.get("volatility_window_days", 63))
    volatility_sample = daily_returns[-volatility_window:]
    volatility = (
        statistics.stdev(volatility_sample) * math.sqrt(252)
        if len(volatility_sample) >= 2 else None
    )
    drawdown_prices = prices[-int(SETTINGS.get("drawdown_window_days", 63)):]
    peak = drawdown_prices[0]
    max_drawdown = 0.0
    for price in drawdown_prices:
        peak = max(peak, price)
        max_drawdown = min(max_drawdown, price / peak - 1)
    avg_window = int(SETTINGS.get("average_volume_window_days", 20))
    recent_prices = prices[-avg_window:]
    recent_volumes = volumes[-avg_window:]
    average_volume = _mean(recent_volumes)
    average_dollar_volume = _mean([p * v for p, v in zip(recent_prices, recent_volumes)])
    recent_five = _mean(volumes[-5:])
    prior_twenty = _mean(volumes[-25:-5])
    activity_ratio = recent_five / prior_twenty if recent_five is not None and prior_twenty else None
    return_1m = _return(prices, 21)
    bull = SETTINGS.get("bullish_return_1m", 0.03)
    bear = SETTINGS.get("bearish_return_1m", -0.03)
    trend = "up" if return_1m is not None and return_1m >= bull else "down" if return_1m is not None and return_1m <= bear else "sideways"
    return {
        "data_status": "available" if len(prices) >= 64 else "partial",
        "as_of": rows[-1]["date"],
        "last_close": round(prices[-1], 4),
        "currency": "USD",
        "returns": {"1w": _return(prices, 5), "1m": return_1m, "3m": _return(prices, 63)},
        "annualized_volatility_3m": round(volatility, 6) if volatility is not None else None,
        "max_drawdown_3m": round(max_drawdown, 6),
        "average_volume_20d": round(average_volume, 2) if average_volume is not None else None,
        "average_dollar_volume_20d": round(average_dollar_volume, 2) if average_dollar_volume is not None else None,
        "volume_activity_ratio": round(activity_ratio, 4) if activity_ratio is not None else None,
        "activity_trend": "higher" if activity_ratio is not None and activity_ratio >= 1.15 else "lower" if activity_ratio is not None and activity_ratio <= 0.85 else "stable",
        "price_trend": trend,
        "buyer_count_status": "not_available",
        "fund_flow_status": "not_assessed",
    }


def collect_market_snapshot(
    competitors: list[dict[str, Any]], cache_dir: Path,
    fetcher: Callable[[str], list[dict[str, Any]]] = _history_from_yahoo,
) -> dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    ttl = int(SETTINGS.get("cache_ttl_seconds", 1800))
    cooldown_seconds = int(SETTINGS.get("failure_cooldown_seconds", 300))
    products: list[dict[str, Any]] = []
    max_products = max(1, int(SETTINGS.get("max_products_per_snapshot", 6)))
    selected_competitors = competitors[:max_products]
    for fund_index, fund in enumerate(selected_competitors):
        if fund_index and fetcher is _history_from_yahoo:
            time.sleep(max(0.0, SETTINGS.get("ticker_throttle_seconds", 0.2)))
        ticker = str(fund.get("ticker", "")).upper()
        yahoo_symbol = str(fund.get("yahoo_symbol") or ticker).upper()
        currency = str(fund.get("currency") or "USD").upper()
        source_url = f"https://finance.yahoo.com/quote/{yahoo_symbol}/"
        cache_file = cache_dir / f"{yahoo_symbol.casefold().replace('^', '_')}-history.json"
        failure_file = cache_dir / f"{yahoo_symbol.casefold().replace('^', '_')}-failure.json"
        error = ""
        rows: list[dict[str, Any]] = []
        try:
            fresh_cache = cache_file.exists() and time.time() - cache_file.stat().st_mtime <= ttl
            if fresh_cache:
                rows = json.loads(cache_file.read_text(encoding="utf-8"))
            if rows:
                cache_status = "hit"
            else:
                # Older versions could persist [] as a successful response.
                # Remove that poison cache and make one bounded live attempt.
                if fresh_cache and cache_file.exists():
                    cache_file.unlink()
                cooling_down = failure_file.exists() and time.time() - failure_file.stat().st_mtime <= cooldown_seconds
                if cooling_down and cache_file.exists():
                    rows = json.loads(cache_file.read_text(encoding="utf-8"))
                    cache_status = "stale_if_error"
                    error = "近期请求失败，处于冷却期；已使用最后一次成功缓存。"
                else:
                    last_error: Exception | None = None
                    retry_attempts = max(1, int(SETTINGS.get("refresh_retry_attempts", 3)))
                    retry_backoff = max(0.0, float(SETTINGS.get("refresh_retry_backoff_seconds", .25)))
                    for attempt in range(retry_attempts):
                        try:
                            rows = fetcher(yahoo_symbol)
                            break
                        except Exception as exc:
                            last_error = exc
                            rate_limited = "429" in str(exc) or "rate limit" in str(exc).casefold()
                            if not rate_limited or attempt == retry_attempts - 1:
                                raise
                            time.sleep(retry_backoff * (2 ** attempt))
                    if last_error is not None and not rows:
                        raise last_error
                    if not rows:
                        raise RuntimeError("Yahoo 未返回可用的历史行情")
                    cache_file.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
                    if failure_file.exists():
                        failure_file.unlink()
                    cache_status = "miss"
            metrics = calculate_market_metrics(rows)
            content_hash = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        except Exception as exc:
            error = str(exc)[:300]
            failure_file.write_text(json.dumps({"failed_at": datetime.now(timezone.utc).isoformat(), "error": error}, ensure_ascii=False), encoding="utf-8")
            if cache_file.exists():
                try:
                    rows = json.loads(cache_file.read_text(encoding="utf-8"))
                    if not rows:
                        raise ValueError("空行情缓存不可用")
                    metrics = calculate_market_metrics(rows)
                    metrics["data_status"] = "stale"
                    content_hash = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
                    cache_status = "stale_if_error"
                except (OSError, json.JSONDecodeError, ValueError):
                    metrics = {"data_status": "unavailable"}
                    content_hash = ""
                    cache_status = "failed"
            else:
                metrics = {"data_status": "unavailable"}
                content_hash = ""
                cache_status = "failed"
        products.append({
            "ticker": ticker,
            "yahoo_symbol": yahoo_symbol,
            "issuer": fund.get("issuer", ""),
            "category": fund.get("category", ""),
            "fund_name": fund.get("fund_name", ""),
            "exchange": fund.get("exchange", ""),
            "listing_market": fund.get("listing_market", "United States"),
            "official_url": fund.get("official_url") or fund.get("holdings_url", ""),
            "verification_status": fund.get("verification_status", "configured_universe"),
            "verification_sources": [
                value for value in (fund.get("verification_sources") or [fund.get("holdings_url", "")])
                if value
            ],
            "source_url": source_url,
            "source": "Yahoo Finance via yfinance",
            "content_hash": content_hash,
            "cache_status": cache_status,
            "error": error,
            **metrics,
            "currency": currency,
        })
    peer_returns = [
        item["returns"]["1m"] for item in products
        if isinstance(item.get("returns"), dict) and item["returns"].get("1m") is not None
    ]
    peer_median = statistics.median(peer_returns) if peer_returns else None
    for item in products:
        value = (item.get("returns") or {}).get("1m")
        item["relative_strength_1m"] = round(value - peer_median, 6) if value is not None and peer_median is not None else None
    available = sum(item.get("data_status") in {"available", "partial", "stale"} for item in products)
    return {
        "market_as_of": max((str(item.get("as_of") or "") for item in products), default=""),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "status": "available" if available == len(products) and products else "partial" if available else "unknown",
        "products": products,
        "requested_products": len(competitors),
        "snapshot_product_limit": max_products,
        "limitations": [
            "Yahoo Finance/yfinance 仅用于个人研究与二级发现；行情不构成投资建议。",
            "成交量与成交额仅表示交易活跃度，不能解释为买入人数或资金净流入。",
            "AUM、净申购和指数规则未由可靠官方来源核验时保持 not_assessed。",
            "不同币种的成交额不做横向排名；跨市场仅比较百分比收益等无量纲指标。",
        ],
    }


def _identity(value: object) -> str:
    text = str(value or "").upper().strip()
    for suffix in (".SS", ".SZ", ".HK"):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
    return "".join(character for character in text if character.isalnum())


def collect_dual_source_market_snapshot(
    competitors: list[dict[str, Any]],
    tiantian_snapshot: dict[str, Any] | None,
    cache_dir: Path,
    fetcher: Callable[[str], list[dict[str, Any]]] = _history_from_yahoo,
) -> dict[str, Any]:
    """Refresh yfinance and merge a frozen Tiantian snapshot with field provenance.

    The sources cover different markets, so cross-validation is performed only for
    products and fields that are actually comparable. A single-source field remains
    usable with an explicit verification state instead of being treated as missing.
    """
    yahoo = collect_market_snapshot(competitors, cache_dir, fetcher)
    products: list[dict[str, Any]] = []
    by_identity: dict[str, dict[str, Any]] = {}
    for item in yahoo.get("products") or []:
        available = item.get("data_status") in {"available", "partial", "stale"}
        enriched = {
            **item,
            "sources": [{
                "name": "Yahoo Finance via yfinance",
                "status": "available" if available else "failed",
                "as_of": item.get("as_of", ""),
                "url": item.get("source_url", ""),
                "error": item.get("error", ""),
            }],
            "field_provenance": {
                key: "yfinance" for key in (
                    "last_close", "returns", "annualized_volatility_3m", "max_drawdown_3m",
                    "average_volume_20d", "average_dollar_volume_20d", "activity_trend",
                ) if item.get(key) is not None
            },
            "cross_source_validation": {"status": "single_source", "comparable_fields": [], "conflicts": []},
        }
        products.append(enriched)
        for value in (item.get("ticker"), item.get("yahoo_symbol")):
            if _identity(value):
                by_identity[_identity(value)] = enriched

    tiantian_products = list((tiantian_snapshot or {}).get("products") or [])
    tiantian_as_of = str((tiantian_snapshot or {}).get("market_as_of") or "")
    for fund in tiantian_products:
        identity = _identity(fund.get("code"))
        source_record = {
            "name": "天天基金网",
            "status": "available",
            "as_of": fund.get("market_date") or fund.get("nav_date") or tiantian_as_of,
            "url": fund.get("source_url", ""),
            "error": "",
        }
        matched = by_identity.get(identity)
        tiantian_fields = {
            "operating_fee": fund.get("operating_fee"),
            "aum_billion_cny": fund.get("scale_billion"),
            "return_2025": fund.get("return_2025"),
            "rolling_1y": fund.get("rolling_1y"),
            "tracking_error": fund.get("tracking_error"),
            "premium_rate": fund.get("premium_rate"),
            "tracking_index": fund.get("tracking_index"),
        }
        if matched:
            matched["sources"].append(source_record)
            matched.update({key: value for key, value in tiantian_fields.items() if value is not None})
            matched["field_provenance"].update({key: "tiantian" for key, value in tiantian_fields.items() if value is not None})
            conflicts = []
            yahoo_name = str(matched.get("fund_name") or "").casefold().strip()
            tiantian_name = str(fund.get("name") or "").casefold().strip()
            if yahoo_name and tiantian_name and yahoo_name != tiantian_name:
                conflicts.append({"field": "fund_name", "yfinance": matched.get("fund_name"), "tiantian": fund.get("name")})
            matched["cross_source_validation"] = {
                "status": "conflict" if conflicts else "consistent",
                "comparable_fields": ["product_identity", "fund_name"],
                "conflicts": conflicts,
            }
            continue
        converted = {
            "ticker": str(fund.get("code") or ""),
            "fund_name": str(fund.get("name") or ""),
            "issuer": str(fund.get("manager") or ""),
            "category": str(fund.get("category_label") or fund.get("category") or ""),
            "exchange": str(fund.get("exchange") or "China fund market"),
            "listing_market": "China",
            "currency": "CNY",
            "official_url": str(fund.get("source_url") or ""),
            "source_url": str(fund.get("source_url") or ""),
            "data_status": "available",
            "as_of": source_record["as_of"],
            "sources": [source_record],
            "field_provenance": {key: "tiantian" for key, value in tiantian_fields.items() if value is not None},
            "cross_source_validation": {
                "status": "single_source",
                "comparable_fields": [],
                "conflicts": [],
                "reason": "yfinance 当前候选中没有可确定匹配的同一产品。",
            },
            **{key: value for key, value in tiantian_fields.items() if value is not None},
        }
        products.append(converted)

    usable = [item for item in products if item.get("data_status") in {"available", "partial", "stale"}]
    source_status = {
        "yfinance": {
            "status": yahoo.get("status", "unknown"),
            "requested": int(yahoo.get("requested_products") or 0),
            "available": sum(item.get("data_status") in {"available", "partial", "stale"} for item in yahoo.get("products") or []),
        },
        "tiantian": {
            "status": str((tiantian_snapshot or {}).get("status") or ("available" if tiantian_products else "not_assessed")),
            "snapshot_id": str((tiantian_snapshot or {}).get("snapshot_id") or ""),
            "available": len(tiantian_products),
        },
    }
    return {
        **{key: value for key, value in yahoo.items() if key not in {"products", "status", "market_as_of"}},
        "market_as_of": max([str(item.get("as_of") or "") for item in products] or [""]),
        "status": "available" if products and len(usable) == len(products) and all(value["status"] == "available" for value in source_status.values()) else "partial" if usable else "unknown",
        "products": products,
        "source_status": source_status,
        "validation_summary": {
            "consistent": sum(item.get("cross_source_validation", {}).get("status") == "consistent" for item in products),
            "conflict": sum(item.get("cross_source_validation", {}).get("status") == "conflict" for item in products),
            "single_source": sum(item.get("cross_source_validation", {}).get("status") == "single_source" for item in products),
        },
        "limitations": [
            *(yahoo.get("limitations") or []),
            "天天基金网与 yfinance 覆盖市场不同；只对可确定匹配且日期可比的产品字段进行交叉验证。",
            "单一来源字段保留来源、日期和验证状态，不伪装成双源一致。",
        ],
    }
