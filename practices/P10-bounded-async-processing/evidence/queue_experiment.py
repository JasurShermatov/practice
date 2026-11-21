"""P10 evidence: every run the activity sheet asks for, against the real app, with the output recorded.

    python3 -I practices/P10-bounded-async-processing/evidence/queue_experiment.py hotel-booking [--skip-postgres]

Each run starts ``python main.py`` (my own command) as a separate process on a fresh
SQLite file, with a throw-away redis-server for the search cache (``--cache redis``, the default),
and the HOTEL_* variables the sheet uses. The client is the project's own ``tools/burst.py`` (or
``tools/race_http.py``), run as a separate process. The server is stopped the way a person stops it -
Ctrl+C (SIGINT), SIGTERM, or ``kill -9`` - and everything it printed is kept. The PostgreSQL runs use a
throw-away PostgreSQL 16 cluster (P09's ``pg_cluster``) and ``serve_pg.py`` (P09's ``pg_wire``
instead of psycopg). Everything started here is stopped in ``finally`` blocks.

Writes ``logs/queue-experiment.txt`` (commands, environment, outputs) and ``logs/queue-results.json``
(the numbers the README, docs/queue-trace.md and ADR-004 quote).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EVIDENCE = Path(__file__).resolve().parent
LOGS = EVIDENCE / "logs"
P09_EVIDENCE = EVIDENCE.parents[1] / "P09-protect-the-last-seat" / "evidence"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextmanager
def redis_server() -> Iterator[int]:
    port = free_port()
    directory = tempfile.mkdtemp(prefix="p10-redis-")
    process = subprocess.Popen(["redis-server", "--port", str(port), "--bind", "127.0.0.1", "--save", "",
                                "--appendonly", "no", "--dir", directory],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.05)
        yield port
    finally:
        process.terminate()
        process.wait(timeout=10)
        shutil.rmtree(directory, ignore_errors=True)


def get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as answer:
        result: dict[str, Any] = json.loads(answer.read())
        return result


@dataclass
class Server:
    """One app process; its stdout and stderr go to a file (a full pipe would block the server)."""

    process: subprocess.Popen[bytes]
    base: str
    output_file: Path
    started: float = field(default_factory=time.monotonic)

    def stop(self, how: signal.Signals) -> str:
        if self.process.poll() is None:
            self.process.send_signal(how)
            try:
                self.process.wait(timeout=90)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        return self.output_file.read_text(encoding="utf-8")


@contextmanager
def server(project: Path, settings: dict[str, str], redis_port: int, work: Path, name: str,
           flags: tuple[str, ...] = (), command: list[str] | None = None) -> Iterator[Server]:
    """``python main.py`` (or ``command`` + ``--port <port>``) with the settings, on a free port."""
    port = free_port()
    output_file = work / f"{name}.server.txt"
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1", "HOTEL_REDIS_PORT": str(redis_port),
           "HOTEL_PORT": str(port), "HOTEL_DB_PATH": str(work / f"{name}.sqlite3"), **settings}
    argv = [*command, "--port", str(port)] if command else [sys.executable, "main.py", *flags]
    with output_file.open("w", encoding="utf-8") as sink:
        process = subprocess.Popen(argv, cwd=project, env=env, stdout=sink, stderr=subprocess.STDOUT)
    running = Server(process, f"http://127.0.0.1:{port}", output_file)
    try:
        for _ in range(300):
            try:
                get_json(f"{running.base}/stats")
                break
            except OSError:
                assert process.poll() is None, output_file.read_text(encoding="utf-8")
                time.sleep(0.05)
        yield running
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def tool(project: Path, script: str, *args: str) -> tuple[int, str]:
    done = subprocess.run([sys.executable, f"tools/{script}", *args], cwd=project, capture_output=True, text=True,
                          timeout=900, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return done.returncode, done.stdout + done.stderr


def burst_json(project: Path, base: str, *args: str) -> dict[str, Any]:
    code, out = tool(project, "burst.py", base, "--json", *args)
    result: dict[str, Any] = json.loads(out.splitlines()[-1])
    result["exit"] = code
    return result


def confirmed_rows(database: Path) -> int:
    with closing(sqlite3.connect(database)) as connection:
        return int(connection.execute("SELECT count(*) FROM reservations WHERE status = 'Confirmed'").fetchone()[0])


def shutdown_lines(output: str) -> list[str]:
    """The lines the app printed when it was stopped (from "Stopping the app" on)."""
    lines = output.splitlines()
    start = next((index for index, line in enumerate(lines) if line.startswith("Stopping the app")), len(lines))
    keep = ("Stopping", "Draining", "(no drain)", "Notification workers", "accepted=", "Nobody", "guests are owed")
    return [line for line in lines[start:] if line.startswith(keep) or " are owed " in line]


def poll_depth(base: str, limit: float = 120.0, every: float = 0.5) -> list[dict[str, Any]]:
    """GET /stats every half second until the workers have caught up: the queue depth over time."""
    series, started = [], time.monotonic()
    while time.monotonic() - started < limit:
        stats = get_json(f"{base}/stats")
        series.append({"t": round(time.monotonic() - started, 2), "queued": stats["notificationsQueued"],
                       "completed": stats["notificationsCompleted"], "failed": stats["notificationsFailed"],
                       "accepted": stats["notificationsAccepted"]})
        if stats["notificationsQueued"] == 0 and (stats["notificationsCompleted"] + stats["notificationsFailed"]
                                                   >= stats["notificationsAccepted"]):
            break
        time.sleep(every)
    return series


class Log:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, *text: str) -> None:
        for chunk in text:
            self.lines.extend(chunk.splitlines() or [""])

    def section(self, title: str) -> None:
        self.lines += ["", "=" * 100, title, "=" * 100]


def env_line(settings: dict[str, str], flags: tuple[str, ...] = ()) -> str:
    return " ".join([*(f"{key}={value}" for key, value in settings.items()), "python main.py", *flags])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("--skip-postgres", action="store_true")
    args = parser.parse_args()
    project = args.project.resolve()
    LOGS.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="p10-queue-"))
    log, results = Log(), {}
    log(f"# P10 queue experiment - {platform.system()} container, Python {platform.python_version()}, "
        f"SQLite {sqlite3.sqlite_version}, {subprocess.run(['redis-server', '--version'], capture_output=True, text=True).stdout.split()[2]}",
        "# every server below is `python main.py` in its own process (HOTEL_DB_PATH = a fresh file, cache = redis);",
        "# the client is tools/burst.py or tools/race_http.py in another process.")
    try:
        with redis_server() as redis_port:
            run_sqlite(project, work, redis_port, log, results)
            if not args.skip_postgres:
                run_postgres(project, work, redis_port, log, results)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    (LOGS / "queue-experiment.txt").write_text("\n".join(log.lines) + "\n", encoding="utf-8")
    (LOGS / "queue-results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("\n".join(log.lines))


def run_sqlite(project: Path, work: Path, redis_port: int, log: Log, results: dict[str, Any]) -> None:
    slow = {"HOTEL_EMAIL_SECONDS": "1"}

    # ---------------------------------------------------------------- Step 1: the cost, email inside the request
    log.section("Step 1 - before: the email sent inside the request (--no-queue), HOTEL_EMAIL_SECONDS=1")
    for count, key in ((1, "before_one"), (30, "before_burst")):
        with server(project, slow, redis_port, work, key, ("--no-queue",)) as app:
            code, out = tool(project, "burst.py", app.base, "--count", str(count))
            log(f"$ {env_line(slow, ('--no-queue',))}", f"$ python tools/burst.py --count {count}   (exit {code})", out)
            results[key] = burst_json(project, app.base, "--count", str(count), "--year", "2030")
            app.stop(signal.SIGINT)

    # ---------------------------------------------------------------- Step 2: one booking with the queue
    log.section("Step 2 - after: the same booking with the queue (default capacity 10, 1 worker)")
    with server(project, slow, redis_port, work, "after_one") as app:
        code, out = tool(project, "burst.py", app.base, "--count", "1", "--wait")
        log(f"$ {env_line(slow)}", f"$ python tools/burst.py --count 1 --wait   (exit {code})", out)
        results["after_one"] = burst_json(project, app.base, "--count", "1", "--year", "2030", "--wait")
        log("", "Server output after Ctrl+C:", *shutdown_lines(app.stop(signal.SIGINT)))

    # ---------------------------------------------------------------- Step 3: unbounded
    unbounded = {**slow, "HOTEL_QUEUE_CAPACITY": "10000", "HOTEL_DRAIN_SECONDS": "3"}
    log.section("Step 3 - a queue so big it never refuses (HOTEL_QUEUE_CAPACITY=10000); stopped with a 3 s drain limit")
    with server(project, unbounded, redis_port, work, "unbounded") as app:
        code, out = tool(project, "burst.py", app.base)
        log(f"$ {env_line(unbounded)}", f"$ python tools/burst.py   (exit {code})", out)
        results["unbounded"] = json.loads(out.split("GET /stats\n")[1].splitlines()[0])
        time.sleep(1.0)
        output = app.stop(signal.SIGINT)
        log("", "Server output after Ctrl+C (drain limited to 3 s):", *shutdown_lines(output))
        results["unbounded_shutdown"] = shutdown_lines(output)
        results["unbounded_rows"] = confirmed_rows(work / "unbounded.sqlite3")
        log(f"Confirmed rows in the database: {results['unbounded_rows']}")

    # ---------------------------------------------------------------- Steps 4-5: bounded, backpressure
    log.section("Steps 4-5 - the bound (default HOTEL_QUEUE_CAPACITY=10, HOTEL_WORKERS=1): refuse, count, catch up")
    with server(project, slow, redis_port, work, "bounded") as app:
        code, out = tool(project, "burst.py", app.base)
        log(f"$ {env_line(slow)}", f"$ python tools/burst.py   (exit {code})", out)
        burst_stats = json.loads(out.split("GET /stats\n")[1].splitlines()[0])
        series = poll_depth(app.base)
        later = get_json(f"{app.base}/stats")
        log("", "Queue depth, GET /stats every 0.5 s after the burst:",
            *(f"  t={point['t']:>5.2f} s  queued={point['queued']:>2}  completed={point['completed']:>2}"
              for point in series),
            "", f"GET /stats, {series[-1]['t']:.1f} seconds later", json.dumps(later, separators=(",", ":")))
        output = app.stop(signal.SIGINT)
        log("", "Server output after Ctrl+C:", *shutdown_lines(output))
        results["bounded"] = {"burst": burst_stats, "series": series, "later": later,
                              "latency": re.search(r"Booking latency: (.*)", out).group(1),  # type: ignore[union-attr]
                              "rows": confirmed_rows(work / "bounded.sqlite3"),
                              "refused_answers": int(re.search(r"notificationFailed: true: (\d+)", out).group(1))}  # type: ignore[union-attr]
        log(f"Confirmed rows in the database: {results['bounded']['rows']}")
    # the same bounded burst, as numbers, five times (fresh server each time)
    repeats = []
    for number in range(5):
        with server(project, slow, redis_port, work, f"bounded{number}") as app:
            repeats.append(burst_json(project, app.base))
            app.stop(signal.SIGKILL)
    results["bounded_repeats"] = [{"accepted": r["stats"]["notificationsAccepted"],
                                   "rejected": r["stats"]["notificationsRejected"],
                                   "queued": r["stats"]["notificationsQueued"],
                                   "p50": round(r_p(r, 0.5), 1), "p95": round(r_p(r, 0.95), 1),
                                   "max": round(max(r["latencies_ms"]), 1), "total": round(r["total_seconds"], 3)}
                                  for r in repeats]
    log("", "The same burst five more times (fresh server each), accepted/rejected/queued and latency:",
        *(f"  run {n + 1}: accepted {r['accepted']}, rejected {r['rejected']}, queued {r['queued']}; "
          f"p50 {r['p50']} ms, p95 {r['p95']} ms, max {r['max']} ms; total {r['total']} s"
          for n, r in enumerate(results["bounded_repeats"])))

    # ---------------------------------------------------------------- Step 6: shutdown
    log.section("Step 6 - stopping the app: drain, no drain, SIGTERM, kill -9 (10 bookings, 1 s sender, stop after ~3 s)")
    for key, flags, how in (("stop_drain", (), signal.SIGINT), ("stop_no_drain", ("--no-drain",), signal.SIGINT),
                            ("stop_sigterm", (), signal.SIGTERM), ("stop_kill9", (), signal.SIGKILL)):
        with server(project, slow, redis_port, work, key, flags) as app:
            code, out = tool(project, "burst.py", app.base, "--count", "10")
            time.sleep(2.6)
            before = get_json(f"{app.base}/stats")
            started = time.monotonic()
            output = app.stop(how)
            took = time.monotonic() - started
            lines = shutdown_lines(output)
            rows = confirmed_rows(work / f"{key}.sqlite3")
            log(f"$ {env_line(slow, flags)}", "$ python tools/burst.py --count 10", out.split("\n\n")[1],
                f"GET /stats just before the stop: {json.dumps(before, separators=(',', ':'))}",
                f"$ kill -{how.name}   -> the process ended {took:.1f} s later; it printed:",
                *(lines or ["  (nothing - the process was killed; no shutdown code ran)"]),
                f"Confirmed rows in the database afterwards: {rows}", "")
            results[key] = {"before": before, "shutdown": lines, "rows": rows, "seconds": round(took, 2)}

    # ---------------------------------------------------------------- worker throughput
    log.section("Workers: HOTEL_WORKERS 1, 2, 4 - the bound decides what is accepted, the workers how fast it is finished")
    results["workers"] = {}
    for workers in (1, 2, 4):
        for label, settings, count in (
                ("1 s sender, capacity 10, burst 30", {**slow, "HOTEL_WORKERS": str(workers)}, 30),
                ("0.2 s sender, capacity 100, burst 50",
                 {"HOTEL_EMAIL_SECONDS": "0.2", "HOTEL_QUEUE_CAPACITY": "100", "HOTEL_WORKERS": str(workers)}, 50)):
            name = f"workers{workers}-{count}"
            with server(project, settings, redis_port, work, name) as app:
                code, out = tool(project, "burst.py", app.base, "--count", str(count), "--wait")
                log(f"$ {env_line(settings)}", f"$ python tools/burst.py --count {count} --wait   (exit {code})",
                    out, "")
                final = json.loads(out.split("seconds later\n")[1].splitlines()[0])
                drained = float(re.search(r"GET /stats, ([\d.]+) seconds later", out).group(1))  # type: ignore[union-attr]
                throughput = float(re.search(r"= ([\d.]+) per second", out).group(1))  # type: ignore[union-attr]
                results["workers"][f"{workers}|{label}"] = {
                    "accepted": final["notificationsAccepted"], "rejected": final["notificationsRejected"],
                    "completed": final["notificationsCompleted"], "drained_after": drained,
                    "throughput": throughput}
                app.stop(signal.SIGINT)

    # ---------------------------------------------------------------- failures, retry, timeout
    log.section("Failures: a flaky mail server (every 3rd attempt fails) without and with retry; a hanging one (timeout)")
    results["failures"] = {}
    for key, settings, count in (
            ("fail_every_3_attempts_1", {"HOTEL_EMAIL_SECONDS": "0.05", "HOTEL_QUEUE_CAPACITY": "100",
                                         "HOTEL_EMAIL_FAIL_EVERY": "3", "HOTEL_SEND_ATTEMPTS": "1"}, 30),
            ("fail_every_3_attempts_3", {"HOTEL_EMAIL_SECONDS": "0.05", "HOTEL_QUEUE_CAPACITY": "100",
                                         "HOTEL_EMAIL_FAIL_EVERY": "3", "HOTEL_SEND_ATTEMPTS": "3"}, 30),
            ("timeout", {"HOTEL_EMAIL_SECONDS": "5", "HOTEL_EMAIL_TIMEOUT": "0.5"}, 4)):
        with server(project, settings, redis_port, work, key) as app:
            code, out = tool(project, "burst.py", app.base, "--count", str(count), "--wait")
            output = app.stop(signal.SIGINT)
            warnings = [line for line in output.splitlines() if "failed after" in line or "retrying in" in line]
            log(f"$ {env_line(settings)}", f"$ python tools/burst.py --count {count} --wait   (exit {code})", out,
                "Server log (failures and retries, first 6):", *warnings[:6],
                f"... {len(warnings)} such lines in all", "Server output after Ctrl+C:", *shutdown_lines(output), "")
            final = json.loads(out.split("seconds later\n")[1].splitlines()[0])
            results["failures"][key] = {"final": final, "log_lines": len(warnings),
                                        "drained_after": float(re.search(r"GET /stats, ([\d.]+) seconds later", out).group(1)),  # type: ignore[union-attr]
                                        "bookings": int(re.search(r"Accepted: (\d+)", out).group(1))}  # type: ignore[union-attr]

    # ---------------------------------------------------------------- P09 still holds
    log.section("P09 still holds with the queue: tools/race_http.py --repeat 20 (HOTEL_SLOW_STEP=1, HOTEL_EMAIL_SECONDS=1)")
    race_settings = {"HOTEL_SLOW_STEP": "1", "HOTEL_EMAIL_SECONDS": "1"}
    results["race"] = {}
    with server(project, race_settings, redis_port, work, "race") as first:
        code, out = tool(project, "race_http.py", "--maya", first.base, "--repeat", "20")
        log(f"$ {env_line(race_settings)}", f"$ python tools/race_http.py --repeat 20   (one instance; exit {code})",
            out.split("\n\n")[-1] if "\n\n" in out else out)
        results["race"]["one_instance"] = {"exit": code, "summary": out.strip().splitlines()[-1]}
        settings_second = {**race_settings, "HOTEL_DB_PATH": str(work / "race.sqlite3")}
        with server(project, settings_second, redis_port, work, "race-second") as second:
            code, out = tool(project, "race_http.py", second.base, "--maya", first.base, "--repeat", "20")
            log(f"$ {env_line(settings_second)}   (a second instance, same database file)",
                f"$ python tools/race_http.py <second instance> --repeat 20   (Omar to the second; exit {code})",
                out.split("\n\n")[-1] if "\n\n" in out else out)
            results["race"]["two_instances"] = {"exit": code, "summary": out.strip().splitlines()[-1]}
            log("", "Second instance after Ctrl+C:", *shutdown_lines(second.stop(signal.SIGINT)))
        log("First instance after Ctrl+C:", *shutdown_lines(first.stop(signal.SIGINT)))


def r_p(result: dict[str, Any], share: float) -> float:
    ordered = sorted(result["latencies_ms"])
    return float(ordered[max(1, -(-int(share * 1000) * len(ordered) // 1000)) - 1])


def run_postgres(project: Path, work: Path, redis_port: int, log: Log, results: dict[str, Any]) -> None:
    sys.path.insert(0, str(P09_EVIDENCE))
    import pg_cluster

    from race_experiment import prepare_postgres

    log.section("PostgreSQL 16 (throw-away cluster, pg_wire instead of psycopg): bounded burst, drain, race")
    results["postgres"] = {}
    with pg_cluster.throwaway_cluster(free_port()) as cluster:
        prepare_postgres(cluster, project, with_rule=True)
        version = cluster.psql("-tAc", "SHOW server_version;").stdout.strip()
        log(f"PostgreSQL {version}; schema: db/postgres/init.sql (exclusion constraint + sequence)")
        command = [sys.executable, "-I", str(EVIDENCE / "serve_pg.py"), "--project", str(project),
                   "--pg-port", str(cluster.port)]
        settings = {"HOTEL_EMAIL_SECONDS": "1"}
        with server(project, settings, redis_port, work, "pg-bounded", command=command) as app:
            code, out = tool(project, "burst.py", app.base, "--wait")
            log(f"$ HOTEL_EMAIL_SECONDS=1 python serve_pg.py   (= python main.py --db postgres)",
                f"$ python tools/burst.py --wait   (exit {code})", out)
            output = app.stop(signal.SIGINT)
            log("Server output after Ctrl+C:", *shutdown_lines(output))
            rows = cluster.psql("-tAc", "SELECT count(*) FROM reservations WHERE status = 'Confirmed';").stdout.strip()
            log(f"psql: Confirmed reservations: {rows}")
            results["postgres"]["bounded"] = {
                "burst": json.loads(out.split("GET /stats\n")[1].splitlines()[0]),
                "final": json.loads(out.split("seconds later\n")[1].splitlines()[0]),
                "latency": re.search(r"Booking latency: (.*)", out).group(1),  # type: ignore[union-attr]
                "rows": int(rows), "shutdown": shutdown_lines(output)}
        prepare_postgres(cluster, project, with_rule=True)
        race_settings = {"HOTEL_SLOW_STEP": "1", "HOTEL_EMAIL_SECONDS": "1"}
        with server(project, race_settings, redis_port, work, "pg-race-1", command=command) as one, \
             server(project, race_settings, redis_port, work, "pg-race-2", command=command) as two:
            code, out = tool(project, "race_http.py", two.base, "--maya", one.base, "--repeat", "20")
            log(f"$ HOTEL_SLOW_STEP=1 HOTEL_EMAIL_SECONDS=1 python serve_pg.py   x 2 instances, one database",
                f"$ python tools/race_http.py <second instance> --repeat 20   (exit {code})",
                out.split("\n\n")[-1] if "\n\n" in out else out)
            results["postgres"]["race_two_instances"] = {"exit": code, "summary": out.strip().splitlines()[-1]}
            for running in (one, two):
                running.stop(signal.SIGINT)
        rows = cluster.psql("-tAc", "SELECT room, check_in, count(*) FROM reservations WHERE status = 'Confirmed' "
                                    "GROUP BY 1, 2 HAVING count(*) > 1;").stdout.strip()
        log(f"psql: rooms with two Confirmed reservations for one stay: {rows or 'none'}")
        results["postgres"]["double_booked_pairs"] = rows or "none"


if __name__ == "__main__":
    main()
