"""Purpose-built parser for ETF registration documents; never treats form type as a new fund by itself."""
from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse


def _find(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.I | re.S)
    return re.sub(r"\s+", " ", unescape(match.group(1))).strip() if match else None


def parse_sec_etf_filing(text: str, url: str, form_type: str | None = None) -> dict[str, str | None]:
    clean = re.sub(r"<[^>]+>", " ", text)
    accession = re.search(r"/([0-9]{18})/", url)
    cik = re.search(r"/data/(\d+)/", url)
    fund_name = _find(r"(?:Fund Summary|Prospectus).*?([A-Z][A-Za-z0-9 &'’\-]+ ETF)", clean)
    trust_name = _find(r"([A-Z][A-Z0-9 &'’\-]+(?:TRUST|Trust))\s*\(Exact Name", clean)
    filing_type = form_type or (_find(r"FORM\s+([A-Z0-9\-]+)", clean) or "unknown")
    effective = _find(r"effective(?: on)?\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})", clean)
    strategy = _find(r"Investment Objective\s*(.{0,600}?)(?:Fees and Expenses|Principal Investment|Summary)", clean)
    index_name = _find(r"(?:Underlying Index|Index)\s*[:\-]?\s*([A-Z][A-Za-z0-9 &®'’\-]+(?:Index|NASDAQ|S&P 500)[A-Za-z0-9 &®'’\-]*)", clean)
    expense = _find(r"(?:Management Fee|Total Annual Fund Operating Expenses).*?([0-9]+(?:\.[0-9]+)?%)", clean)
    adviser = _find(r"(?:Investment Adviser|Adviser)\s*[:\-]?\s*([A-Z][A-Za-z0-9 &,.'’\-]+(?:LLC|Inc\.|LP|Ltd\.)?)", clean)
    risks = _find(r"Principal Risks\s*(.{0,800}?)(?:Performance|Management|Purchase)", clean)
    ticker = _find(r"(?:Ticker|Trading Symbol)\s*[:\-]?\s*([A-Z]{1,5})", clean)
    # A 485 amendment is ordinary unless the document explicitly says it adds a new series/fund.
    lower = clean.lower()
    if "withdraw" in lower: event_type = "withdrawal"
    elif "effective" in lower and filing_type in {"497", "485BPOS"}: event_type = "effectiveness"
    elif re.search(r"add (?:a |two |new )?(?:new )?(?:series|funds?)", lower): event_type = "new_series"
    elif filing_type == "N-1A" and re.search(r"registration statement|initial", lower): event_type = "new_fund_registration"
    elif "fee" in lower and ("change" in lower or "expense" in lower): event_type = "fee_change"
    elif "name change" in lower or "renamed" in lower: event_type = "name_change"
    elif "strategy" in lower and "change" in lower: event_type = "strategy_change"
    elif filing_type.startswith("485"): event_type = "ordinary_amendment"
    else: event_type = "unknown"
    return {"cik": cik.group(1) if cik else None, "registrant_name": trust_name, "trust_name": trust_name, "fund_name": fund_name, "filing_type": filing_type, "filing_date": _find(r"(?:As filed|Filed)\s+(?:with.*?on\s+)?([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})", clean), "accession_number": accession.group(1) if accession else None, "effective_date": effective, "sponsor_or_adviser": adviser, "sub_adviser": _find(r"Sub-Adviser\s*[:\-]?\s*(.{0,160})", clean), "index_provider": _find(r"(?:Index Provider|Index)\s*[:\-]?\s*([A-Z][A-Za-z0-9 &]+)", clean), "active_or_passive": "passive" if "passively managed" in lower or "seeks to track" in lower else "active" if "actively managed" in lower else None, "underlying_index": index_name, "expense_ratio": expense, "investment_strategy": strategy, "principal_risks": risks, "ticker_if_available": ticker, "filing_event_type": event_type}
