from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from etf_theme_radar.api import CONTRACT_VERSION, STREAM_PAUSE_STATES, app
from etf_theme_radar.store import (
    AGENT_GOAL_ACTIVE_STATUSES,
    AGENT_GOAL_TERMINAL_STATUSES,
    EvidenceStore,
    RESEARCH_EXECUTION_STATUSES,
)


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).casefold()


def _normalize_frontend_path(path: str) -> str:
    path = path.replace("${query}", "")
    path = re.sub(
        r"\$\{encodeURIComponent\((?:\w+\.)*(\w+)\)\}",
        lambda match: "{" + _snake_case(match.group(1)) + "}",
        path,
    )
    path = re.sub(
        r"\$\{(\w+)\}",
        lambda match: "{" + _snake_case(match.group(1)) + "}",
        path,
    )
    path = re.sub(r"\$\{[^}]+\}", "", path)
    return path.split("?", 1)[0].rstrip("`'\"),; ")


def _database_tables() -> list[str]:
    with tempfile.TemporaryDirectory() as directory:
        store = EvidenceStore(Path(directory) / "contract.db")
        try:
            rows = store.conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            return [str(row[0]) for row in rows]
        finally:
            store.close()


def _api_routes() -> list[list[str]]:
    routes: list[list[str]] = []
    for route in app.routes:
        path = str(getattr(route, "path", ""))
        if path != "/health" and not path.startswith("/api/"):
            continue
        for method in sorted(getattr(route, "methods", set()) or set()):
            if method not in {"HEAD", "OPTIONS"}:
                routes.append([method, path])
    return sorted(routes, key=lambda item: (item[1], item[0]))


def _frontend_gateway_dependencies() -> dict[str, list[str]]:
    dependencies: dict[str, list[str]] = {}
    services = PROJECT_ROOT / "frontend" / "src" / "services"
    for source in sorted(services.glob("*.ts")):
        source_text = source.read_text(encoding="utf-8")
        source_text = re.sub(r"/\*.*?\*/", "", source_text, flags=re.DOTALL)
        source_text = re.sub(r"^\s*//.*$", "", source_text, flags=re.MULTILINE)
        paths = {
            normalized
            for match in re.findall(r"/api/[^`\"'\s]+", source_text)
            if (normalized := _normalize_frontend_path(match))
        }
        dependencies[source.name] = sorted(paths)
    return dependencies


def build_snapshot() -> dict[str, object]:
    return {
        "contract_version": CONTRACT_VERSION,
        "database_tables": _database_tables(),
        "status_enums": {
            "research_execution": list(RESEARCH_EXECUTION_STATUSES),
            "research_stream_pause": sorted(STREAM_PAUSE_STATES),
            "agent_goal": {
                "active": list(AGENT_GOAL_ACTIVE_STATUSES),
                "terminal": list(AGENT_GOAL_TERMINAL_STATUSES),
            },
            "content_quality": ["publishable", "needs_enrichment", "rejected"],
            "extracted_fact": ["audited", "incomplete"],
            "extraction_exception": ["open", "resolved"],
            "independent_score": ["assessed", "not_assessed"],
            "theme_candidate": [
                "signal", "validating", "awaiting_confirmation",
                "confirmed", "merged", "rejected",
            ],
            "sync_run": ["queued", "running", "completed", "cancelled", "failed"],
            "discovery_run": ["queued", "running", "completed", "failed"],
            "report_asset": ["deep_research", "watch", "completed", "draft", "archived"],
            "connector_health": ["healthy", "degraded", "disabled"],
            "theme_definition": ["draft", "confirmed"],
            "entity_review": ["pending", "confirmed", "rejected"],
        },
        "api_routes": _api_routes(),
        "frontend_gateway_dependencies": _frontend_gateway_dependencies(),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    json.dump(build_snapshot(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
