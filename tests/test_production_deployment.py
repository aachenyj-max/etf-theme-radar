from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_tool(name: str):
    path = PROJECT_ROOT / "tools" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_production_compose_keeps_internal_services_off_host_ports() -> None:
    compose = (PROJECT_ROOT / "compose.production.yml").read_text(encoding="utf-8")
    assert "target: api" in compose and "target: frontend" in compose
    assert "radar_data:/app/data" in compose
    assert "127.0.0.1" in compose
    assert '"8001"' in compose and '"3000"' in compose
    assert "ports:" in compose.split("  caddy:", 1)[1]
    assert "profiles: [\"maintenance\"]" in compose


def test_production_reverse_proxy_preserves_sse_and_security_headers() -> None:
    caddy = (PROJECT_ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    assert "flush_interval -1" in caddy
    assert "X-Content-Type-Options" in caddy
    assert "X-Frame-Options" in caddy


def test_sqlite_backup_and_restore_round_trip(tmp_path: Path) -> None:
    backup_tool = _load_tool("backup_sqlite.py")
    restore_tool = _load_tool("restore_sqlite.py")
    source = tmp_path / "source.db"
    import sqlite3
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE records (value TEXT)")
        connection.execute("INSERT INTO records VALUES ('preserved')")
    backup = backup_tool.create_backup(source, tmp_path / "backups")
    target = tmp_path / "restored.db"
    restore_tool.restore_backup(backup, target, str(target.resolve()))
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT value FROM records").fetchone() == ("preserved",)


def test_restore_rejects_an_unconfirmed_target(tmp_path: Path) -> None:
    restore_tool = _load_tool("restore_sqlite.py")
    backup = tmp_path / "backup.db"
    import sqlite3
    with sqlite3.connect(backup) as connection:
        connection.execute("CREATE TABLE records (value TEXT)")
    target = tmp_path / "target.db"
    try:
        restore_tool.restore_backup(backup, target, "different-path")
    except ValueError as error:
        assert "confirm-target" in str(error)
    else:
        raise AssertionError("restore must require an exact target confirmation")


def test_backup_and_restore_include_versioned_knowledge_files(tmp_path: Path) -> None:
    backup_tool = _load_tool("backup_sqlite.py")
    restore_tool = _load_tool("restore_sqlite.py")
    source = tmp_path / "source.db"
    knowledge = tmp_path / "knowledge-files"
    (knowledge / "item-1").mkdir(parents=True)
    stored = knowledge / "item-1" / "v000001.bin"
    stored.write_bytes(b"versioned private material")
    import sqlite3
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE versions (content_hash TEXT)")
        connection.execute("INSERT INTO versions VALUES ('preserved')")
    backup = backup_tool.create_backup(source, tmp_path / "backups", knowledge_dir=knowledge)
    target = tmp_path / "restored.db"
    restored_files = tmp_path / "restored-files"
    restore_tool.restore_backup(
        backup, target, str(target.resolve()),
        knowledge_backup_dir=backup.with_suffix(".knowledge"), knowledge_target_dir=restored_files,
    )
    assert (restored_files / "item-1" / "v000001.bin").read_bytes() == b"versioned private material"
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT content_hash FROM versions").fetchone() == ("preserved",)
