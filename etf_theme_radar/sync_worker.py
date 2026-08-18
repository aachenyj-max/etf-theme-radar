"""Persistent source-sync and candidate-discovery worker."""
from __future__ import annotations

import os
import socket
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from .agent_goals import AgentGoalRuntime
from .connector_factory import configured_connectors
from .etf_preview import collect_etf_preview_snapshot, load_preview_config
from .governance import reclassify_store
from .info_agent import create_information_goal, run_information_goal
from .models import utcnow
from .ontology import refresh_research_assets
from .pipeline import ingest
from .reports import build_daily_briefing
from .store import EvidenceStore
from .theme_discovery import discover_theme_candidates


def _timestamp(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


class SyncDiscoveryWorker:
    def __init__(self, database_path: str | Path, *, poll_seconds: float = 0.2, lease_seconds: int = 60):
        self.database_path = str(Path(database_path))
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self.owner = f"{socket.gethostname()}:{os.getpid()}:sync:{id(self)}"
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="etf-radar-sync-worker", daemon=True)
        self.last_heartbeat_at = ""
        self._last_preview_schedule_check = 0.0
        self._last_persisted_heartbeat = 0.0

    @property
    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()
        self.last_heartbeat_at = _timestamp()
        self._publish_heartbeat(force=True)
        self.wake()

    def _publish_heartbeat(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_persisted_heartbeat < 5.0:
            return
        store: EvidenceStore | None = None
        try:
            store = EvidenceStore(self.database_path)
            self.last_heartbeat_at = _timestamp()
            store.record_worker_heartbeat("sync_discovery", self.owner, self.last_heartbeat_at)
            self._last_persisted_heartbeat = now
        except sqlite3.OperationalError:
            # Keep source synchronization alive when another short SQLite
            # writer temporarily owns the database.
            return
        finally:
            if store is not None:
                store.close()

    def wake(self) -> None:
        self._wake.set()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set(); self._wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout)

    def run_once(self) -> bool:
        store = EvidenceStore(self.database_path)
        try:
            preview_run = store.claim_next_sync_run(
                self.owner, _timestamp(), _timestamp(self.lease_seconds), etf_preview_only=True,
            )
            information_goal = None if preview_run else AgentGoalRuntime(store, self.owner).claim(
                "background", _timestamp(), _timestamp(self.lease_seconds), goal_types=("information_collection",),
            )
            run = None
            discovery_run = None
            if preview_run:
                run = preview_run
            elif not information_goal:
                run = store.claim_next_sync_run(self.owner, _timestamp(), _timestamp(self.lease_seconds))
                if not run:
                    discovery_run = store.claim_next_discovery_run(self.owner, _timestamp(), _timestamp(self.lease_seconds))
        finally:
            store.close()
        if information_goal:
            self._execute_information_goal(information_goal)
            return True
        if not run:
            if not discovery_run:
                return False
            self._execute_discovery(discovery_run)
            return True
        stopped = threading.Event()
        heartbeat = threading.Thread(target=self._heartbeat, args=(run["sync_run_id"], stopped), daemon=True)
        heartbeat.start()
        try:
            self._execute(run)
        finally:
            stopped.set(); heartbeat.join(1.0)
        return True

    def _execute_information_goal(self, goal: dict) -> None:
        stopped = threading.Event()
        heartbeat = threading.Thread(
            target=self._goal_heartbeat, args=(goal["goal_id"], stopped), daemon=True,
        )
        heartbeat.start()
        store = EvidenceStore(self.database_path)
        try:
            run_information_goal(store, goal, self.owner, collect=self._collect_information_source)
        except Exception as exc:
            current = store.agent_goal(goal["goal_id"])
            if current and current["status"] not in {"completed", "cancelled", "partial", "needs_attention"}:
                store.transition_agent_goal(
                    goal["goal_id"], self.owner, "needs_attention", _timestamp(),
                    safe_summary="信息 Goal 执行异常，已保留审计与待处理状态",
                    result=current["result"], error=str(exc),
                )
        finally:
            stopped.set()
            heartbeat.join(1.0)
            store.close()

    def _collect_information_source(self, source: str, _purpose: str, payload: dict) -> dict:
        aliases = {
            "sec": "sec_edgar_etf", "arxiv": "openalex",
            "company_careers": "public_job_boards", "etf_holdings": "official_etf_holdings",
            "etf_news": "yahoo_etf_news", "patents": "google_patents", "sp_global": "sp_global_dji",
        }
        target = aliases.get(source, source)
        connector = next(
            (item for item in configured_connectors(Path("data/cache")) if item.source_name == target),
            None,
        )
        if connector is None:
            return {"status": "unavailable", "reason": "source_not_configured"}
        until = date.fromisoformat(str(payload.get("scheduled_for") or date.today().isoformat())[:10])
        source_store = EvidenceStore(self.database_path)
        try:
            result = ingest(connector, source_store, until - timedelta(days=7), until)
            return {"status": str(result.get("status") or "succeeded"), "source": target, "events": int(result.get("events") or 0)}
        except Exception:
            return {"status": "degraded", "reason": "source_collection_failed"}
        finally:
            source_store.close()

    def _execute_discovery(self, run: dict) -> None:
        store = EvidenceStore(self.database_path)
        try:
            as_of = date.fromisoformat(run["window_end"]) if run.get("window_end") else date.today()
            result = discover_theme_candidates(store, as_of=as_of)
            store.update_discovery_run(run["discovery_run_id"], status="completed", stage="finish_research", updated_at=utcnow(), result=result)
        except Exception as exc:
            store.update_discovery_run(run["discovery_run_id"], status="failed", stage="finish_research", updated_at=utcnow(), error=str(exc))
        finally:
            store.close()

    def _execute(self, run: dict) -> None:
        if str(run.get("idempotency_key") or "").startswith("etf-preview:"):
            self._execute_etf_preview(run)
            return
        store = EvidenceStore(self.database_path)
        results: dict = {}
        connectors = configured_connectors(Path("data/cache"))
        daily_key = str(run.get("idempotency_key") or "")
        if daily_key.startswith("daily:"):
            until = date.fromisoformat(daily_key.removeprefix("daily:")[:10])
        else:
            until = date.today()
        try:
            for index, connector in enumerate(connectors):
                current = store.sync_run(run["sync_run_id"])
                if current and current["cancel_requested"]:
                    store.update_sync_run(run["sync_run_id"], status="cancelled", progress=current["progress"], current_source=connector.source_name, updated_at=utcnow(), result=results, error="用户取消同步")
                    return
                store.update_sync_run(run["sync_run_id"], status="running", progress=max(1, int(index / max(len(connectors), 1) * 80)), current_source=connector.source_name, updated_at=utcnow(), result=results)
                try:
                    results[connector.source_name] = ingest(connector, store, until - timedelta(days=int(run.get("days") or 7)), until)
                except Exception as exc:
                    results[connector.source_name] = {"status": "degraded", "error": str(exc)}
            # Classification, entity refresh, confirmed snapshots and candidate
            # discovery are one resumable terminal stage after source isolation.
            governance = reclassify_store(store)
            discovery_run_id = f"discovery:{run['sync_run_id']}"
            store.create_discovery_run({
                "discovery_run_id": discovery_run_id,
                "idempotency_key": f"sync:{run['sync_run_id']}",
                "run_kind": "daily" if str(run.get("idempotency_key") or "").startswith("daily:") else "manual",
                "status": "running", "stage": "clustering", "created_at": utcnow(),
                "window_start": (until - timedelta(days=29)).isoformat(), "window_end": until.isoformat(),
            })
            try:
                assets = refresh_research_assets(store)
                store.update_discovery_run(discovery_run_id, status="completed", stage="finish_research", updated_at=utcnow(), result=assets.get("theme_discovery", {}))
            except Exception as exc:
                store.update_discovery_run(discovery_run_id, status="failed", stage="finish_research", updated_at=utcnow(), error=str(exc))
                raise
            daily_briefing = None
            if str(run.get("idempotency_key") or "").startswith("daily:"):
                daily_briefing = store.save_daily_briefing_asset(build_daily_briefing(
                    store, as_of_date=until.isoformat(), generated_at=utcnow(),
                ))
                create_information_goal(
                    store, kind="daily", goal_id=f"information:daily:{until.isoformat()}",
                    now=utcnow(), scheduled_for=until.isoformat(),
                )
            store.update_sync_run(run["sync_run_id"], status="completed", progress=100, updated_at=utcnow(), result={
                "sources": results, "governance": governance, "research_assets": assets,
                "daily_briefing_id": daily_briefing["briefing_id"] if daily_briefing else "",
            })
        except Exception as exc:
            store.update_sync_run(run["sync_run_id"], status="failed", progress=0, updated_at=utcnow(), result=results, error=str(exc))
        finally:
            store.close()

    def _execute_etf_preview(self, run: dict) -> None:
        store = EvidenceStore(self.database_path)
        try:
            store.update_sync_run(
                run["sync_run_id"], status="running", progress=5,
                current_source="天天基金网", updated_at=utcnow(),
            )

            def cancelled() -> bool:
                current = store.sync_run(run["sync_run_id"])
                return bool(current and current["cancel_requested"])

            snapshot = collect_etf_preview_snapshot(cancelled=cancelled)
            if cancelled():
                store.update_sync_run(
                    run["sync_run_id"], status="cancelled", progress=0,
                    current_source="天天基金网", updated_at=utcnow(),
                    error="用户取消同步",
                )
                return
            store.save_etf_preview_snapshot(snapshot)
            store.update_sync_run(
                run["sync_run_id"], status="completed", progress=100,
                current_source="天天基金网", updated_at=utcnow(),
                result={
                    "snapshot_id": snapshot["snapshot_id"],
                    "status": snapshot["status"],
                    "counts": snapshot["counts"],
                    "error_count": len(snapshot["errors"]),
                },
            )
        except Exception as exc:
            current = store.sync_run(run["sync_run_id"])
            cancelled = bool(current and current["cancel_requested"])
            store.update_sync_run(
                run["sync_run_id"], status="cancelled" if cancelled else "failed",
                progress=0, current_source="天天基金网", updated_at=utcnow(),
                error="用户取消同步" if cancelled else str(exc),
            )
        finally:
            store.close()

    def _schedule_etf_preview_if_due(self) -> None:
        now_monotonic = time.monotonic()
        if now_monotonic - self._last_preview_schedule_check < 60:
            return
        self._last_preview_schedule_check = now_monotonic
        config = load_preview_config()
        schedule = config["schedule"]
        local_now = datetime.now(ZoneInfo(str(schedule["timezone"])))
        if bool(schedule.get("weekdays_only", True)) and local_now.weekday() >= 5:
            return
        due = local_now.replace(hour=int(schedule["hour"]), minute=int(schedule["minute"]), second=0, microsecond=0)
        if local_now < due:
            return
        store = EvidenceStore(self.database_path)
        try:
            created = store.create_sync_run(
                str(uuid4()), utcnow(), days=0,
                idempotency_key=f"etf-preview:daily:{local_now.date().isoformat()}",
            )
        finally:
            store.close()
        if created:
            self.wake()

    def _heartbeat(self, sync_run_id: str, stopped: threading.Event) -> None:
        while not stopped.wait(max(1.0, self.lease_seconds / 3)):
            store = None
            try:
                store = EvidenceStore(self.database_path)
                if not store.heartbeat_sync_run(sync_run_id, self.owner, _timestamp(), _timestamp(self.lease_seconds)):
                    return
                self.last_heartbeat_at = _timestamp()
            except sqlite3.OperationalError:
                continue
            finally:
                if store:
                    store.close()

    def _goal_heartbeat(self, goal_id: str, stopped: threading.Event) -> None:
        while not stopped.wait(max(1.0, self.lease_seconds / 3)):
            store = None
            try:
                store = EvidenceStore(self.database_path)
                if not store.heartbeat_agent_goal(goal_id, self.owner, _timestamp(), _timestamp(self.lease_seconds)):
                    return
                self.last_heartbeat_at = _timestamp()
            except sqlite3.OperationalError:
                continue
            finally:
                if store:
                    store.close()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._publish_heartbeat()
                self._schedule_etf_preview_if_due()
                worked = self.run_once()
            except Exception:
                worked = False
            if not worked:
                self._wake.wait(self.poll_seconds); self._wake.clear()


