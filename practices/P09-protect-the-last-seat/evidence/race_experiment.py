"""The race tool, run for real against running servers: before the fix, with an app lock, after the fix.

    python3 -I practices/P09-protect-the-last-seat/evidence/race_experiment.py \
        hotel-booking <version-5 copy of hotel-booking> [--rounds 20] [--burst 100]

For every configuration the script starts the app instance(s) as separate processes (uvicorn),
sharing one database file / one PostgreSQL database and one Redis, then runs the project's own
``tools/race_http.py``:

1. once, as the course does (``HOTEL_SLOW_STEP=1``, Omar 0.5 s after Maya), printing its output and
   then the reservations table *read from the database itself* (sqlite3 / psql);
2. ``--rounds`` more times (``--repeat``): the tool cancels the accepted bookings after each round,
   so every round starts with R7 free; the database is counted again at the end;
3. ``--burst`` rounds without any slow step and without a stagger (both requests at once), to see how
   often the natural, microseconds-wide gap is hit.

Configurations (Step = activity sheet step):

    v5  SQLite, 1 and 2 instances          before the fix (the P08 code, as it was)          Steps 1, 4
    v5 + app lock, 1 and 2 instances       Step 3's in-process lock on the web app            Steps 3, 4
    v6  SQLite, 1 and 2 instances          after the fix: python main.py, HOTEL_SLOW_STEP      Step 7
    v6  PostgreSQL 16, no constraint       the course's state after Step 1, before Step 7     Steps 1, 4
    v6  PostgreSQL 16, db/postgres/init.sql after the fix                                       Step 7

The v6 SQLite instances are started with ``python main.py`` and the environment variables of
Step 1.3 (the real command line). The others go through ``serve.py`` (see its docstring: version 5
has no HOTEL_SLOW_STEP; PostgreSQL needs ``pg_wire`` because psycopg is not installable here).
Every server is stopped at the end of its configuration; the PostgreSQL cluster and Redis at the end.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
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

EVIDENCE = Path(__file__).resolve().parent
sys.path.insert(0, str(EVIDENCE))
from pg_cluster import Cluster, throwaway_cluster  # noqa: E402

PG_PORT = 55433
CONFIRMED_R7 = ("SELECT id, room, check_in, check_out, status FROM reservations "
                "WHERE room = 'R7' AND status = 'Confirmed' ORDER BY id")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextmanager
def redis_server() -> Iterator[int]:
    port = free_port()
    directory = tempfile.mkdtemp(prefix="p09-redis-")
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


@dataclass
class Config:
    key: str
    title: str
    project: Path
    database: str                  # "sqlite" | "postgres-no-rule" | "postgres"
    instances: int
    via_main: bool = False         # start with `python main.py` + HOTEL_* variables
    app_lock: bool = False
    results: dict[str, object] = field(default_factory=dict)


def wait_until_up(base: str) -> None:
    for _ in range(200):
        try:
            with urllib.request.urlopen(f"{base}/stats", timeout=1) as answer:
                answer.read()
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"{base} did not start")


@contextmanager
def instances(config: Config, slow_step: float, db_arg: str, sqlite_file: Path | None,
              redis_port: int, server_log: Path) -> Iterator[list[str]]:
    """Start the instance(s). Their stderr (uvicorn + the app's log) goes to ``server_log``: a pipe that
    nobody reads fills up after 64 KB of tracebacks and then blocks the server (seen in a first run)."""
    ports = [free_port() for _ in range(config.instances)]
    processes = []
    log_file = server_log.open("a", encoding="utf-8")
    env = {**os.environ, "HOTEL_REDIS_PORT": str(redis_port), "PYTHONDONTWRITEBYTECODE": "1"}
    for port in ports:
        if config.via_main:
            command = [sys.executable, "main.py"]  # the project's own code: its folder must be on sys.path
            extra = {"HOTEL_PORT": str(port), "HOTEL_SLOW_STEP": str(slow_step), "HOTEL_DB_PATH": str(sqlite_file)}
            processes.append(subprocess.Popen(command, cwd=config.project, env={**env, **extra},
                                              stdout=subprocess.DEVNULL, stderr=log_file))
        else:
            command = [sys.executable, "-I", str(EVIDENCE / "serve.py"), "--project", str(config.project),
                       "--port", str(port), "--slow-step", str(slow_step), "--db", db_arg]
            if config.app_lock:
                command.append("--app-lock")
            processes.append(subprocess.Popen(command, cwd=config.project, env=env,
                                              stdout=subprocess.DEVNULL, stderr=log_file))
        # one after the other: two processes opening a new SQLite file at once would both create it
        wait_until_up(f"http://127.0.0.1:{port}")
    try:
        yield [f"http://127.0.0.1:{port}" for port in ports]
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        log_file.close()


def server_errors(server_log: Path) -> str:
    """What the servers logged as the cause of their 500 answers, counted (the last line of each traceback)."""
    causes: dict[str, int] = {}
    lines = server_log.read_text(encoding="utf-8").splitlines() if server_log.exists() else []
    for index, line in enumerate(lines):
        # the app's own error log line ("POST /reservations failed") is followed by its traceback;
        # uvicorn prints the same traceback a second time, which is not counted again
        if line.startswith("Traceback") and index and lines[index - 1].endswith(" failed"):
            end = next((j for j in range(index + 1, len(lines)) if lines[j] and not lines[j].startswith((" ", "~", "^"))), None)
            if end is not None:
                causes[lines[end]] = causes.get(lines[end], 0) + 1
    return "; ".join(f"{count} x {cause}" for cause, count in sorted(causes.items())) or "none"


def race_tool(project: Path, bases: list[str], *args: str) -> tuple[int, str]:
    omar = bases[-1]
    done = subprocess.run([sys.executable, "-I", "tools/race_http.py", *( [omar] if len(bases) > 1 else []),
                           "--maya", bases[0], *args], cwd=project, capture_output=True, text=True, timeout=1800)
    return done.returncode, done.stdout + done.stderr


def show_tool_output(text: str) -> str:
    """The tool prints 127.0.0.1:<random port>; show the course's localhost:5080/5081 names instead."""
    ports = list(dict.fromkeys(re.findall(r"127\.0\.0\.1:(\d+)", text)))
    for index, port in enumerate(ports):
        text = text.replace(f"http://127.0.0.1:{port}", f"http://localhost:{5080 + index}")
    return text


class Database:
    """The configuration's database, read directly (not through the app)."""

    def __init__(self, kind: str, sqlite_file: Path | None, cluster: Cluster | None, project: Path) -> None:
        self.kind, self.sqlite_file, self.cluster, self.project = kind, sqlite_file, cluster, project

    def table(self) -> str:
        if self.sqlite_file is not None:
            with closing(sqlite3.connect(self.sqlite_file)) as connection:
                rows = connection.execute(CONFIRMED_R7).fetchall()
            lines = ["  id  | room |  check_in  | check_out  |  status", "------+------+------------+------------+-----------"]
            lines += [f" {i:4} | {r:4} | {a:10} | {b:10} | {s}" for i, r, a, b, s in rows]
            return "\n".join([*lines, f"({len(rows)} row{'s' if len(rows) != 1 else ''})"])
        assert self.cluster is not None
        return self.cluster.psql("-c", CONFIRMED_R7 + ";").stdout.rstrip()

    def confirmed_ids(self) -> list[str]:
        if self.sqlite_file is not None:
            with closing(sqlite3.connect(self.sqlite_file)) as connection:
                return [row[0] for row in connection.execute(CONFIRMED_R7)]
        assert self.cluster is not None
        out = self.cluster.psql("-t", "-A", "-c", "SELECT id FROM reservations WHERE status = 'Confirmed' ORDER BY id;")
        return out.stdout.split()

    def ids_handed_out(self) -> int | None:
        """How many reservation numbers the database has handed out (None: version 5 had no counter)."""
        if self.sqlite_file is not None:
            with closing(sqlite3.connect(self.sqlite_file)) as connection:
                if connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'reservation_ids'").fetchone() is None:
                    return None
                return int(connection.execute("SELECT last_value FROM reservation_ids").fetchone()[0]) - 100
        assert self.cluster is not None
        last, called = self.cluster.psql("-t", "-A", "-F", " ", "-c",
                                         "SELECT last_value, is_called FROM reservation_ids;").stdout.split()
        return int(last) - 100 if called == "t" else 0

    def all_rows(self) -> tuple[int, int]:
        """(all reservation rows, Confirmed rows) - after the repeated rounds every booking was cancelled."""
        sql = "SELECT count(*), coalesce(sum(CASE WHEN status = 'Confirmed' THEN 1 ELSE 0 END), 0) FROM reservations"
        if self.sqlite_file is not None:
            with closing(sqlite3.connect(self.sqlite_file)) as connection:
                total, confirmed = connection.execute(sql).fetchone()
                return int(total), int(confirmed)
        assert self.cluster is not None
        total, confirmed = self.cluster.psql("-t", "-A", "-F", " ", "-c", sql + ";").stdout.split()
        return int(total), int(confirmed)


def prepare_postgres(cluster: Cluster, project: Path, with_rule: bool) -> None:
    cluster.recreate_database()
    sql = (project / "db" / "postgres" / "init.sql").read_text(encoding="utf-8")
    if not with_rule:  # the course's database after Step 1 and before Step 7: sequence yes, constraint no
        sql = re.sub(r",\s*(--[^\n]*\n\s*)*CONSTRAINT reservations_no_overlap EXCLUDE USING gist \(.*?\) "
                     r"WHERE \(status = 'Confirmed'\)", "", sql, flags=re.DOTALL)
        sql = sql.replace("CREATE EXTENSION IF NOT EXISTS btree_gist;", "")
        assert "EXCLUDE USING" not in sql.split("CREATE INDEX")[0].split("CREATE TABLE reservations")[1]
    done = cluster.psql("-q", "-v", "ON_ERROR_STOP=1", input_text=sql)
    if done.returncode:
        raise RuntimeError(done.stderr)


def cancel_through_the_api(base: str, ids: list[str]) -> None:
    for reservation_id in ids:
        request = urllib.request.Request(f"{base}/reservations/{reservation_id}", method="DELETE")
        with urllib.request.urlopen(request, timeout=10) as answer:
            assert answer.status == 204


def run_config(config: Config, cluster: Cluster | None, redis_port: int, rounds: int, burst: int,
               log: list[str], tool_project: Path) -> None:
    """``tool_project``: where tools/race_http.py lives (version 6) - the same tool for every configuration."""
    work = Path(tempfile.mkdtemp(prefix="p09-race-"))
    try:
        run_phases(config, cluster, redis_port, rounds, burst, log, tool_project, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def run_phases(config: Config, cluster: Cluster | None, redis_port: int, rounds: int, burst: int,
               log: list[str], tool_project: Path, work: Path) -> None:
    log.append(f"\n{'=' * 100}\n{config.title}\n{'=' * 100}")

    for phase, slow, stagger, count in (("course", 1.0, 0.5, rounds), ("burst", 0.0, 0.0, burst)):
        if count == 0:
            continue
        sqlite_file = work / f"{phase}.sqlite3" if config.database == "sqlite" else None
        if config.database.startswith("postgres"):
            assert cluster is not None
            prepare_postgres(cluster, config.project, with_rule=config.database == "postgres")
        db_arg = f"sqlite:{sqlite_file}" if sqlite_file else f"postgres:{PG_PORT}"
        database = Database(config.database, sqlite_file, cluster, config.project)
        server_log = work / f"{phase}-servers.log"
        pg_log = cluster.directory / "server.log" if cluster is not None and config.database.startswith("postgres") else None
        pg_log_start = pg_log.stat().st_size if pg_log is not None else 0
        with instances(config, slow, db_arg, sqlite_file, redis_port, server_log) as bases:
            if phase == "course":
                code, out = race_tool(tool_project, bases)
                log.append(f"\n$ HOTEL_SLOW_STEP=1 ... ; python tools/race_http.py"
                           f"{' http://localhost:5081' if len(bases) > 1 else ''}      (exit status {code})")
                log.append(show_tool_output(out).rstrip())
                log.append("\n-- the reservations table, read from the database itself (Confirmed rows for R7):")
                log.append(database.table())
                config.results["single run confirmed rows"] = len(database.confirmed_ids())
                cancel_through_the_api(bases[0], database.confirmed_ids())
                code, out = race_tool(tool_project, bases, "--repeat", str(count), "--stagger", str(stagger))
                log.append(f"\n$ python tools/race_http.py{' <5081>' if len(bases) > 1 else ''} --repeat {count}   "
                           f"(slow step {slow} s, Omar {stagger} s after Maya; exit status {code})")
            else:
                code, out = race_tool(tool_project, bases, "--repeat", str(count), "--stagger", "0")
                log.append(f"\n$ (HOTEL_SLOW_STEP=0) python tools/race_http.py{' <5081>' if len(bases) > 1 else ''} "
                           f"--repeat {count} --stagger 0   (both at once, no slow step; exit status {code})")
            lines = out.rstrip().splitlines()
            log.append("\n".join(lines if phase == "course" else [*lines[:5], "  ...", *lines[-3:]]))
            summary = re.search(r"Double bookings: (\d+) of (\d+) rounds; one 201 and one 409: (\d+); anything else: (\d+)", out)
            if summary is None:  # the tool itself failed: keep its output as evidence and go on
                log.append("-- the race tool ended without a summary; output above")
                config.results[phase] = {"tool_failed": True}
                continue
            double, total, correct, other = (int(group) for group in summary.groups())
            log.append(f"-- errors the server(s) logged (cause of each 500): {server_errors(server_log)}")
            postgres_counts = {}
            if pg_log is not None:
                with pg_log.open(encoding="utf-8", errors="replace") as handle:
                    handle.seek(pg_log_start)
                    postgres_said = handle.read()
                deadlocks = postgres_said.count("ERROR:  deadlock detected")
                refusals = postgres_said.count('violates exclusion constraint "reservations_no_overlap"')
                log.append(f"-- PostgreSQL's own log for this phase: {refusals} x 23P01 reservations_no_overlap, "
                           f"{deadlocks} x 40P01 deadlock detected")
                postgres_counts = {"postgres_23P01": refusals, "postgres_40P01": deadlocks}
            total_rows, confirmed_left = database.all_rows()
            log.append(f"-- database after the rounds: {total_rows} reservation rows, {confirmed_left} still Confirmed "
                       f"(the tool cancels what it booked)")
            config.results[phase] = {"rounds": total, "double_booked": double, "one_201_one_409": correct,
                                     "other": other, "rows_in_database": total_rows, **postgres_counts}
            handed_out = database.ids_handed_out()
            if handed_out is not None:
                # Every accepted booking used one number; a number more means a request passed the
                # pre-check, drew an id and was then refused by the database - it lost the race.
                refused_by_database = handed_out - total_rows
                log.append(f"-- ids handed out by the database: {handed_out}; bookings that passed the pre-check and were "
                           f"refused by the database itself (lost the race): {refused_by_database}")
                config.results[phase]["refused_by_the_database"] = refused_by_database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path, help="the hotel-booking folder (version 6)")
    parser.add_argument("version5", type=Path, help="a copy of hotel-booking as it was at the end of P08")
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--burst", type=int, default=100)
    parser.add_argument("--only", default="", help="comma-separated configuration keys (default: all)")
    parser.add_argument("--json", type=Path, help="write the results here")
    args = parser.parse_args()
    v6, v5 = args.project.resolve(), args.version5.resolve()
    configs = [
        Config("v5-sqlite-1", "BEFORE - version 5 (P08 code), SQLite, ONE instance", v5, "sqlite", 1),
        Config("v5-sqlite-2", "BEFORE - version 5 (P08 code), SQLite, TWO instances (Step 4)", v5, "sqlite", 2),
        Config("v5-lock-1", "STEP 3 - version 5 + an in-process lock around every request, ONE instance", v5, "sqlite", 1,
               app_lock=True),
        Config("v5-lock-2", "STEP 4 - version 5 + the same in-process lock, TWO instances", v5, "sqlite", 2, app_lock=True),
        Config("v6-sqlite-1", "AFTER - version 6 (P09), SQLite (triggers), ONE instance - python main.py", v6, "sqlite", 1,
               via_main=True),
        Config("v6-sqlite-2", "AFTER - version 6 (P09), SQLite (triggers), TWO instances - python main.py", v6, "sqlite", 2,
               via_main=True),
        Config("v6-pg-norule-1", "BEFORE STEP 7 - version 6 code on PostgreSQL 16 WITHOUT the constraint, ONE instance",
               v6, "postgres-no-rule", 1),
        Config("v6-pg-norule-2", "BEFORE STEP 7 - version 6 code on PostgreSQL 16 WITHOUT the constraint, TWO instances",
               v6, "postgres-no-rule", 2),
        Config("v6-pg-1", "AFTER - version 6 on PostgreSQL 16 with db/postgres/init.sql (exclusion constraint), ONE instance",
               v6, "postgres", 1),
        Config("v6-pg-2", "AFTER - version 6 on PostgreSQL 16 with db/postgres/init.sql (exclusion constraint), TWO instances",
               v6, "postgres", 2),
    ]
    wanted = set(filter(None, args.only.split(",")))
    configs = [config for config in configs if not wanted or config.key in wanted]
    log = [f"Linux container, Python {sys.version.split()[0]}, SQLite {sqlite3.sqlite_version}; "
           f"rounds={args.rounds}, burst={args.burst}"]
    with redis_server() as redis_port, throwaway_cluster(PG_PORT) as cluster:
        log.append(cluster.psql("-t", "-A", "-c", "SELECT version();").stdout.strip())
        for config in configs:
            run_config(config, cluster, redis_port, args.rounds, args.burst, log, v6)
            print(log[-1] if len(log) else "", file=sys.stderr)
    print("\n".join(log))
    results = {config.key: {"title": config.title, **config.results} for config in configs}
    print("\nSUMMARY " + json.dumps(results))
    if args.json:
        args.json.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
