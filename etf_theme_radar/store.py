from __future__ import annotations
import json, sqlite3, threading
from pathlib import Path
from .models import ConnectorHealth, NormalizedEvent, RawDocument, utcnow

SCHEMA = '''
CREATE TABLE IF NOT EXISTS raw_documents (content_hash TEXT PRIMARY KEY, source TEXT, source_url TEXT, title TEXT, text TEXT, source_type TEXT, published_at TEXT, retrieved_at TEXT, parser_version TEXT, access_note TEXT);
CREATE TABLE IF NOT EXISTS normalized_events (event_id TEXT PRIMARY KEY, source TEXT, source_url TEXT, source_type TEXT, title TEXT, summary TEXT, published_at TEXT, observed_at TEXT, themes TEXT, companies TEXT, tickers TEXT, source_quality REAL, extraction_confidence REAL, raw_content_hash TEXT);
CREATE TABLE IF NOT EXISTS connector_health (source_name TEXT, checked_at TEXT, enabled INTEGER, status TEXT, coverage_note TEXT);
CREATE TABLE IF NOT EXISTS themes (theme_id TEXT PRIMARY KEY, name TEXT, description TEXT, status TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS theme_scores (theme_id TEXT, as_of_date TEXT, score REAL, confidence TEXT, components TEXT, evidence_ids TEXT, PRIMARY KEY(theme_id, as_of_date));
CREATE TABLE IF NOT EXISTS citations (citation_id TEXT PRIMARY KEY, event_id TEXT, source_url TEXT, source_title TEXT, source_type TEXT, quality REAL, confidence REAL);
CREATE TABLE IF NOT EXISTS product_proposals (proposal_id TEXT PRIMARY KEY, theme_id TEXT, generated_at TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS research_runs (run_id TEXT PRIMARY KEY, theme_id TEXT, status TEXT, stage TEXT, created_at TEXT, updated_at TEXT, result_json TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS report_assets (report_id TEXT PRIMARY KEY, run_id TEXT, title TEXT, kind TEXT, theme_id TEXT, folder_id TEXT, status TEXT, tags TEXT, summary TEXT, updated_at TEXT, created_at TEXT, archived_at TEXT, deleted_at TEXT, version INTEGER DEFAULT 1, source_count INTEGER DEFAULT 0, evidence_count INTEGER DEFAULT 0, audit_passed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS run_steps (run_id TEXT, attempt INTEGER, step_name TEXT, status TEXT, started_at TEXT, finished_at TEXT, error TEXT, details_json TEXT, PRIMARY KEY(run_id,attempt,step_name));
CREATE TABLE IF NOT EXISTS approvals (approval_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, gate TEXT, decision TEXT, note TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS tool_calls (tool_call_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, attempt INTEGER, tool_name TEXT, status TEXT, started_at TEXT, finished_at TEXT, error TEXT, metadata_json TEXT);
CREATE TABLE IF NOT EXISTS agent_runs (agent_run_id TEXT PRIMARY KEY, run_id TEXT, attempt INTEGER, stage TEXT, provider TEXT, model TEXT, prompt_version TEXT, prompt_hash TEXT, status TEXT, stop_reason TEXT, model_requests INTEGER DEFAULT 0, tool_calls INTEGER DEFAULT 0, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, started_at TEXT, finished_at TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS run_registry (run_id TEXT PRIMARY KEY, database_path TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS theme_aliases (theme_id TEXT, alias TEXT, alias_type TEXT, confirmed INTEGER DEFAULT 0, created_at TEXT, PRIMARY KEY(theme_id,alias));
CREATE TABLE IF NOT EXISTS theme_snapshots (snapshot_id TEXT PRIMARY KEY, theme_id TEXT, as_of_date TEXT, metrics_json TEXT, score REAL, confidence TEXT, evidence_count INTEGER, source_type_count INTEGER, trend TEXT, trend_reason TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS entities (entity_id TEXT PRIMARY KEY, entity_type TEXT, canonical_name TEXT, ticker TEXT, exchange TEXT, review_status TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS entity_aliases (entity_id TEXT, alias TEXT, PRIMARY KEY(entity_id,alias));
CREATE TABLE IF NOT EXISTS entity_links (link_id TEXT PRIMARY KEY, entity_id TEXT, event_id TEXT, theme_id TEXT, relation_type TEXT, confidence REAL, review_status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS report_versions (report_id TEXT, version INTEGER, content_hash TEXT, payload_json TEXT, markdown TEXT, created_at TEXT, PRIMARY KEY(report_id,version));
CREATE TABLE IF NOT EXISTS report_claims (claim_id TEXT PRIMARY KEY, report_id TEXT, version INTEGER, claim_text TEXT, claim_type TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS report_claim_evidence (claim_id TEXT, event_id TEXT, relation TEXT, PRIMARY KEY(claim_id,event_id));
CREATE TABLE IF NOT EXISTS sync_runs (sync_run_id TEXT PRIMARY KEY, status TEXT, progress INTEGER, current_source TEXT, created_at TEXT, updated_at TEXT, result_json TEXT, error TEXT, cancel_requested INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS etf_market_snapshots (snapshot_id TEXT PRIMARY KEY, report_id TEXT NOT NULL, collected_at TEXT NOT NULL, market_as_of TEXT, status TEXT, products_json TEXT, errors_json TEXT, payload_json TEXT);
CREATE TABLE IF NOT EXISTS etf_preview_snapshots (snapshot_id TEXT PRIMARY KEY, collected_at TEXT NOT NULL, market_as_of TEXT, status TEXT, source TEXT, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS theme_candidates (candidate_id TEXT PRIMARY KEY, proposed_name TEXT NOT NULL, description TEXT, status TEXT NOT NULL, signature TEXT NOT NULL, window_start TEXT, window_end TEXT, first_seen_at TEXT, last_seen_at TEXT, metrics_json TEXT, rationale TEXT, merged_theme_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidate_evidence (candidate_id TEXT NOT NULL, event_id TEXT NOT NULL, relevance REAL DEFAULT 0, added_at TEXT NOT NULL, PRIMARY KEY(candidate_id,event_id));
CREATE TABLE IF NOT EXISTS candidate_entities (candidate_id TEXT NOT NULL, entity_key TEXT NOT NULL, label TEXT NOT NULL, entity_type TEXT NOT NULL, mention_count INTEGER DEFAULT 1, PRIMARY KEY(candidate_id,entity_key));
CREATE TABLE IF NOT EXISTS candidate_aliases (candidate_id TEXT NOT NULL, alias TEXT NOT NULL, confirmed INTEGER DEFAULT 0, created_at TEXT NOT NULL, PRIMARY KEY(candidate_id,alias));
CREATE TABLE IF NOT EXISTS discovery_runs (discovery_run_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, run_kind TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL, window_start TEXT, window_end TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, result_json TEXT, error TEXT, lease_owner TEXT, lease_expires_at TEXT, heartbeat_at TEXT, attempt INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS source_watermarks (source_name TEXT PRIMARY KEY, watermark TEXT, cursor_json TEXT, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_goals (goal_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, goal_type TEXT NOT NULL, lane TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL, priority INTEGER DEFAULT 0, payload_json TEXT NOT NULL, result_json TEXT NOT NULL, error TEXT NOT NULL, cancel_requested INTEGER DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deadline_at TEXT, lease_owner TEXT NOT NULL, lease_expires_at TEXT NOT NULL, heartbeat_at TEXT NOT NULL, attempt INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS agent_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, event_type TEXT NOT NULL, from_status TEXT NOT NULL, to_status TEXT NOT NULL, created_at TEXT NOT NULL, safe_summary TEXT NOT NULL, details_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS concurrency_leases (lease_id TEXT PRIMARY KEY, goal_id TEXT NOT NULL UNIQUE, lane TEXT NOT NULL, owner TEXT NOT NULL, acquired_at TEXT NOT NULL, heartbeat_at TEXT NOT NULL, expires_at TEXT NOT NULL);
'''
EVENT_COLUMNS = [
    "event_id", "source", "source_url", "source_type", "title", "summary", "published_at", "observed_at", "themes", "companies", "tickers", "source_quality", "extraction_confidence", "raw_content_hash",
    "discovery_source", "origin_source_type", "publisher", "publisher_domain", "primary_or_secondary", "relevance_status", "theme_assignment_status", "primary_theme", "secondary_themes", "classification_confidence", "classification_reasons", "matched_terms", "company_id", "canonical_job_family", "department", "technical_or_nontechnical", "seniority", "first_seen_at", "last_seen_at", "posting_status", "duplicate_job_cluster", "location", "theme_relevance",
]
EVENT_EXTRA_COLUMNS = {
    "discovery_source": "TEXT DEFAULT ''", "origin_source_type": "TEXT DEFAULT 'unknown'", "publisher": "TEXT DEFAULT ''", "publisher_domain": "TEXT DEFAULT ''", "primary_or_secondary": "TEXT DEFAULT 'unknown'", "relevance_status": "TEXT DEFAULT 'uncertain'", "theme_assignment_status": "TEXT DEFAULT 'needs_review'", "primary_theme": "TEXT DEFAULT 'unknown'", "secondary_themes": "TEXT DEFAULT '[]'", "classification_confidence": "REAL DEFAULT 0", "classification_reasons": "TEXT DEFAULT '[]'", "matched_terms": "TEXT DEFAULT '[]'", "company_id": "TEXT DEFAULT ''", "canonical_job_family": "TEXT DEFAULT ''", "department": "TEXT DEFAULT ''", "technical_or_nontechnical": "TEXT DEFAULT 'unknown'", "seniority": "TEXT DEFAULT 'unknown'", "first_seen_at": "TEXT", "last_seen_at": "TEXT", "posting_status": "TEXT DEFAULT 'unknown'", "duplicate_job_cluster": "TEXT DEFAULT ''", "location": "TEXT DEFAULT ''", "theme_relevance": "REAL DEFAULT 0",
}
RUN_EXTRA_COLUMNS = {
    "request_json": "TEXT DEFAULT '{}'",
    "progress": "INTEGER DEFAULT 0",
    "review_gate": "TEXT DEFAULT ''",
    "attempt": "INTEGER DEFAULT 1",
    "parent_run_id": "TEXT DEFAULT ''",
    "database_path": "TEXT DEFAULT ''",
    "lease_owner": "TEXT DEFAULT ''",
    "lease_expires_at": "TEXT DEFAULT ''",
    "heartbeat_at": "TEXT DEFAULT ''",
    "queue_position": "INTEGER",
}
STEP_EXTRA_COLUMNS = {
    "idempotency_key": "TEXT DEFAULT ''",
    "lease_owner": "TEXT DEFAULT ''",
    "lease_expires_at": "TEXT DEFAULT ''",
    "heartbeat_at": "TEXT DEFAULT ''",
    "retry_count": "INTEGER DEFAULT 0",
}
SYNC_EXTRA_COLUMNS = {
    "days": "INTEGER DEFAULT 7",
    "idempotency_key": "TEXT DEFAULT ''",
    "lease_owner": "TEXT DEFAULT ''",
    "lease_expires_at": "TEXT DEFAULT ''",
    "heartbeat_at": "TEXT DEFAULT ''",
    "attempt": "INTEGER DEFAULT 1",
}
TOOL_CALL_EXTRA_COLUMNS = {
    "call_uid": "TEXT DEFAULT ''",
    "agent_run_id": "TEXT DEFAULT ''",
    "round_number": "INTEGER DEFAULT 0",
    "arguments_json": "TEXT DEFAULT '{}'",
    "result_json": "TEXT DEFAULT '{}'",
    "retry_count": "INTEGER DEFAULT 0",
    "latency_ms": "INTEGER DEFAULT 0",
    "evidence_delta": "INTEGER DEFAULT 0",
    "relevant_evidence_delta": "INTEGER DEFAULT 0",
    "coverage_before_json": "TEXT DEFAULT '{}'",
    "coverage_after_json": "TEXT DEFAULT '{}'",
}

