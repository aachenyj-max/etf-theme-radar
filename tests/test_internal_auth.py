from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from etf_theme_radar import internal_auth
from etf_theme_radar.api import app


def _configure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("STARTUP_SYNC_ENABLED", "false")
    monkeypatch.setenv("INTERNAL_AUTH_ENABLED", "true")
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "a" * 48)
    monkeypatch.setenv("INTERNAL_AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("PUBLIC_FRONTEND_URL", "http://testserver")
    monkeypatch.setenv("INTERNAL_USERS_JSON", json.dumps([
        {"username": "radar01", "password_hash": internal_auth.hash_password("a-strong-password")},
    ]))


def test_internal_login_protects_research_api(tmp_path: Path, monkeypatch) -> None:
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/capabilities").status_code == 401
        assert client.post("/api/auth/login", json={"username": "radar01", "password": "wrong"}).status_code == 401
        login = client.post("/api/auth/login", json={"username": "radar01", "password": "a-strong-password"})
        assert login.status_code == 200
        assert login.json() == {"authenticated": True, "username": "radar01"}
        assert client.get("/api/capabilities").status_code == 200
        assert client.post("/api/sync-runs?days=7", headers={"Origin": "https://unexpected.example"}).status_code == 403
        assert client.post("/api/auth/logout").status_code == 200
        assert client.get("/api/capabilities").status_code == 401


def test_session_token_rejects_tampering(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_AUTH_ENABLED", "true")
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "b" * 48)
    monkeypatch.setenv("INTERNAL_USERS_JSON", json.dumps([
        {"username": "radar01", "password_hash": internal_auth.hash_password("a-strong-password")},
    ]))
    token = internal_auth.issue_session("radar01", now=100)
    assert internal_auth.session_user(token, now=101) == "radar01"
    assert internal_auth.session_user(token + "changed", now=101) is None
