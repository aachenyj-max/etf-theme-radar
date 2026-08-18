from __future__ import annotations

import os
import socket
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .store import EvidenceStore
from .workflow import execute_event_run, execute_market_refresh, execute_run, plan_run


def _timestamp(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


class DurableWorker:
    """A single persistent worker loop for one SQLite control database."""

    def __init__(self, database_path: str | Path, *, poll_seconds: float = 0.05, lease_seconds: int = 30):
        self.database_path = str(Path(database_path))
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self.owner = f"{socket.gethostname()}:{os.getpid()}:{id(self)}"
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=f"etf-radar-worker-{id(self)}", daemon=True)
        self.last_heartbeat_at = ""
        self._last_persisted_heartbeat = 0.0

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
            store.record_worker_heartbeat("research", self.owner, self.last_heartbeat_at)
            self._last_persisted_heartbeat = now
        except sqlite3.OperationalError:
            # The durable loop already retries a locked queue. Its independent
            # liveness pulse must follow the same rule, including database open.
            return
        finally:
            if store is not None:
                store.close()

    def wake(self) -> None:
        self._wake.set()

    @property
    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout)

    def run_once(self) -> bool:
        store = EvidenceStore(self.database_path)
        try:
            # Attention states never occupy the execution slot. Recover any
            # persisted waiter left behind by a restart before claiming work.
            store.promote_waiting_run(_timestamp())
            run = store.claim_next_run(self.owner, _timestamp(), _timestamp(self.lease_seconds))
        finally:
            store.close()
        if not run:
            return False
        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop, args=(run["run_id"], heartbeat_stop),
            name=f"etf-radar-heartbeat-{run['run_id']}", daemon=True,
        )
        heartbeat.start()
        try:
            if run["theme_id"].startswith("report-refresh:"):
                execute_market_refresh(self.database_path, run["run_id"], self.owner)
            elif run["theme_id"].startswith("event:"):
                execute_event_run(self.database_path, run["run_id"], self.owner)
            elif run["status"] == "planning":
                plan_run(self.database_path, run["run_id"], self.owner)
            else:
                execute_run(self.database_path, run["run_id"], self.owner)
        finally:
            heartbeat_stop.set()
            heartbeat.join(min(1.0, self.poll_seconds * 2))
        return True

    def _heartbeat_loop(self, run_id: str, stopped: threading.Event) -> None:
        interval = max(1.0, self.lease_seconds / 3)
        while not stopped.wait(interval):
            store: EvidenceStore | None = None
            try:
                store = EvidenceStore(self.database_path)
                if not store.heartbeat_run(run_id, self.owner, _timestamp(), _timestamp(self.lease_seconds)):
                    return
                self.last_heartbeat_at = _timestamp()
            except sqlite3.OperationalError:
                # Another short writer may own SQLite. A missed heartbeat must
                # retry instead of terminating the lease-renewal thread.
                if stopped.wait(min(1.0, max(self.poll_seconds, 0.1))):
                    return
            finally:
                if store is not None:
                    store.close()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._publish_heartbeat()
            try:
                worked = self.run_once()
            except sqlite3.OperationalError:
                # Sync and research share SQLite. A transient writer lock must
                # delay this poll, not permanently kill the durable worker.
                self._wake.wait(max(self.poll_seconds, 0.25))
                self._wake.clear()
                continue
            except Exception:
                # Individual runs persist their own failure state. Keep the
                # process worker available for later queued work.
                self._wake.wait(max(self.poll_seconds, 0.25))
                self._wake.clear()
                continue
            if not worked:
                self._wake.wait(self.poll_seconds)
                self._wake.clear()


_LOCK = threading.Lock()
_WORKERS: dict[str, DurableWorker] = {}


def worker_for(database_path: str | Path) -> DurableWorker:
    key = str(Path(database_path).resolve())
    with _LOCK:
        worker = _WORKERS.get(key)
        if worker is None or not worker.is_alive:
            worker = DurableWorker(key)
            _WORKERS[key] = worker
            worker.start()
        else:
            worker.wake()
        return worker


def stop_all_workers() -> None:
    with _LOCK:
        workers = list(_WORKERS.values())
        _WORKERS.clear()
    for worker in workers:
        worker.stop()


def worker_status(database_path: str | Path) -> dict[str, object]:
    """Return a read-only service heartbeat for launcher contract checks."""
    key = str(Path(database_path).resolve())
    with _LOCK:
        worker = _WORKERS.get(key)
        if worker and worker.is_alive:
            return {
                "status": "healthy", "alive": True, "owner": worker.owner,
                "heartbeat_at": worker.last_heartbeat_at,
            }
    store = EvidenceStore(database_path)
    try:
        heartbeat = store.worker_heartbeat("research")
    finally:
        store.close()
    if heartbeat is None:
        return {"status": "stopped", "alive": False, "owner": "", "heartbeat_at": ""}
    try:
        fresh = (datetime.now(timezone.utc) - datetime.fromisoformat(heartbeat["heartbeat_at"])).total_seconds() <= 30
    except ValueError:
        fresh = False
    return {"status": "healthy" if fresh else "stopped", "alive": fresh, **heartbeat}
