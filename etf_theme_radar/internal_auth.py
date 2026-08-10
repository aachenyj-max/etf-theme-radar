"""Small, configuration-backed authentication for the internal pilot."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass


COOKIE_NAME = "radar_session"
DEFAULT_TTL_SECONDS = 60 * 60 * 12


@dataclass(frozen=True)
class InternalUser:
    username: str
    password_hash: str


def enabled() -> bool:
    return os.getenv("INTERNAL_AUTH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _secret() -> bytes:
    value = os.getenv("INTERNAL_AUTH_SECRET", "")
    if len(value) < 32:
        raise RuntimeError("INTERNAL_AUTH_SECRET must be at least 32 characters when internal authentication is enabled")
    return value.encode("utf-8")


def _users() -> dict[str, InternalUser]:
    raw = os.getenv("INTERNAL_USERS_JSON", "")
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("INTERNAL_USERS_JSON must be a JSON array") from error
    if not isinstance(items, list) or not items:
        raise RuntimeError("INTERNAL_USERS_JSON must contain at least one account")
    users: dict[str, InternalUser] = {}
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("every internal account must be an object")
        username = str(item.get("username") or "").strip()
        password_hash = str(item.get("password_hash") or "")
        if not username or not password_hash.startswith("scrypt$") or username in users:
            raise RuntimeError("internal accounts require unique usernames and scrypt password hashes")
        users[username] = InternalUser(username, password_hash)
    return users


def validate_configuration() -> None:
    if enabled():
        _secret()
        _users()


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    salt = salt or secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
    return f"scrypt${n}${r}${p}${encode(salt)}${encode(derived)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, encoded_salt, encoded_hash = stored.split("$")
        if algorithm != "scrypt":
            return False
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        expected = decode(encoded_hash)
        derived = hashlib.scrypt(
            password.encode("utf-8"), salt=decode(encoded_salt),
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
        return hmac.compare_digest(derived, expected)
    except (ValueError, TypeError):
        return False


def authenticate(username: str, password: str) -> InternalUser | None:
    user = _users().get(username.strip())
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def issue_session(username: str, *, now: int | None = None) -> str:
    now = now or int(time.time())
    ttl = max(300, int(os.getenv("INTERNAL_AUTH_TTL_SECONDS", str(DEFAULT_TTL_SECONDS))))
    payload = json.dumps({"u": username, "e": now + ttl}, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def session_user(token: str | None, *, now: int | None = None) -> str | None:
    if not token or "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    expected = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        username = str(payload["u"])
        expires_at = int(payload["e"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if expires_at < (now or int(time.time())) or username not in _users():
        return None
    return username
