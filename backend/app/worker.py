"""Standalone sync worker (alternative to RUN_SYNC_WORKER=true inside the API):  python -m app.worker"""
import logging
import signal
import threading

from .config import Settings
from .db import make_engine, make_sessionmaker
from .peer import PeerClient
from .services.sync_worker import SyncRunner
from .store import ensure_defaults


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings()
    if not settings.is_hospital:
        raise SystemExit("The sync worker runs on the hospital server only.")
    SessionLocal = make_sessionmaker(make_engine(settings.database_url))
    ensure_defaults(SessionLocal)
    runner = SyncRunner(settings, SessionLocal, PeerClient(settings))
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    runner.start()
    stop.wait()
    runner.stop()


if __name__ == "__main__":
    main()