_LOCK = threading.Lock()
_WORKERS: dict[str, SyncDiscoveryWorker] = {}


def sync_worker_for(database_path: str | Path) -> SyncDiscoveryWorker:
    key = str(Path(database_path).resolve())
    with _LOCK:
        worker = _WORKERS.get(key)
        if worker is None or not worker.is_alive:
            worker = SyncDiscoveryWorker(key); _WORKERS[key] = worker; worker.start()
        else:
            worker.wake()
        return worker


def stop_all_sync_workers() -> None:
    with _LOCK:
        workers = list(_WORKERS.values()); _WORKERS.clear()
    for worker in workers:
        worker.stop()


def sync_worker_status(database_path: str | Path) -> dict[str, object]:
    key = str(Path(database_path).resolve())
    with _LOCK:
        worker = _WORKERS.get(key)
        if worker and worker.is_alive:
            return {"status": "healthy", "alive": True, "owner": worker.owner, "heartbeat_at": worker.last_heartbeat_at}
    store = EvidenceStore(database_path)
    try:
        heartbeat = store.worker_heartbeat("sync_discovery")
    finally:
        store.close()
    if heartbeat is None:
        return {"status": "stopped", "alive": False, "owner": "", "heartbeat_at": ""}
    try:
        fresh = (datetime.now(timezone.utc) - datetime.fromisoformat(heartbeat["heartbeat_at"])).total_seconds() <= 30
    except ValueError:
        fresh = False
    return {"status": "healthy" if fresh else "stopped", "alive": fresh, **heartbeat}
