"""Start the version-7 web app on PostgreSQL for the P10 evidence (the queue, the drain, the race).

    python3 -I serve_pg.py --project <hotel-booking folder> --port 5080 --pg-port 55433

``python main.py --db postgres`` needs psycopg, which cannot be installed in the build container. This
file does what ``main.run_api`` does - the same ``NotificationOptions`` from the same HOTEL_*
variables, ``build_notifications``, ``build_api`` with the queue, Redis from HOTEL_REDIS_PORT, the
shutdown hook ``shut_down_notifications`` - but connects through P09's ``pg_wire`` (a stdlib
stand-in for psycopg; the store's SQL and error handling are the app's own, unchanged).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

EVIDENCE = Path(__file__).resolve().parent
P09_EVIDENCE = EVIDENCE.parents[1] / "P09-protect-the-last-seat" / "evidence"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--pg-port", type=int, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.project.resolve()))
    sys.path.insert(0, str(P09_EVIDENCE))
    import pg_wire
    import uvicorn

    import main as wiring  # the project's own wiring (version 7)

    parsed = wiring.argparse.ArgumentParser()
    wiring.add_notification_arguments(parsed)
    options = parsed.parse_args([])  # the HOTEL_* variables, exactly as python main.py reads them
    sending = wiring.NotificationOptions(
        queue=options.queue, email_seconds=options.email_seconds, email_timeout=options.email_timeout,
        email_fail_every=options.email_fail_every, capacity=options.queue_capacity, workers=options.workers,
        send_attempts=options.send_attempts, drain=options.drain, drain_seconds=options.drain_seconds)

    def connect() -> Any:
        return pg_wire.connect(port=args.pg_port)

    notifications = wiring.build_notifications(sending)
    slow_step = float(wiring.os.getenv("HOTEL_SLOW_STEP", "0"))
    app, _ = wiring.build_api(
        connect, slow_step, notifications=notifications, cache=wiring.build_cache("redis"),
        on_shutdown=lambda: wiring.shut_down_notifications(notifications, sending.drain, sending.drain_seconds))
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        notifications.close(drain=False)


if __name__ == "__main__":
    main()
