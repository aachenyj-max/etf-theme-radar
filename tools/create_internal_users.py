"""Generate five internal pilot accounts and configuration values exactly once."""

from __future__ import annotations

import argparse
import json
import secrets
from etf_theme_radar.internal_auth import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--prefix", default="radar")
    args = parser.parse_args()
    if not 1 <= args.count <= 20:
        raise SystemExit("--count must be between 1 and 20")
    credentials = []
    users = []
    for index in range(1, args.count + 1):
        username = f"{args.prefix}{index:02d}"
        password = secrets.token_urlsafe(14)
        credentials.append((username, password))
        users.append({"username": username, "password_hash": hash_password(password)})
    print("Give each colleague one password through a private channel; it will not be shown again.")
    for username, password in credentials:
        print(f"{username}: {password}")
    print("\nAdd these lines to deploy/.env.production:")
    print("INTERNAL_AUTH_ENABLED=true")
    print(f"INTERNAL_AUTH_SECRET={secrets.token_urlsafe(48)}")
    print("INTERNAL_USERS_JSON=" + json.dumps(users, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
