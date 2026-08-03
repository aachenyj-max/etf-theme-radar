from __future__ import annotations

import ipaddress
import json
import os
import socket
import re
from pathlib import Path
from urllib.parse import urlparse


class BrowserPolicyError(ValueError):
    pass


INSTRUCTION_PATTERNS = (
    r"ignore\s+(all\s+)?previous\s+instructions?",
    r"system\s+prompt",
    r"developer\s+message",
    r"you\s+are\s+(chatgpt|an?\s+assistant|an?\s+agent)",
    r"do\s+not\s+follow",
    r"忽略.{0,12}(指令|提示)",
    r"系统提示词|开发者消息|扮演.{0,12}(助手|agent)",
)


def sanitize_untrusted_text(text: str, *, max_chars: int = 50_000) -> tuple[str, int]:
    """Remove instruction-like lines from untrusted browser text."""
    removed = 0
    kept: list[str] = []
    for raw_line in text.replace("\x00", "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in INSTRUCTION_PATTERNS):
            removed += 1
            continue
        kept.append(line)
    return "\n".join(kept)[:max_chars], removed


def _tool_text(result: object) -> str:
    return "\n".join(
        getattr(item, "text", "")
        for item in getattr(result, "content", [])
        if getattr(item, "type", "") == "text"
    )


def _result_url(result: object, fallback: str) -> str:
    text = _tool_text(result)
    matches = re.findall(r"https?://[^\s\]\[<>'\"`]+", text)
    return matches[-1].rstrip(".,);") if matches else fallback


def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BrowserPolicyError("仅允许公开 HTTP/HTTPS URL")
    allowed = {item.strip().casefold() for item in os.getenv("PUBLIC_BROWSER_ALLOWED_DOMAINS", "").split(",") if item.strip()}
    host = parsed.hostname.casefold()
    if allowed and not any(host == domain or host.endswith("." + domain) for domain in allowed):
        raise BrowserPolicyError("目标域名不在公开浏览器允许列表")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except socket.gaierror as exc:
        raise BrowserPolicyError("目标域名无法解析") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise BrowserPolicyError("禁止访问本机、内网或保留地址")
    return url


async def fetch_public_page(url: str) -> dict:
    """Read a public page through a local Playwright MCP stdio server.

    The dependency is imported lazily so ordinary connector workflows do not load
    MCP schemas or require a browser process.
    """
    validate_public_url(url)
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise RuntimeError("Playwright MCP client dependency is not installed") from exc
    command = os.getenv("PLAYWRIGHT_MCP_COMMAND", "npx.cmd" if os.name == "nt" else "npx")
    configured = os.getenv("PLAYWRIGHT_MCP_ARGS")
    args = json.loads(configured) if configured else ["-y", "@playwright/mcp", "--headless", "--isolated", "--output-mode", "file", "--output-dir", str(Path("data/mcp-output").resolve())]
    parameters = StdioServerParameters(command=command, args=args)
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            try:
                navigation = await session.call_tool("browser_navigate", {"url": url})
                location = await session.call_tool("browser_evaluate", {"function": "() => window.location.href"})
                final_url = validate_public_url(_result_url(location, _result_url(navigation, url)))
                network = await session.call_tool("browser_network_requests", {"includeStatic": False})
                network_urls = re.findall(r"https?://[^\s\]\[<>'\"`]+", _tool_text(network))
                for request_url in network_urls:
                    validate_public_url(request_url.rstrip(".,);"))
                snapshot = await session.call_tool("browser_snapshot", {})
            finally:
                await session.call_tool("browser_close", {})
    raw_text = _tool_text(snapshot)
    text, removed = sanitize_untrusted_text(raw_text)
    return {
        "url": final_url, "requested_url": url, "text": text,
        "content_length": len(text), "removed_instruction_lines": removed,
        "network_request_count": len(network_urls), "access": "public-playwright-mcp-untrusted",
    }
