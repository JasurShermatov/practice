"""Start one instance of a hotel-booking version's web app for the P09 experiments.

    python3 -I serve.py --project <hotel-booking folder> --port 5080 --slow-step 1 --db sqlite:<file>
    python3 -I serve.py --project <...> --port 5081 --slow-step 1 --db postgres:55432
    python3 -I serve.py --project <version 5 copy> --port 5080 --slow-step 1 --db sqlite:<file> --app-lock

It imports ``main`` from the given project folder and uses that version's own wiring -
``main.build_api`` (the unit of work, the counting store, the real ``SqlReservationStore``) and
``main.build_cache`` (Redis from HOTEL_REDIS_PORT) - and serves it with uvicorn, exactly as
``python main.py`` does. Three things ``python main.py`` cannot do, and why this file exists:

- run version 5 (the P08 code, before the fix) with a slow step: version 5 has no HOTEL_SLOW_STEP
  setting, but its ``build_api`` already takes ``slow_step_seconds`` (P03's race knob);
- ``--db postgres:<port>``: connect through ``pg_wire`` (a stdlib stand-in for psycopg, which cannot
  be installed here) - the store's SQL and error handling are the app's own, unchanged;
- ``--app-lock``: the Step 3 repair applied to the web app - one ``threading.Lock`` per process held
  around every request's unit of work, so check-then-save is atomic *inside this process*.
"""
from __future__ import annotations

import argparse
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

EVIDENCE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--slow-step", type=float, default=0.0)
    parser.add_argument("--db", required=True, help="sqlite:<file> or postgres:<port>")
    parser.add_argument("--app-lock", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(args.project.resolve()))
    import uvicorn

    import main as wiring  # the project's own wiring (version 5 or 6)

    kind, _, where = args.db.partition(":")
    if kind == "sqlite":
        connect = wiring.sqlite_connector(Path(where))
    elif kind == "postgres":
        sys.path.insert(0, str(EVIDENCE))
        import pg_wire

        def connect() -> Any:
            return pg_wire.connect(port=int(where))
    else:
        raise SystemExit(f"unknown --db {args.db}")

    if args.app_lock:
        original = wiring.sql_unit_of_work
        process_lock = threading.Lock()  # one per process: exactly what Step 4 is about

        def locked_unit_of_work(*given: Any, **named: Any) -> Any:
            inner = original(*given, **named)

            @contextmanager
            def unit_of_work() -> Iterator[Any]:
                with process_lock, inner() as service:
                    yield service

            return unit_of_work

        wiring.sql_unit_of_work = locked_unit_of_work

    app, _ = wiring.build_api(connect, args.slow_step, cache=wiring.build_cache("redis"))
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