_SCHEMA_LOCK = threading.Lock()
_INITIALIZED_DATABASES: set[str] = set()
RESEARCH_EXECUTION_STATUSES = (
    "planning", "queued", "collecting", "governing", "analyzing", "auditing",
)
AGENT_GOAL_ACTIVE_STATUSES = (
    "planning", "collecting", "extracting", "validating", "replanning",
    "context_building", "answering", "quick_retrieval", "streaming",
    "summarizing", "validating_coverage",
)
AGENT_GOAL_TERMINAL_STATUSES = (
    "completed", "partial", "needs_attention", "rebuild_required", "cancelled",
)
AGENT_GOAL_TRANSITIONS = {
    "planning": {"collecting", "extracting", "partial", "needs_attention", "cancelled"},
    "collecting": {"validating", "partial", "needs_attention", "cancelled"},
    "extracting": {"validating", "partial", "needs_attention", "cancelled"},
    "validating": {"replanning", "completed", "partial", "needs_attention", "cancelled"},
    "replanning": {"collecting", "extracting", "partial", "needs_attention", "cancelled"},
    "context_building": {"answering", "quick_retrieval", "cancelled"},
    "answering": {"streaming", "completed", "cancelled"},
    "quick_retrieval": {"streaming", "completed", "cancelled"},
    "streaming": {"completed", "cancelled"},
    "summarizing": {"validating_coverage", "cancelled"},
    "validating_coverage": {"completed", "rebuild_required", "cancelled"},
}

