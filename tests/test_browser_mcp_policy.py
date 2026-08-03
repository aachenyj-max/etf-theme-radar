from __future__ import annotations

import socket

import pytest

from etf_theme_radar.browser_mcp import BrowserPolicyError, validate_public_url


def test_browser_policy_rejects_local_and_file_urls(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))])
    with pytest.raises(BrowserPolicyError): validate_public_url("http://localhost/admin")
    with pytest.raises(BrowserPolicyError): validate_public_url("file:///etc/passwd")


def test_browser_policy_applies_domain_allowlist(monkeypatch) -> None:
    monkeypatch.setenv("PUBLIC_BROWSER_ALLOWED_DOMAINS", "sec.gov,openalex.org")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("23.1.2.3", 443))])
    assert validate_public_url("https://www.sec.gov/Archives/example")
    with pytest.raises(BrowserPolicyError): validate_public_url("https://example.com/")
