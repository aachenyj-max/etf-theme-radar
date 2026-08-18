"""Run the single production research and sync workers outside the API process."""
from __future__ import annotations

import os
import signal
import threading

from .sync_worker import stop_all_sync_workers, sync_worker_for
from .worker import stop_all_workers, worker_for


def main() -> None:
    database_path = os.getenv("DATABASE_PATH", "data/radar.db")
    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    worker_for(database_path)
    sync_worker_for(database_path)
    stopped.wait()
    stop_all_sync_workers()
    stop_all_workers()


if __name__ == "__main__":
    main()