class EvidenceStore:
    def __init__(self, path: str | Path):
        path = Path(path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        existed_before = path.exists() and path.stat().st_size > 0
        self.conn = sqlite3.connect(path, timeout=30)
        self.conn.execute("PRAGMA busy_timeout=30000")
        if str(self.conn.execute("PRAGMA journal_mode").fetchone()[0]).casefold() != "wal":
            self.conn.execute("PRAGMA journal_mode=WAL")
        database_key = str(path)
        with _SCHEMA_LOCK:
            if database_key not in _INITIALIZED_DATABASES:
                self._initialize_schema(existed_before, path)
                _INITIALIZED_DATABASES.add(database_key)

    def _initialize_schema(self, existed_before: bool, path: Path) -> None:
        self.conn.executescript(SCHEMA)
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(normalized_events)")}
        run_existing = {row[1] for row in self.conn.execute("PRAGMA table_info(research_runs)")}
        tool_existing = {row[1] for row in self.conn.execute("PRAGMA table_info(tool_calls)")}
        step_existing = {row[1] for row in self.conn.execute("PRAGMA table_info(run_steps)")}
        sync_existing = {row[1] for row in self.conn.execute("PRAGMA table_info(sync_runs)")}
        needs_upgrade = any(column not in existing for column in EVENT_EXTRA_COLUMNS) or any(column not in run_existing for column in RUN_EXTRA_COLUMNS) or any(column not in tool_existing for column in TOOL_CALL_EXTRA_COLUMNS) or any(column not in step_existing for column in STEP_EXTRA_COLUMNS) or any(column not in sync_existing for column in SYNC_EXTRA_COLUMNS)
        backup_path = path.with_suffix(path.suffix + ".pre-schema-v5-theme-discovery.bak")
        if needs_upgrade and existed_before and not backup_path.exists():
            backup = sqlite3.connect(backup_path)
            try: self.conn.backup(backup)
            finally: backup.close()
        for column, definition in EVENT_EXTRA_COLUMNS.items():
            if column not in existing:
                self.conn.execute(f"ALTER TABLE normalized_events ADD COLUMN {column} {definition}")
        for column, definition in RUN_EXTRA_COLUMNS.items():
            if column not in run_existing:
                self.conn.execute(f"ALTER TABLE research_runs ADD COLUMN {column} {definition}")
        for column, definition in TOOL_CALL_EXTRA_COLUMNS.items():
            if column not in tool_existing:
                self.conn.execute(f"ALTER TABLE tool_calls ADD COLUMN {column} {definition}")
        for column, definition in STEP_EXTRA_COLUMNS.items():
            if column not in step_existing:
                self.conn.execute(f"ALTER TABLE run_steps ADD COLUMN {column} {definition}")
        for column, definition in SYNC_EXTRA_COLUMNS.items():
            if column not in sync_existing:
                self.conn.execute(f"ALTER TABLE sync_runs ADD COLUMN {column} {definition}")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_calls_run ON tool_calls(run_id, attempt, tool_call_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_run ON agent_runs(run_id, attempt)")
        self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_step_idempotency ON run_steps(idempotency_key) WHERE idempotency_key <> ''")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_worker ON research_runs(status, lease_expires_at, updated_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_queue ON research_runs(status, queue_position, created_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_report ON etf_market_snapshots(report_id, collected_at DESC)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_etf_preview_snapshots ON etf_preview_snapshots(collected_at DESC)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_status ON theme_candidates(status, updated_at DESC)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_candidate_evidence_event ON candidate_evidence(event_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_discovery_runs_status ON discovery_runs(status, lease_expires_at, created_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_sync_runs_worker ON sync_runs(status, lease_expires_at, created_at)")
        self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_idempotency ON sync_runs(idempotency_key) WHERE idempotency_key <> ''")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_goals_queue ON agent_goals(lane,status,priority DESC,created_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_goals_lease ON agent_goals(status,lease_expires_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_events_goal ON agent_events(goal_id,event_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_concurrency_leases_lane ON concurrency_leases(lane,expires_at)")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
    def save_raw(self, d: RawDocument) -> None:
        self.conn.execute("INSERT OR IGNORE INTO raw_documents VALUES (?,?,?,?,?,?,?,?,?,?)", (d.content_hash,d.source,d.source_url,d.title,d.text,d.source_type,d.published_at,d.retrieved_at,d.parser_version,d.access_note))
    def save_event(self, e: NormalizedEvent) -> None:
        values = (
            e.event_id, e.source, e.source_url, e.source_type, e.title, e.summary, e.published_at, e.observed_at,
            json.dumps(e.themes), json.dumps(e.companies), json.dumps(e.tickers), e.source_quality, e.extraction_confidence, e.raw_content_hash,
            e.discovery_source, e.origin_source_type, e.publisher, e.publisher_domain, e.primary_or_secondary, e.relevance_status, e.theme_assignment_status, e.primary_theme,
            json.dumps(e.secondary_themes), e.classification_confidence, json.dumps(e.classification_reasons), json.dumps(e.matched_terms), e.company_id,
            e.canonical_job_family, e.department, e.technical_or_nontechnical, e.seniority, e.first_seen_at, e.last_seen_at, e.posting_status,
            e.duplicate_job_cluster, e.location, e.theme_relevance,
        )
        marks = ",".join("?" for _ in EVENT_COLUMNS)
        self.conn.execute(f"INSERT OR REPLACE INTO normalized_events ({','.join(EVENT_COLUMNS)}) VALUES ({marks})", values)
    def save_health(self, h: ConnectorHealth) -> None:
        self.conn.execute("INSERT INTO connector_health VALUES (?,?,?,?,?)", (h.source_name,h.checked_at,int(h.enabled),h.status,h.coverage_note))

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    @staticmethod
    def _agent_goal_from_row(row: tuple | None) -> dict | None:
        if row is None:
            return None
        keys = (
            "goal_id", "idempotency_key", "goal_type", "lane", "status", "stage",
            "priority", "payload", "result", "error", "cancel_requested", "created_at",
            "updated_at", "deadline_at", "lease_owner", "lease_expires_at",
            "heartbeat_at", "attempt",
        )
        item = dict(zip(keys, row))
        item["payload"] = json.loads(item["payload"] or "{}")
        item["result"] = json.loads(item["result"] or "{}")
        item["cancel_requested"] = bool(item["cancel_requested"])
        return item

    def _agent_goal_row(self, goal_id: str) -> tuple | None:
        return self.conn.execute(
            """SELECT goal_id,idempotency_key,goal_type,lane,status,stage,priority,
            payload_json,result_json,error,cancel_requested,created_at,updated_at,deadline_at,
            lease_owner,lease_expires_at,heartbeat_at,attempt FROM agent_goals WHERE goal_id=?""",
            (goal_id,),
        ).fetchone()

    def _append_agent_event(
        self, goal_id: str, event_type: str, from_status: str, to_status: str,
        created_at: str, safe_summary: str = "", details: dict | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO agent_events
            (goal_id,event_type,from_status,to_status,created_at,safe_summary,details_json)
            VALUES (?,?,?,?,?,?,?)""",
            (goal_id, event_type, from_status, to_status, created_at, safe_summary,
             json.dumps(details or {}, ensure_ascii=False)),
        )

    def create_agent_goal(
        self, *, goal_id: str, idempotency_key: str, goal_type: str, lane: str,
        payload: dict, created_at: str, priority: int = 0, deadline_at: str | None = None,
    ) -> dict:
        if lane not in {"interactive", "background"}:
            raise ValueError(f"Unsupported agent goal lane: {lane}")
        cursor = self.conn.execute(
            """INSERT OR IGNORE INTO agent_goals
            (goal_id,idempotency_key,goal_type,lane,status,stage,priority,payload_json,
             result_json,error,cancel_requested,created_at,updated_at,deadline_at,
             lease_owner,lease_expires_at,heartbeat_at,attempt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (goal_id, idempotency_key, goal_type, lane, "queued", "queued", priority,
             json.dumps(payload, ensure_ascii=False), "{}", "", 0, created_at, created_at,
             deadline_at, "", "", "", 1),
        )
        created = cursor.rowcount == 1
        if created:
            self._append_agent_event(goal_id, "created", "", "queued", created_at)
        row = self.conn.execute(
            """SELECT goal_id,idempotency_key,goal_type,lane,status,stage,priority,
            payload_json,result_json,error,cancel_requested,created_at,updated_at,deadline_at,
            lease_owner,lease_expires_at,heartbeat_at,attempt
            FROM agent_goals WHERE idempotency_key=?""",
            (idempotency_key,),
        ).fetchone()
        self.conn.commit()
        item = self._agent_goal_from_row(row)
        assert item is not None
        if not created:
            item["idempotent_replay"] = True
        return item

    def agent_goal(self, goal_id: str) -> dict | None:
        return self._agent_goal_from_row(self._agent_goal_row(goal_id))

    def agent_goal_events(self, goal_id: str) -> list[dict]:
        rows = self.conn.execute(
            """SELECT event_id,goal_id,event_type,from_status,to_status,created_at,
            safe_summary,details_json FROM agent_events WHERE goal_id=? ORDER BY event_id""",
            (goal_id,),
        ).fetchall()
        keys = ("event_id", "goal_id", "event_type", "from_status", "to_status", "created_at", "safe_summary", "details")
        result = []
        for row in rows:
            item = dict(zip(keys, row))
            item["details"] = json.loads(item["details"] or "{}")
            result.append(item)
        return result

    def active_concurrency_leases(self, now: str, lane: str | None = None) -> list[dict]:
        query = "SELECT lease_id,goal_id,lane,owner,acquired_at,heartbeat_at,expires_at FROM concurrency_leases WHERE expires_at>?"
        params: tuple = (now,)
        if lane is not None:
            query += " AND lane=?"
            params = (now, lane)
        query += " ORDER BY acquired_at,lease_id"
        keys = ("lease_id", "goal_id", "lane", "owner", "acquired_at", "heartbeat_at", "expires_at")
        return [dict(zip(keys, row)) for row in self.conn.execute(query, params)]

    def claim_next_agent_goal(
        self, owner: str, lane: str, now: str, lease_expires_at: str, slot_limit: int,
    ) -> dict | None:
        if lane not in {"interactive", "background"}:
            raise ValueError(f"Unsupported agent goal lane: {lane}")
        if slot_limit < 1:
            return None
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute("DELETE FROM concurrency_leases WHERE expires_at<=?", (now,))
            active = self.conn.execute(
                "SELECT COUNT(*) FROM concurrency_leases WHERE lane=? AND expires_at>?",
                (lane, now),
            ).fetchone()[0]
            if active >= slot_limit:
                self.conn.commit()
                return None
            active_marks = ",".join("?" for _ in AGENT_GOAL_ACTIVE_STATUSES)
            row = self.conn.execute(
                f"""SELECT goal_id,status,attempt FROM agent_goals
                WHERE lane=? AND cancel_requested=0 AND (
                    status='queued' OR (status IN ({active_marks}) AND lease_expires_at<>'' AND lease_expires_at<=?)
                ) ORDER BY priority DESC,created_at,goal_id LIMIT 1""",
                (lane, *AGENT_GOAL_ACTIVE_STATUSES, now),
            ).fetchone()
            if row is None:
                self.conn.commit()
                return None
            goal_id, previous_status, attempt = row
            recovered = previous_status != "queued"
            next_status = previous_status if recovered else "planning"
            next_attempt = attempt + 1 if recovered else attempt
            self.conn.execute(
                """UPDATE agent_goals SET status=?,stage=?,updated_at=?,lease_owner=?,
                lease_expires_at=?,heartbeat_at=?,attempt=? WHERE goal_id=?""",
                (next_status, next_status, now, owner, lease_expires_at, now, next_attempt, goal_id),
            )
            self.conn.execute(
                """INSERT INTO concurrency_leases
                (lease_id,goal_id,lane,owner,acquired_at,heartbeat_at,expires_at)
                VALUES (?,?,?,?,?,?,?)""",
                (goal_id, goal_id, lane, owner, now, now, lease_expires_at),
            )
            self._append_agent_event(
                goal_id, "recovered" if recovered else "claimed", previous_status, next_status,
                now, details={"owner": owner, "attempt": next_attempt},
            )
            self.conn.commit()
            return self.agent_goal(goal_id)
        except Exception:
            self.conn.rollback()
            raise

    def heartbeat_agent_goal(
        self, goal_id: str, owner: str, heartbeat_at: str, lease_expires_at: str,
    ) -> bool:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            updated_goal = self.conn.execute(
                """UPDATE agent_goals SET heartbeat_at=?,lease_expires_at=?,updated_at=?
                WHERE goal_id=? AND lease_owner=? AND status IN ({})""".format(
                    ",".join("?" for _ in AGENT_GOAL_ACTIVE_STATUSES)
                ),
                (heartbeat_at, lease_expires_at, heartbeat_at, goal_id, owner, *AGENT_GOAL_ACTIVE_STATUSES),
            ).rowcount
            updated_lease = self.conn.execute(
                """UPDATE concurrency_leases SET heartbeat_at=?,expires_at=?
                WHERE goal_id=? AND owner=?""",
                (heartbeat_at, lease_expires_at, goal_id, owner),
            ).rowcount
            if updated_goal != 1 or updated_lease != 1:
                self.conn.rollback()
                return False
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            raise

    def request_agent_goal_cancel(self, goal_id: str, now: str, *, reason: str = "") -> dict | None:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self._agent_goal_row(goal_id)
            item = self._agent_goal_from_row(row)
            if item is None:
                self.conn.commit()
                return None
            if item["status"] in AGENT_GOAL_TERMINAL_STATUSES:
                self.conn.commit()
                return item
            if item["status"] == "queued":
                self.conn.execute(
                    """UPDATE agent_goals SET status='cancelled',stage='cancelled',
                    cancel_requested=1,updated_at=? WHERE goal_id=?""",
                    (now, goal_id),
                )
                self._append_agent_event(
                    goal_id, "cancelled", "queued", "cancelled", now,
                    safe_summary=reason, details={"reason": reason},
                )
            else:
                self.conn.execute(
                    "UPDATE agent_goals SET cancel_requested=1,updated_at=? WHERE goal_id=?",
                    (now, goal_id),
                )
                self._append_agent_event(
                    goal_id, "cancel_requested", item["status"], item["status"], now,
                    safe_summary=reason, details={"reason": reason},
                )
            self.conn.commit()
            return self.agent_goal(goal_id)
        except Exception:
            self.conn.rollback()
            raise

    def transition_agent_goal(
        self, goal_id: str, owner: str, to_status: str, now: str, *,
        safe_summary: str = "", result: dict | None = None, error: str = "",
    ) -> dict:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            item = self._agent_goal_from_row(self._agent_goal_row(goal_id))
            if item is None:
                raise KeyError(goal_id)
            if item["lease_owner"] != owner:
                raise ValueError(f"Agent goal lease is not owned by {owner}")
            allowed = AGENT_GOAL_TRANSITIONS.get(item["status"], set())
            if to_status not in allowed:
                raise ValueError(f"Invalid agent goal transition: {item['status']} -> {to_status}")
            terminal = to_status in AGENT_GOAL_TERMINAL_STATUSES
            self.conn.execute(
                """UPDATE agent_goals SET status=?,stage=?,updated_at=?,result_json=?,error=?,
                lease_owner=?,lease_expires_at=?,heartbeat_at=? WHERE goal_id=?""",
                (to_status, to_status, now, json.dumps(result or item["result"], ensure_ascii=False),
                 error, "" if terminal else owner, "" if terminal else item["lease_expires_at"],
                 "" if terminal else item["heartbeat_at"], goal_id),
            )
            if terminal:
                self.conn.execute("DELETE FROM concurrency_leases WHERE goal_id=?", (goal_id,))
            self._append_agent_event(
                goal_id, "transitioned", item["status"], to_status, now,
                safe_summary=safe_summary,
            )
            self.conn.commit()
            updated = self.agent_goal(goal_id)
            assert updated is not None
            return updated
        except Exception:
            self.conn.rollback()
            raise
    def events(self) -> list[dict]:
        cols=[x[0] for x in self.conn.execute("SELECT * FROM normalized_events").description]; return [dict(zip(cols,row)) for row in self.conn.execute("SELECT * FROM normalized_events ORDER BY observed_at DESC")]

    def replace_event(self, event: NormalizedEvent) -> None:
        self.save_event(event)

    def health_records(self) -> list[dict]:
        columns = [item[0] for item in self.conn.execute("SELECT * FROM connector_health").description]
        return [dict(zip(columns, row)) for row in self.conn.execute("SELECT * FROM connector_health ORDER BY checked_at DESC")]

    def raw_text(self, content_hash: str) -> str:
        row = self.conn.execute("SELECT text FROM raw_documents WHERE content_hash=?", (content_hash,)).fetchone()
        return row[0] if row else ""

    def create_research_run(self, run_id: str, theme_id: str, created_at: str, request: dict | None = None, *, status: str = "queued", stage: str = "evidence_selection", database_path: str = "") -> None:
        self.conn.execute(
            """INSERT INTO research_runs
            (run_id,theme_id,status,stage,created_at,updated_at,result_json,error,request_json,progress,review_gate,attempt,parent_run_id,database_path,lease_owner,lease_expires_at,heartbeat_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, theme_id, status, stage, created_at, created_at, "{}", "", json.dumps(request or {}, ensure_ascii=False), 0, "", 1, "", database_path, "", "", ""),
        ); self.commit()

    def enqueue_theme_research_run(
        self, run_id: str, theme_id: str, created_at: str, request: dict,
        *, database_path: str = "",
    ) -> str:
        """Create a run without allowing it to overtake an existing FIFO waiter."""
        marks = ",".join("?" for _ in RESEARCH_EXECUTION_STATUSES)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            active = self.conn.execute(
                f"""SELECT run_id FROM research_runs
                WHERE status IN ({marks})
                  AND theme_id NOT LIKE 'event:%' AND theme_id NOT LIKE 'report-refresh:%'
                LIMIT 1""",
                RESEARCH_EXECUTION_STATUSES,
            ).fetchone()
            waiting = self.conn.execute(
                """SELECT run_id FROM research_runs
                WHERE status='waiting'
                  AND theme_id NOT LIKE 'event:%' AND theme_id NOT LIKE 'report-refresh:%'
                ORDER BY queue_position,created_at LIMIT 1"""
            ).fetchone()
            if not active and waiting:
                self._activate_waiter(str(waiting[0]), created_at)
                self._normalize_waiting_positions()
                active = waiting
            status = "waiting" if active else "planning"
            stage = "planning"
            queue_position = self._next_waiting_position() if active else None
            self.conn.execute(
                """INSERT INTO research_runs
                (run_id,theme_id,status,stage,created_at,updated_at,result_json,error,request_json,
                 progress,review_gate,attempt,parent_run_id,database_path,lease_owner,
                 lease_expires_at,heartbeat_at,queue_position)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, theme_id, status, stage, created_at, created_at, "{}", "",
                    json.dumps(request, ensure_ascii=False), 0, "", 1, "", database_path,
                    "", "", "", queue_position,
                ),
            )
            self.conn.commit()
            return status
        except Exception:
            self.conn.rollback()
            raise

    def create_event_research_run(self, run_id: str, evidence_id: str, created_at: str, *, database_path: str = "") -> None:
        self.create_research_run(run_id, f"event:{evidence_id}", created_at, {"evidence_id": evidence_id, "database_path": database_path}, status="queued", stage="source_verification", database_path=database_path)

    def update_research_run(self, run_id: str, *, status: str, stage: str, updated_at: str, result: dict | None = None, error: str = "", progress: int | None = None, review_gate: str | None = None) -> None:
        current = self.research_run(run_id)
        if not current: return
        self.conn.execute(
            "UPDATE research_runs SET status=?,stage=?,updated_at=?,result_json=?,error=?,progress=?,review_gate=? WHERE run_id=?",
            (status, stage, updated_at, json.dumps(result if result is not None else current["result"], ensure_ascii=False), error, current["progress"] if progress is None else progress, current["review_gate"] if review_gate is None else review_gate, run_id),
        ); self.commit()

    def research_run(self, run_id: str) -> dict | None:
        row = self.conn.execute("SELECT run_id,theme_id,status,stage,created_at,updated_at,result_json,error,request_json,progress,review_gate,attempt,parent_run_id,database_path,lease_owner,lease_expires_at,heartbeat_at,queue_position FROM research_runs WHERE run_id=?", (run_id,)).fetchone()
        if not row: return None
        keys = ("run_id", "theme_id", "status", "stage", "created_at", "updated_at", "result", "error", "request", "progress", "review_gate", "attempt", "parent_run_id", "database_path", "lease_owner", "lease_expires_at", "heartbeat_at", "queue_position")
        data = dict(zip(keys, row)); data["result"] = json.loads(data["result"]); data["request"] = json.loads(data["request"]); return data

    def research_runs(self, limit: int = 50) -> list[dict]:
        ids = [row[0] for row in self.conn.execute("SELECT run_id FROM research_runs ORDER BY updated_at DESC LIMIT ?", (limit,))]
        return [item for run_id in ids if (item := self.research_run(run_id))]

    def paginated_research_runs(self, *, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        where = "theme_id NOT LIKE 'event:%' AND theme_id NOT LIKE 'report-refresh:%'"
        total = int(self.conn.execute(f"SELECT COUNT(*) FROM research_runs WHERE {where}").fetchone()[0])
        ids = [
            row[0] for row in self.conn.execute(
                f"""SELECT run_id FROM research_runs WHERE {where}
                ORDER BY CASE status
                    WHEN 'planning' THEN 0 WHEN 'queued' THEN 0 WHEN 'collecting' THEN 0
                    WHEN 'governing' THEN 0 WHEN 'analyzing' THEN 0 WHEN 'auditing' THEN 0
                    WHEN 'waiting' THEN 1 WHEN 'awaiting_theme_review' THEN 2
                    WHEN 'awaiting_report_review' THEN 2 WHEN 'returned' THEN 2
                    WHEN 'blocked_configuration' THEN 2 ELSE 3 END,
                    CASE WHEN status='waiting' THEN queue_position END,
                    updated_at DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            )
        ]
        return [item for run_id in ids if (item := self.research_run(run_id))], total

    def promote_waiting_run(self, updated_at: str) -> str | None:
        """Promote the oldest waiting run iff the active slot is free."""
        marks = ",".join("?" for _ in RESEARCH_EXECUTION_STATUSES)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            active = self.conn.execute(
                f"""SELECT 1 FROM research_runs WHERE status IN ({marks})
                AND theme_id NOT LIKE 'event:%' AND theme_id NOT LIKE 'report-refresh:%' LIMIT 1""",
                RESEARCH_EXECUTION_STATUSES,
            ).fetchone()
            if active:
                self.conn.commit()
                return None
            waiting = self.conn.execute(
                """SELECT run_id FROM research_runs WHERE status='waiting'
                AND theme_id NOT LIKE 'event:%' AND theme_id NOT LIKE 'report-refresh:%'
                ORDER BY queue_position,created_at LIMIT 1"""
            ).fetchone()
            if not waiting:
                self.conn.commit()
                return None
            self._activate_waiter(str(waiting[0]), updated_at)
            self._normalize_waiting_positions()
            self.conn.commit()
            return str(waiting[0])
        except Exception:
            self.conn.rollback()
            raise

    def transition_and_promote(
        self, run_id: str, expected_statuses: set[str], *, promote: bool = False,
        **values: object,
    ) -> tuple[bool, str | None]:
        """CAS a run and optionally promote the waiter in the same transaction."""
        if not expected_statuses:
            return False, None
        allowed = {"status", "stage", "updated_at", "result_json", "error", "progress", "review_gate", "attempt", "lease_owner", "lease_expires_at", "heartbeat_at", "queue_position"}
        updates = {key: value for key, value in values.items() if key in allowed}
        if "result" in values:
            updates["result_json"] = json.dumps(values["result"], ensure_ascii=False)
        marks = ",".join("?" for _ in expected_statuses)
        assignments = ",".join(f"{key}=?" for key in updates)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = self.conn.execute(
                f"UPDATE research_runs SET {assignments} WHERE run_id=? AND status IN ({marks})",
                (*updates.values(), run_id, *sorted(expected_statuses)),
            )
            promoted = None
            if cursor.rowcount == 1:
                if promote:
                    promoted = self._promote_waiter_if_idle(str(values.get("updated_at") or utcnow()))
                self._normalize_waiting_positions()
            self.conn.commit()
            return cursor.rowcount == 1, promoted
        except Exception:
            self.conn.rollback()
            raise

    def requeue_research_run(
        self, run_id: str, expected_statuses: set[str], *, stage_after_promotion: str,
        **values: object,
    ) -> tuple[bool, str | None]:
        """Append an existing run to FIFO, then immediately promote the head if idle."""
        if not expected_statuses:
            return False, None
        allowed = {"updated_at", "result_json", "error", "progress", "review_gate", "attempt", "lease_owner", "lease_expires_at", "heartbeat_at"}
        updates = {key: value for key, value in values.items() if key in allowed}
        if "result" in values:
            updates["result_json"] = json.dumps(values["result"], ensure_ascii=False)
        updates.update({
            "status": "waiting", "stage": stage_after_promotion,
            "queue_position": 0,
        })
        marks = ",".join("?" for _ in expected_statuses)
        assignments = ",".join(f"{key}=?" for key in updates)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            # Recompute after the write lock is held so concurrent reviews keep FIFO order.
            updates["queue_position"] = self._next_waiting_position()
            cursor = self.conn.execute(
                f"UPDATE research_runs SET {assignments} WHERE run_id=? AND status IN ({marks})",
                (*updates.values(), run_id, *sorted(expected_statuses)),
            )
            promoted = self._promote_waiter_if_idle(str(values.get("updated_at") or utcnow())) if cursor.rowcount == 1 else None
            self._normalize_waiting_positions()
            self.conn.commit()
            return cursor.rowcount == 1, promoted
        except Exception:
            self.conn.rollback()
            raise

    def _next_waiting_position(self) -> int:
        row = self.conn.execute(
            """SELECT COALESCE(MAX(queue_position),0) FROM research_runs
            WHERE status='waiting' AND theme_id NOT LIKE 'event:%' AND theme_id NOT LIKE 'report-refresh:%'"""
        ).fetchone()
        return int(row[0] or 0) + 1

    def _promote_waiter_if_idle(self, updated_at: str) -> str | None:
        marks = ",".join("?" for _ in RESEARCH_EXECUTION_STATUSES)
        active = self.conn.execute(
            f"""SELECT 1 FROM research_runs WHERE status IN ({marks})
            AND theme_id NOT LIKE 'event:%' AND theme_id NOT LIKE 'report-refresh:%' LIMIT 1""",
            RESEARCH_EXECUTION_STATUSES,
        ).fetchone()
        if active:
            return None
        waiting = self.conn.execute(
            """SELECT run_id FROM research_runs WHERE status='waiting'
            AND theme_id NOT LIKE 'event:%' AND theme_id NOT LIKE 'report-refresh:%'
            ORDER BY queue_position,created_at LIMIT 1"""
        ).fetchone()
        if not waiting:
            return None
        self._activate_waiter(str(waiting[0]), updated_at)
        return str(waiting[0])

    def _activate_waiter(self, run_id: str, updated_at: str) -> None:
        row = self.conn.execute(
            "SELECT stage FROM research_runs WHERE run_id=? AND status='waiting'",
            (run_id,),
        ).fetchone()
        resume_stage = str(row[0]) if row and str(row[0]) in RESEARCH_EXECUTION_STATUSES else "planning"
        self.conn.execute(
            """UPDATE research_runs SET status=?,stage=?,queue_position=NULL,updated_at=?
            WHERE run_id=? AND status='waiting'""",
            (resume_stage, resume_stage, updated_at, run_id),
        )

    def _normalize_waiting_positions(self) -> None:
        rows = self.conn.execute(
            """SELECT run_id FROM research_runs WHERE status='waiting'
            AND theme_id NOT LIKE 'event:%' AND theme_id NOT LIKE 'report-refresh:%'
            ORDER BY queue_position,created_at"""
        ).fetchall()
        for position, row in enumerate(rows, start=1):
            self.conn.execute(
                "UPDATE research_runs SET queue_position=? WHERE run_id=?",
                (position, row[0]),
            )

    def register_run(self, run_id: str, database_path: str, created_at: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO run_registry(run_id,database_path,created_at) VALUES (?,?,?)",
            (run_id, database_path, created_at),
        )
        self.commit()

    def registered_run_path(self, run_id: str) -> str | None:
        row = self.conn.execute("SELECT database_path FROM run_registry WHERE run_id=?", (run_id,)).fetchone()
        return str(row[0]) if row else None

    def save_theme_definition(self, definition: dict, created_at: str, *, confirmed: bool = True) -> None:
        theme_id = str(definition["theme_id"])
        self.conn.execute(
            """INSERT INTO themes(theme_id,name,description,status,created_at,updated_at) VALUES (?,?,?,?,?,?)
            ON CONFLICT(theme_id) DO UPDATE SET name=excluded.name,description=excluded.description,status=excluded.status,updated_at=excluded.updated_at""",
            (theme_id, definition.get("name", theme_id), definition.get("description", ""), "confirmed" if confirmed else "draft", created_at, created_at),
        )
        aliases = set(definition.get("aliases", [])) | set(definition.get("include_terms", []))
        for alias in aliases:
            if str(alias).strip():
                self.conn.execute(
                    "INSERT OR REPLACE INTO theme_aliases(theme_id,alias,alias_type,confirmed,created_at) VALUES (?,?,?,?,?)",
                    (theme_id, str(alias).strip(), "research", int(confirmed), created_at),
                )
        self.commit()

    def theme_definitions(self) -> list[dict]:
        columns = ("theme_id", "name", "description", "status", "created_at", "updated_at")
        result = [dict(zip(columns, row)) for row in self.conn.execute("SELECT theme_id,name,description,status,created_at,updated_at FROM themes ORDER BY updated_at DESC")]
        for item in result:
            item["aliases"] = [row[0] for row in self.conn.execute("SELECT alias FROM theme_aliases WHERE theme_id=? ORDER BY alias", (item["theme_id"],))]
        return result

    def save_theme_snapshot(self, item: dict) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO theme_snapshots
            (snapshot_id,theme_id,as_of_date,metrics_json,score,confidence,evidence_count,source_type_count,trend,trend_reason,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (item["snapshot_id"], item["theme_id"], item["as_of_date"], json.dumps(item.get("metrics", {}), ensure_ascii=False), item["score"], item["confidence"], item["evidence_count"], item["source_type_count"], item["trend"], item["trend_reason"], item["created_at"]),
        )
        self.commit()

    def theme_snapshots(self, theme_id: str | None = None) -> list[dict]:
        query = "SELECT snapshot_id,theme_id,as_of_date,metrics_json,score,confidence,evidence_count,source_type_count,trend,trend_reason,created_at FROM theme_snapshots"
        params: tuple = ()
        if theme_id:
            query += " WHERE theme_id=?"
            params = (theme_id,)
        query += " ORDER BY as_of_date DESC,created_at DESC"
        keys = ("snapshot_id", "theme_id", "as_of_date", "metrics", "score", "confidence", "evidence_count", "source_type_count", "trend", "trend_reason", "created_at")
        result = [dict(zip(keys, row)) for row in self.conn.execute(query, params)]
        for item in result:
            item["metrics"] = json.loads(item["metrics"] or "{}")
        return result

    def save_theme_candidate(self, item: dict) -> None:
        """Upsert a governed candidate while preserving its review terminal state."""
        existing = self.conn.execute(
            "SELECT status,created_at FROM theme_candidates WHERE candidate_id=?",
            (item["candidate_id"],),
        ).fetchone()
        if existing and existing[0] in {"confirmed", "merged", "rejected"}:
            return
        status = str(item["status"])
        created_at = str(existing[1]) if existing else str(item["created_at"])
        self.conn.execute(
            """INSERT INTO theme_candidates
            (candidate_id,proposed_name,description,status,signature,window_start,window_end,
             first_seen_at,last_seen_at,metrics_json,rationale,merged_theme_id,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(candidate_id) DO UPDATE SET
              proposed_name=excluded.proposed_name,description=excluded.description,
              status=excluded.status,window_start=excluded.window_start,window_end=excluded.window_end,
              first_seen_at=excluded.first_seen_at,last_seen_at=excluded.last_seen_at,
              metrics_json=excluded.metrics_json,rationale=excluded.rationale,updated_at=excluded.updated_at""",
            (
                item["candidate_id"], item["proposed_name"], item.get("description", ""), status,
                item["signature"], item.get("window_start", ""), item.get("window_end", ""),
                item.get("first_seen_at", ""), item.get("last_seen_at", ""),
                json.dumps(item.get("metrics", {}), ensure_ascii=False), item.get("rationale", ""),
                item.get("merged_theme_id", ""), created_at, item["updated_at"],
            ),
        )
        candidate_id = str(item["candidate_id"])
        self.conn.execute("DELETE FROM candidate_evidence WHERE candidate_id=?", (candidate_id,))
        self.conn.execute("DELETE FROM candidate_entities WHERE candidate_id=?", (candidate_id,))
        self.conn.execute("DELETE FROM candidate_aliases WHERE candidate_id=?", (candidate_id,))
        for evidence in item.get("evidence", []):
            self.conn.execute(
                "INSERT OR IGNORE INTO candidate_evidence(candidate_id,event_id,relevance,added_at) VALUES (?,?,?,?)",
                (candidate_id, str(evidence["event_id"]), float(evidence.get("relevance", 0)), item["updated_at"]),
            )
        for entity in item.get("entities", []):
            self.conn.execute(
                """INSERT INTO candidate_entities(candidate_id,entity_key,label,entity_type,mention_count)
                VALUES (?,?,?,?,?) ON CONFLICT(candidate_id,entity_key) DO UPDATE SET
                label=excluded.label,entity_type=excluded.entity_type,mention_count=excluded.mention_count""",
                (
                    candidate_id, str(entity["entity_key"]), str(entity["label"]),
                    str(entity.get("entity_type", "company")), int(entity.get("mention_count", 1)),
                ),
            )
        for alias in item.get("aliases", []):
            if str(alias).strip():
                self.conn.execute(
                    "INSERT OR IGNORE INTO candidate_aliases(candidate_id,alias,confirmed,created_at) VALUES (?,?,0,?)",
                    (candidate_id, str(alias).strip(), item["updated_at"]),
                )
        self.commit()

    def theme_candidate(self, candidate_id: str) -> dict | None:
        keys = (
            "candidate_id", "proposed_name", "description", "status", "signature",
            "window_start", "window_end", "first_seen_at", "last_seen_at", "metrics",
            "rationale", "merged_theme_id", "created_at", "updated_at",
        )
        row = self.conn.execute(
            """SELECT candidate_id,proposed_name,description,status,signature,window_start,window_end,
            first_seen_at,last_seen_at,metrics_json,rationale,merged_theme_id,created_at,updated_at
            FROM theme_candidates WHERE candidate_id=?""",
            (candidate_id,),
        ).fetchone()
        if not row:
            return None
        item = dict(zip(keys, row))
        item["metrics"] = json.loads(item["metrics"] or "{}")
        item["aliases"] = [row[0] for row in self.conn.execute(
            "SELECT alias FROM candidate_aliases WHERE candidate_id=? ORDER BY alias", (candidate_id,)
        )]
        entity_keys = ("entity_key", "label", "entity_type", "mention_count")
        item["entities"] = [dict(zip(entity_keys, row)) for row in self.conn.execute(
            "SELECT entity_key,label,entity_type,mention_count FROM candidate_entities WHERE candidate_id=? ORDER BY mention_count DESC,label",
            (candidate_id,),
        )]
        event_ids = [row[0] for row in self.conn.execute(
            "SELECT event_id FROM candidate_evidence WHERE candidate_id=? ORDER BY relevance DESC,event_id", (candidate_id,)
        )]
        item["evidence"] = [event for event_id in event_ids if (event := self.event(event_id))]
        return item

    def theme_candidates(self, status: str | None = None, limit: int = 100) -> list[dict]:
        query = "SELECT candidate_id FROM theme_candidates"
        params: tuple = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params = (*params, limit)
        return [item for row in self.conn.execute(query, params) if (item := self.theme_candidate(str(row[0])))]

    def event(self, event_id: str) -> dict | None:
        columns = [item[0] for item in self.conn.execute("SELECT * FROM normalized_events LIMIT 0").description]
        row = self.conn.execute("SELECT * FROM normalized_events WHERE event_id=?", (event_id,)).fetchone()
        return dict(zip(columns, row)) if row else None

    def review_theme_candidate(
        self, candidate_id: str, decision: str, updated_at: str,
        *, target_theme_id: str = "", note: str = "",
    ) -> dict | None:
        """Atomically confirm, merge or reject a candidate and its evidence assignments."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT proposed_name,description,status FROM theme_candidates WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
            if not row or str(row[2]) in {"confirmed", "merged", "rejected"}:
                self.conn.rollback()
                return None
            aliases = [str(item[0]) for item in self.conn.execute(
                "SELECT alias FROM candidate_aliases WHERE candidate_id=?", (candidate_id,)
            )]
            if decision == "confirm":
                theme_id = target_theme_id or candidate_id.removeprefix("candidate:")
                exists = self.conn.execute("SELECT 1 FROM themes WHERE theme_id=?", (theme_id,)).fetchone()
                if exists:
                    raise ValueError("theme_id 已存在，请改用 merge")
                self.conn.execute(
                    "INSERT INTO themes(theme_id,name,description,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                    (theme_id, str(row[0]), str(row[1] or ""), "confirmed", updated_at, updated_at),
                )
                aliases.append(str(row[0]))
                final_status = "confirmed"
            elif decision == "merge":
                theme_id = target_theme_id
                if not theme_id or not self.conn.execute(
                    "SELECT 1 FROM themes WHERE theme_id=? AND status='confirmed'", (theme_id,)
                ).fetchone():
                    raise ValueError("merge 需要有效的已确认 target_theme_id")
                final_status = "merged"
            elif decision == "reject":
                theme_id = ""
                final_status = "rejected"
            else:
                raise ValueError("不支持的候选复核决定")
            if theme_id:
                for alias in dict.fromkeys(aliases):
                    if alias.strip():
                        self.conn.execute(
                            "INSERT OR REPLACE INTO theme_aliases(theme_id,alias,alias_type,confirmed,created_at) VALUES (?,?,?,?,?)",
                            (theme_id, alias.strip(), "discovery", 1, updated_at),
                        )
                event_ids = [item[0] for item in self.conn.execute(
                    "SELECT event_id FROM candidate_evidence WHERE candidate_id=?", (candidate_id,)
                )]
                for event_id in event_ids:
                    self.conn.execute(
                        """UPDATE normalized_events SET relevance_status='relevant',theme_assignment_status='assigned',
                        primary_theme=?,themes=?,classification_reasons=?,classification_confidence=MAX(classification_confidence,0.75),theme_relevance=MAX(theme_relevance,0.75)
                        WHERE event_id=?""",
                        (theme_id, json.dumps([theme_id], ensure_ascii=False), json.dumps([f"人工确认候选主题：{candidate_id}"], ensure_ascii=False), event_id),
                    )
            self.conn.execute(
                "UPDATE theme_candidates SET status=?,merged_theme_id=?,rationale=?,updated_at=? WHERE candidate_id=?",
                (final_status, theme_id if decision == "merge" else "", note, updated_at, candidate_id),
            )
            self.conn.commit()
            return {"candidate_id": candidate_id, "status": final_status, "theme_id": theme_id}
        except Exception:
            self.conn.rollback()
            raise

    def create_discovery_run(self, item: dict) -> bool:
        cursor = self.conn.execute(
            """INSERT OR IGNORE INTO discovery_runs
            (discovery_run_id,idempotency_key,run_kind,status,stage,window_start,window_end,created_at,updated_at,result_json,error,lease_owner,lease_expires_at,heartbeat_at,attempt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item["discovery_run_id"], item["idempotency_key"], item.get("run_kind", "daily"),
                item.get("status", "queued"), item.get("stage", "queued"), item.get("window_start", ""),
                item.get("window_end", ""), item["created_at"], item["created_at"], "{}", "", "", "", "", 1,
            ),
        )
        self.commit()
        return cursor.rowcount == 1

    def update_discovery_run(self, discovery_run_id: str, *, status: str, stage: str, updated_at: str, result: dict | None = None, error: str = "") -> None:
        self.conn.execute(
            "UPDATE discovery_runs SET status=?,stage=?,updated_at=?,result_json=?,error=? WHERE discovery_run_id=?",
            (status, stage, updated_at, json.dumps(result or {}, ensure_ascii=False), error, discovery_run_id),
        )
        self.commit()

    def discovery_runs(self, limit: int = 20) -> list[dict]:
        keys = ("discovery_run_id", "idempotency_key", "run_kind", "status", "stage", "window_start", "window_end", "created_at", "updated_at", "result", "error", "lease_owner", "lease_expires_at", "heartbeat_at", "attempt")
        rows = self.conn.execute(
            """SELECT discovery_run_id,idempotency_key,run_kind,status,stage,window_start,window_end,
            created_at,updated_at,result_json,error,lease_owner,lease_expires_at,heartbeat_at,attempt
            FROM discovery_runs ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        )
        result = [dict(zip(keys, row)) for row in rows]
        for item in result:
            item["result"] = json.loads(item["result"] or "{}")
        return result

    def claim_next_discovery_run(self, owner: str, now: str, lease_expires_at: str) -> dict | None:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                """SELECT discovery_run_id FROM discovery_runs
                WHERE status='queued' OR (status='running' AND lease_expires_at<>'' AND lease_expires_at<?)
                ORDER BY created_at LIMIT 1""", (now,),
            ).fetchone()
            if not row:
                self.conn.rollback(); return None
            self.conn.execute(
                """UPDATE discovery_runs SET status='running',stage='clustering',lease_owner=?,lease_expires_at=?,heartbeat_at=?,updated_at=?,attempt=CASE WHEN status='running' THEN attempt+1 ELSE attempt END
                WHERE discovery_run_id=?""", (owner,lease_expires_at,now,now,row[0]),
            )
            self.conn.commit()
            return next((item for item in self.discovery_runs(100) if item["discovery_run_id"] == row[0]), None)
        except Exception:
            self.conn.rollback(); raise

    def save_entity(self, item: dict) -> None:
        self.conn.execute(
            """INSERT INTO entities(entity_id,entity_type,canonical_name,ticker,exchange,review_status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(entity_id) DO UPDATE SET canonical_name=excluded.canonical_name,ticker=excluded.ticker,updated_at=excluded.updated_at""",
            (item["entity_id"], item["entity_type"], item["canonical_name"], item.get("ticker", ""), item.get("exchange", "unknown"), item.get("review_status", "needs_review"), item["created_at"], item["updated_at"]),
        )
        for alias in item.get("aliases", []):
            self.conn.execute("INSERT OR IGNORE INTO entity_aliases(entity_id,alias) VALUES (?,?)", (item["entity_id"], alias))
        self.commit()

    def save_entity_link(self, item: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO entity_links(link_id,entity_id,event_id,theme_id,relation_type,confidence,review_status,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (item["link_id"], item["entity_id"], item["event_id"], item["theme_id"], item.get("relation_type", "mentioned"), item.get("confidence", 0.5), item.get("review_status", "needs_review"), item["created_at"]),
        )
        self.commit()

    def save_entities_and_links(self, entities: list[dict], links: list[dict]) -> None:
        """Upsert a complete entity-resolution batch in one short transaction."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.executemany(
                """INSERT INTO entities(entity_id,entity_type,canonical_name,ticker,exchange,review_status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(entity_id) DO UPDATE SET
                entity_type=excluded.entity_type,canonical_name=excluded.canonical_name,
                ticker=excluded.ticker,exchange=excluded.exchange,updated_at=excluded.updated_at""",
                [
                    (
                        item["entity_id"], item["entity_type"], item["canonical_name"],
                        item.get("ticker", ""), item.get("exchange", "unknown"),
                        item.get("review_status", "needs_review"), item["created_at"], item["updated_at"],
                    )
                    for item in entities
                ],
            )
            self.conn.executemany(
                "INSERT OR IGNORE INTO entity_aliases(entity_id,alias) VALUES (?,?)",
                [
                    (item["entity_id"], str(alias))
                    for item in entities for alias in item.get("aliases", []) if str(alias).strip()
                ],
            )
            self.conn.executemany(
                """INSERT OR REPLACE INTO entity_links
                (link_id,entity_id,event_id,theme_id,relation_type,confidence,review_status,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                [
                    (
                        item["link_id"], item["entity_id"], item["event_id"], item["theme_id"],
                        item.get("relation_type", "mentioned"), item.get("confidence", 0.5),
                        item.get("review_status", "needs_review"), item["created_at"],
                    )
                    for item in links
                ],
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def entities(self, review_status: str | None = None) -> list[dict]:
        query = "SELECT entity_id,entity_type,canonical_name,ticker,exchange,review_status,created_at,updated_at FROM entities"
        params: tuple = ()
        if review_status:
            query += " WHERE review_status=?"; params = (review_status,)
        keys = ("entity_id", "entity_type", "canonical_name", "ticker", "exchange", "review_status", "created_at", "updated_at")
        return [dict(zip(keys, row)) for row in self.conn.execute(query + " ORDER BY updated_at DESC", params)]

    def review_entity(self, entity_id: str, decision: str, updated_at: str) -> bool:
        cursor = self.conn.execute(
            "UPDATE entities SET review_status=?,updated_at=? WHERE entity_id=?",
            (decision, updated_at, entity_id),
        )
        self.commit()
        return cursor.rowcount == 1

    def save_report_version(self, report_id: str, version: int, payload: dict, markdown: str, created_at: str) -> None:
        from hashlib import sha256
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.conn.execute(
            "INSERT OR IGNORE INTO report_versions(report_id,version,content_hash,payload_json,markdown,created_at) VALUES (?,?,?,?,?,?)",
            (report_id, version, sha256((serialized + markdown).encode("utf-8")).hexdigest(), serialized, markdown, created_at),
        )
        self.commit()

    def promote_report_version(self, report_id: str, version: int, updated_at: str) -> None:
        self.conn.execute(
            "UPDATE report_assets SET version=?,updated_at=? WHERE report_id=? AND deleted_at IS NULL",
            (version, updated_at, report_id),
        )
        self.commit()

    def save_and_promote_report_version(
        self, report_id: str, version: int, payload: dict, markdown: str,
        created_at: str, claims: list[dict],
    ) -> bool:
        """Atomically append an immutable version, clone its claims, and promote the asset."""
        from hashlib import sha256
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            cursor = self.conn.execute(
                "INSERT OR IGNORE INTO report_versions(report_id,version,content_hash,payload_json,markdown,created_at) VALUES (?,?,?,?,?,?)",
                (report_id, version, sha256((serialized + markdown).encode("utf-8")).hexdigest(), serialized, markdown, created_at),
            )
            if cursor.rowcount != 1:
                self.conn.rollback()
                return False
            for index, claim in enumerate(claims, 1):
                claim_id = f"{report_id}:v{version}:c{index}"
                claim_type = str(claim.get("claim_type") or claim.get("type") or "support")
                self.conn.execute(
                    "INSERT INTO report_claims(claim_id,report_id,version,claim_text,claim_type,created_at) VALUES (?,?,?,?,?,?)",
                    (claim_id, report_id, version, str(claim.get("claim_text") or claim.get("text") or ""), claim_type, created_at),
                )
                relation = "contradicts" if claim_type == "counter" else "supports"
                for event_id in claim.get("evidence_ids") or []:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO report_claim_evidence(claim_id,event_id,relation) VALUES (?,?,?)",
                        (claim_id, str(event_id), relation),
                    )
            asset = payload.get("asset") or {}
            promoted = self.conn.execute(
                """UPDATE report_assets SET
                run_id=?,title=?,kind=?,theme_id=?,folder_id=?,status=?,tags=?,summary=?,
                updated_at=?,version=?,source_count=?,evidence_count=?,audit_passed=?
                WHERE report_id=? AND deleted_at IS NULL""",
                (
                    asset.get("run_id", ""), asset.get("title", ""),
                    asset.get("kind", "theme_report"), asset.get("theme_id", "unknown"),
                    asset.get("folder_id", "ai"), asset.get("status", "completed"),
                    json.dumps(asset.get("tags", []), ensure_ascii=False), asset.get("summary", ""),
                    created_at, version, int(asset.get("source_count", 0)),
                    int(asset.get("evidence_count", 0)), int(bool(asset.get("audit_passed", False))),
                    report_id,
                ),
            )
            if promoted.rowcount != 1:
                raise ValueError("报告资产不存在或已删除")
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            raise

    def report_versions(self, report_id: str) -> list[dict]:
        keys = ("report_id", "version", "content_hash", "payload", "markdown", "created_at")
        result = [dict(zip(keys, row)) for row in self.conn.execute(
            "SELECT report_id,version,content_hash,payload_json,markdown,created_at FROM report_versions WHERE report_id=? ORDER BY version DESC",
            (report_id,),
        )]
        for item in result:
            item["payload"] = json.loads(item["payload"] or "{}")
        return result

    def save_report_claim(self, claim_id: str, report_id: str, version: int, claim_text: str, claim_type: str, evidence_ids: list[str], created_at: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO report_claims(claim_id,report_id,version,claim_text,claim_type,created_at) VALUES (?,?,?,?,?,?)",
            (claim_id, report_id, version, claim_text, claim_type, created_at),
        )
        for event_id in evidence_ids:
            self.conn.execute(
                "INSERT OR IGNORE INTO report_claim_evidence(claim_id,event_id,relation) VALUES (?,?,?)",
                (claim_id, event_id, "supports" if claim_type != "counter" else "contradicts"),
            )
        self.commit()

    def report_claims(self, report_id: str, version: int | None = None) -> list[dict]:
        query = "SELECT claim_id,report_id,version,claim_text,claim_type,created_at FROM report_claims WHERE report_id=?"
        params: tuple = (report_id,)
        if version is not None:
            query += " AND version=?"; params = (report_id, version)
        keys = ("claim_id", "report_id", "version", "claim_text", "claim_type", "created_at")
        result = [dict(zip(keys, row)) for row in self.conn.execute(query + " ORDER BY claim_id", params)]
        for item in result:
            item["evidence_ids"] = [row[0] for row in self.conn.execute("SELECT event_id FROM report_claim_evidence WHERE claim_id=? ORDER BY event_id", (item["claim_id"],))]
        return result

    def create_sync_run(self, sync_run_id: str, created_at: str, *, days: int = 7, idempotency_key: str = "") -> bool:
        cursor = self.conn.execute(
            """INSERT OR IGNORE INTO sync_runs
            (sync_run_id,status,progress,current_source,created_at,updated_at,result_json,error,cancel_requested,days,idempotency_key,lease_owner,lease_expires_at,heartbeat_at,attempt)
            VALUES (?,?,?,?,?,?,?,?,0,?,?,?,?,?,1)""",
            (sync_run_id,"queued",0,"",created_at,created_at,"{}","",days,idempotency_key,"","",""),
        )
        self.commit()
        return cursor.rowcount == 1

    def update_sync_run(self, sync_run_id: str, *, status: str, progress: int, updated_at: str, current_source: str = "", result: dict | None = None, error: str = "") -> None:
        self.conn.execute("UPDATE sync_runs SET status=?,progress=?,current_source=?,updated_at=?,result_json=?,error=? WHERE sync_run_id=?", (status,progress,current_source,updated_at,json.dumps(result or {},ensure_ascii=False),error,sync_run_id))
        self.commit()

    def sync_run(self, sync_run_id: str) -> dict | None:
        keys=("sync_run_id","status","progress","current_source","created_at","updated_at","result","error","cancel_requested","days","idempotency_key","lease_owner","lease_expires_at","heartbeat_at","attempt")
        row=self.conn.execute("SELECT sync_run_id,status,progress,current_source,created_at,updated_at,result_json,error,cancel_requested,days,idempotency_key,lease_owner,lease_expires_at,heartbeat_at,attempt FROM sync_runs WHERE sync_run_id=?",(sync_run_id,)).fetchone()
        if not row: return None
        item=dict(zip(keys,row)); item["result"]=json.loads(item["result"] or "{}"); item["cancel_requested"]=bool(item["cancel_requested"]); return item

    def sync_runs(self, limit: int = 10) -> list[dict]:
        ids=[row[0] for row in self.conn.execute("SELECT sync_run_id FROM sync_runs ORDER BY created_at DESC LIMIT ?",(limit,))]
        return [item for sync_run_id in ids if (item:=self.sync_run(sync_run_id))]

    def active_etf_preview_sync_run(self) -> dict | None:
        row = self.conn.execute(
            """SELECT sync_run_id FROM sync_runs
            WHERE idempotency_key LIKE 'etf-preview:%' AND status IN ('queued','running')
            ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
        return self.sync_run(str(row[0])) if row else None

    def request_sync_cancel(self, sync_run_id: str) -> bool:
        cursor=self.conn.execute("UPDATE sync_runs SET cancel_requested=1,updated_at=? WHERE sync_run_id=? AND status IN ('queued','running')",(utcnow(),sync_run_id))
        self.commit(); return cursor.rowcount==1

    def claim_next_sync_run(self, owner: str, now: str, lease_expires_at: str) -> dict | None:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                """SELECT sync_run_id FROM sync_runs
                WHERE cancel_requested=0 AND (status='queued' OR (status='running' AND lease_expires_at<>'' AND lease_expires_at<?))
                ORDER BY CASE WHEN idempotency_key LIKE 'etf-preview:%' THEN 0 ELSE 1 END,
                         created_at LIMIT 1""", (now,),
            ).fetchone()
            if not row:
                self.conn.rollback()
                return None
            self.conn.execute(
                """UPDATE sync_runs SET status='running',lease_owner=?,lease_expires_at=?,heartbeat_at=?,updated_at=?,attempt=CASE WHEN status='running' THEN attempt+1 ELSE attempt END
                WHERE sync_run_id=?""", (owner,lease_expires_at,now,now,row[0]),
            )
            self.conn.commit()
            return self.sync_run(str(row[0]))
        except Exception:
            self.conn.rollback()
            raise

    def heartbeat_sync_run(self, sync_run_id: str, owner: str, now: str, lease_expires_at: str) -> bool:
        cursor = self.conn.execute(
            "UPDATE sync_runs SET heartbeat_at=?,lease_expires_at=?,updated_at=? WHERE sync_run_id=? AND status='running' AND lease_owner=?",
            (now,lease_expires_at,now,sync_run_id,owner),
        )
        self.commit()
        return cursor.rowcount == 1

    def save_step(self, run_id: str, attempt: int, step_name: str, status: str, *, started_at: str | None = None, finished_at: str | None = None, error: str = "", details: dict | None = None, idempotency_key: str | None = None, lease_owner: str = "", lease_expires_at: str = "", heartbeat_at: str = "", retry_count: int = 0) -> None:
        existing = self.conn.execute(
            "SELECT retry_count FROM run_steps WHERE run_id=? AND attempt=? AND step_name=?",
            (run_id, attempt, step_name),
        ).fetchone()
        if existing and retry_count == 0:
            retry_count = int(existing[0] or 0)
        self.conn.execute(
            """INSERT OR REPLACE INTO run_steps
            (run_id,attempt,step_name,status,started_at,finished_at,error,details_json,idempotency_key,lease_owner,lease_expires_at,heartbeat_at,retry_count)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, attempt, step_name, status, started_at, finished_at, error, json.dumps(details or {}, ensure_ascii=False), idempotency_key or f"{run_id}:{attempt}:{step_name}", lease_owner, lease_expires_at, heartbeat_at, retry_count),
        ); self.commit()

    def claim_next_run(self, owner: str, now: str, lease_expires_at: str) -> dict | None:
        """Atomically lease one runnable run to a single-process worker."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                """SELECT run_id FROM research_runs
                WHERE status IN ('planning','queued','collecting','governing','analyzing','auditing')
                  AND (lease_expires_at='' OR lease_expires_at IS NULL OR lease_expires_at<=?)
                ORDER BY CASE WHEN theme_id LIKE 'report-refresh:%' THEN 0 ELSE 1 END,
                         created_at
                LIMIT 1""",
                (now,),
            ).fetchone()
            if not row:
                self.conn.commit()
                return None
            cursor = self.conn.execute(
                """UPDATE research_runs SET lease_owner=?,lease_expires_at=?,heartbeat_at=?
                WHERE run_id=? AND (lease_expires_at='' OR lease_expires_at IS NULL OR lease_expires_at<=?)""",
                (owner, lease_expires_at, now, row[0], now),
            )
            self.conn.commit()
            return self.research_run(row[0]) if cursor.rowcount == 1 else None
        except Exception:
            self.conn.rollback()
            raise

    def heartbeat_run(self, run_id: str, owner: str, heartbeat_at: str, lease_expires_at: str) -> bool:
        cursor = self.conn.execute(
            "UPDATE research_runs SET heartbeat_at=?,lease_expires_at=? WHERE run_id=? AND lease_owner=?",
            (heartbeat_at, lease_expires_at, run_id, owner),
        )
        self.commit()
        return cursor.rowcount == 1

    def release_run(self, run_id: str, owner: str) -> None:
        self.conn.execute(
            "UPDATE research_runs SET lease_owner='',lease_expires_at='',heartbeat_at='' WHERE run_id=? AND lease_owner=?",
            (run_id, owner),
        )
        self.commit()

    def transition_research_run(self, run_id: str, expected_statuses: set[str], **values: object) -> bool:
        """Compare-and-set transition used by review, cancellation and rerun routes."""
        if not expected_statuses:
            return False
        allowed = {"status", "stage", "updated_at", "result_json", "error", "progress", "review_gate", "attempt", "lease_owner", "lease_expires_at", "heartbeat_at"}
        updates = {key: value for key, value in values.items() if key in allowed}
        if "result" in values:
            updates["result_json"] = json.dumps(values["result"], ensure_ascii=False)
        marks = ",".join("?" for _ in expected_statuses)
        assignments = ",".join(f"{key}=?" for key in updates)
        cursor = self.conn.execute(
            f"UPDATE research_runs SET {assignments} WHERE run_id=? AND status IN ({marks})",
            (*updates.values(), run_id, *sorted(expected_statuses)),
        )
        self.commit()
        return cursor.rowcount == 1

    def run_steps(self, run_id: str) -> list[dict]:
        columns = [item[0] for item in self.conn.execute("SELECT * FROM run_steps").description]
        rows = self.conn.execute("SELECT * FROM run_steps WHERE run_id=? ORDER BY attempt, rowid", (run_id,))
        result = [dict(zip(columns, row)) for row in rows]
        for item in result: item["details"] = json.loads(item.pop("details_json") or "{}")
        return result

    def save_approval(self, run_id: str, gate: str, decision: str, note: str, created_at: str) -> None:
        self.conn.execute("INSERT INTO approvals (run_id,gate,decision,note,created_at) VALUES (?,?,?,?,?)", (run_id, gate, decision, note, created_at)); self.commit()

    def approvals(self, run_id: str) -> list[dict]:
        columns = ("approval_id", "run_id", "gate", "decision", "note", "created_at")
        return [dict(zip(columns, row)) for row in self.conn.execute("SELECT approval_id,run_id,gate,decision,note,created_at FROM approvals WHERE run_id=? ORDER BY approval_id", (run_id,))]

    def increment_attempt(self, run_id: str, updated_at: str) -> int:
        self.conn.execute("UPDATE research_runs SET attempt=attempt+1,updated_at=?,error='' WHERE run_id=?", (updated_at, run_id)); self.commit()
        run = self.research_run(run_id)
        return int(run["attempt"]) if run else 0

    def create_agent_run(self, item: dict) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO agent_runs
            (agent_run_id,run_id,attempt,stage,provider,model,prompt_version,prompt_hash,status,stop_reason,model_requests,tool_calls,input_tokens,output_tokens,started_at,finished_at,error)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item["agent_run_id"], item["run_id"], item["attempt"], item.get("stage", "collecting"),
                item.get("provider", ""), item.get("model", ""), item.get("prompt_version", ""),
                item.get("prompt_hash", ""), item.get("status", "running"), item.get("stop_reason", ""),
                item.get("model_requests", 0), item.get("tool_calls", 0), item.get("input_tokens", 0),
                item.get("output_tokens", 0), item.get("started_at"), item.get("finished_at"), item.get("error", ""),
            ),
        )
        self.commit()

    def finish_agent_run(self, agent_run_id: str, **values: object) -> None:
        allowed = {"status", "stop_reason", "model_requests", "tool_calls", "input_tokens", "output_tokens", "finished_at", "error"}
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return
        assignments = ",".join(f"{key}=?" for key in updates)
        self.conn.execute(f"UPDATE agent_runs SET {assignments} WHERE agent_run_id=?", (*updates.values(), agent_run_id))
        self.commit()

    def agent_runs(self, run_id: str) -> list[dict]:
        columns = [item[0] for item in self.conn.execute("SELECT * FROM agent_runs").description]
        return [dict(zip(columns, row)) for row in self.conn.execute("SELECT * FROM agent_runs WHERE run_id=? ORDER BY started_at", (run_id,))]

    def close_interrupted_agent_runs(self, run_id: str, finished_at: str) -> int:
        """Close stale audit rows before a leased run starts a new agent session."""
        cursor = self.conn.execute(
            """UPDATE agent_runs
            SET status='interrupted',stop_reason='worker_recovered',finished_at=?,
                error=CASE WHEN error='' THEN 'Worker restarted before the agent session closed.' ELSE error END
            WHERE run_id=? AND status='running'""",
            (finished_at, run_id),
        )
        self.commit()
        return int(cursor.rowcount)

    def start_tool_call(self, *, run_id: str, attempt: int, call_uid: str, agent_run_id: str, round_number: int, tool_name: str, started_at: str, arguments: dict) -> int:
        existing = self.conn.execute("SELECT tool_call_id FROM tool_calls WHERE run_id=? AND call_uid=?", (run_id, call_uid)).fetchone()
        if existing:
            return int(existing[0])
        cursor = self.conn.execute(
            """INSERT INTO tool_calls
            (run_id,attempt,tool_name,status,started_at,finished_at,error,metadata_json,call_uid,agent_run_id,round_number,arguments_json,result_json,retry_count,latency_ms,evidence_delta)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, attempt, tool_name, "running", started_at, None, "", "{}", call_uid, agent_run_id, round_number, json.dumps(arguments, ensure_ascii=False), "{}", 0, 0, 0),
        )
        self.commit()
        return int(cursor.lastrowid)

    def tool_call_by_uid(self, run_id: str, call_uid: str) -> dict | None:
        columns = [item[0] for item in self.conn.execute("SELECT * FROM tool_calls").description]
        row = self.conn.execute("SELECT * FROM tool_calls WHERE run_id=? AND call_uid=?", (run_id, call_uid)).fetchone()
        if not row: return None
        item = dict(zip(columns, row))
        item["arguments"] = json.loads(item.pop("arguments_json") or "{}")
        item["result"] = json.loads(item.pop("result_json") or "{}")
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        item["coverage_before"] = json.loads(item.pop("coverage_before_json") or "{}")
        item["coverage_after"] = json.loads(item.pop("coverage_after_json") or "{}")
        return item

    def finish_tool_call(
        self, tool_call_id: int, *, status: str, finished_at: str, result: dict | None = None,
        error: str = "", retry_count: int = 0, latency_ms: int = 0, evidence_delta: int = 0,
        relevant_evidence_delta: int = 0, coverage_before: dict | None = None,
        coverage_after: dict | None = None,
    ) -> None:
        self.conn.execute(
            """UPDATE tool_calls SET status=?,finished_at=?,error=?,result_json=?,retry_count=?,latency_ms=?,
            evidence_delta=?,relevant_evidence_delta=?,coverage_before_json=?,coverage_after_json=?
            WHERE tool_call_id=?""",
            (
                status, finished_at, error, json.dumps(result or {}, ensure_ascii=False), retry_count,
                latency_ms, evidence_delta, relevant_evidence_delta,
                json.dumps(coverage_before or {}, ensure_ascii=False),
                json.dumps(coverage_after or {}, ensure_ascii=False), tool_call_id,
            ),
        )
        self.commit()

    def tool_calls(self, run_id: str) -> list[dict]:
        columns = [item[0] for item in self.conn.execute("SELECT * FROM tool_calls").description]
        rows = [dict(zip(columns, row)) for row in self.conn.execute("SELECT * FROM tool_calls WHERE run_id=? ORDER BY tool_call_id", (run_id,))]
        for item in rows:
            item["arguments"] = json.loads(item.pop("arguments_json") or "{}")
            item["result"] = json.loads(item.pop("result_json") or "{}")
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            item["coverage_before"] = json.loads(item.pop("coverage_before_json") or "{}")
            item["coverage_after"] = json.loads(item.pop("coverage_after_json") or "{}")
        return rows

    def save_report_asset(self, asset: dict) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO report_assets
            (report_id,run_id,title,kind,theme_id,folder_id,status,tags,summary,updated_at,created_at,archived_at,deleted_at,version,source_count,evidence_count,audit_passed)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                asset["report_id"], asset.get("run_id", ""), asset["title"], asset.get("kind", "theme_report"),
                asset.get("theme_id", "unknown"), asset.get("folder_id", "ai"), asset.get("status", "completed"),
                json.dumps(asset.get("tags", []), ensure_ascii=False), asset.get("summary", ""), asset["updated_at"],
                asset.get("created_at", asset["updated_at"]), asset.get("archived_at"), asset.get("deleted_at"),
                int(asset.get("version", 1)), int(asset.get("source_count", 0)), int(asset.get("evidence_count", 0)),
                int(bool(asset.get("audit_passed", False))),
            ),
        )
        self.commit()

    def report_assets(self, *, include_deleted: bool = False) -> list[dict]:
        columns = [item[0] for item in self.conn.execute("SELECT * FROM report_assets").description]
        query = "SELECT * FROM report_assets" if include_deleted else "SELECT * FROM report_assets WHERE deleted_at IS NULL"
        query += " ORDER BY updated_at DESC"
        return [dict(zip(columns, row)) for row in self.conn.execute(query)]

    def report_asset(self, report_id: str) -> dict | None:
        columns = [item[0] for item in self.conn.execute("SELECT * FROM report_assets").description]
        row = self.conn.execute("SELECT * FROM report_assets WHERE report_id=? AND deleted_at IS NULL", (report_id,)).fetchone()
        return dict(zip(columns, row)) if row else None

    def save_etf_market_snapshot(self, item: dict) -> None:
        payload = dict(item.get("payload") or {})
        products = item.get("products", payload.get("products", []))
        errors = item.get("errors", payload.get("errors", []))
        self.conn.execute(
            """INSERT OR REPLACE INTO etf_market_snapshots
            (snapshot_id,report_id,collected_at,market_as_of,status,products_json,errors_json,payload_json)
            VALUES (?,?,?,?,?,?,?,?)""",
            (
                item["snapshot_id"], item["report_id"], item["collected_at"],
                item.get("market_as_of", payload.get("market_as_of", "")),
                item.get("status", payload.get("status", "unknown")),
                json.dumps(products, ensure_ascii=False),
                json.dumps(errors, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        self.commit()

    def latest_etf_market_snapshot(self, report_id: str) -> dict | None:
        row = self.conn.execute(
            """SELECT snapshot_id,report_id,collected_at,market_as_of,status,
            products_json,errors_json,payload_json FROM etf_market_snapshots
            WHERE report_id=? ORDER BY collected_at DESC, rowid DESC LIMIT 1""",
            (report_id,),
        ).fetchone()
        if not row:
            return None
        keys = ("snapshot_id", "report_id", "collected_at", "market_as_of", "status", "products", "errors", "payload")
        item = dict(zip(keys, row))
        for key, fallback in (("products", []), ("errors", []), ("payload", {})):
            item[key] = json.loads(item[key] or json.dumps(fallback))
        return item

    def save_etf_preview_snapshot(self, item: dict) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO etf_preview_snapshots
            (snapshot_id,collected_at,market_as_of,status,source,payload_json)
            VALUES (?,?,?,?,?,?)""",
            (
                item["snapshot_id"], item["collected_at"], item.get("market_as_of", ""),
                item.get("status", "unknown"), item.get("source", "天天基金网"),
                json.dumps(item, ensure_ascii=False),
            ),
        )
        self.commit()

    def latest_etf_preview_snapshot(self) -> dict | None:
        row = self.conn.execute(
            """SELECT payload_json FROM etf_preview_snapshots
            ORDER BY collected_at DESC, rowid DESC LIMIT 1"""
        ).fetchone()
        return json.loads(row[0]) if row else None

    def update_report_asset(self, report_id: str, *, title: str | None = None, status: str | None = None, updated_at: str) -> dict | None:
        current = self.report_asset(report_id)
        if not current:
            return None
        next_title = title.strip() if title is not None else current["title"]
        next_status = status or current["status"]
        archived_at = updated_at if next_status == "archived" else current["archived_at"]
        self.conn.execute(
            "UPDATE report_assets SET title=?,status=?,updated_at=?,archived_at=? WHERE report_id=?",
            (next_title, next_status, updated_at, archived_at, report_id),
        )
        self.commit()
        return self.report_asset(report_id)

    def soft_delete_report_asset(self, report_id: str, deleted_at: str) -> bool:
        cursor = self.conn.execute(
            "UPDATE report_assets SET deleted_at=?,updated_at=? WHERE report_id=? AND deleted_at IS NULL",
            (deleted_at, deleted_at, report_id),
        )
        self.commit()
        return cursor.rowcount > 0
