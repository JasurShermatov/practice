"""The P08 cache experiment, run for real: the same workload with and without the cache, repeated.

    python3 -I practices/P08-cache-scale-experiment/evidence/run_experiment.py hotel-booking [--rounds 5]

For every run, exactly the same procedure (so the rows can be compared):

1. a fresh SQLite database in a temporary folder (HOTEL_DB_PATH) - empty reservations table, the
   course's two rooms R7/R8, or 40 rooms for the scale scenario (P07's capacity estimate);
2. ``python main.py --port <free port> --cache <off|redis|memory>`` started as a real uvicorn
   server (HOTEL_REDIS_PORT points at one redis-server 7 started by this script, no persistence);
3. a warm-up of 50 searches for another stay (imports, first connections, SQLite page cache);
4. for Redis: FLUSHALL (the course's "empty the cache first"), so the measured stay starts with a miss;
5. ``python tools/measure.py --json`` - the course's workload: 1,000 searches for 12-14 Nov, one
   after another over one keep-alive connection (``--clients 8`` in the concurrency scenario);
6. CPU time of the app process and of redis-server, read from /proc before and after step 5
   (the course's S6 talks about energy; CPU time is the closest thing a container can measure);
7. the app is stopped (SIGINT, like Ctrl+C).

Configurations are interleaved round by round (off, redis, memory, off, redis, ...) so that a
slow moment of the machine does not land on one configuration only. The script writes the raw
output of every run, a JSON file with every number, and a summary table (median, min-max).
Standard library only; needs redis-server and the project's requirements.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

WARM_UP_STAY = ("2026-10-01", "2026-10-03")
CLOCK_TICKS = os.sysconf("SC_CLK_TCK")


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    rooms: int
    clients: int
    caches: tuple[str, ...]
    rounds: int


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def cpu_seconds(pid: int) -> float:
    """utime + stime of a process, from /proc/<pid>/stat (fields 14 and 15)."""
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / CLOCK_TICKS


def redis_cli(port: int, *args: str) -> str:
    return subprocess.run(["redis-cli", "-p", str(port), *args], capture_output=True, text=True, check=True).stdout.strip()


def create_database(path: Path, project: Path, rooms: int) -> None:
    connection = sqlite3.connect(path)
    connection.executescript((project / "db" / "postgres" / "init.sql").read_text(encoding="utf-8"))
    extra = [(f"R{number}", "Standard") for number in range(10, 10 + rooms - 2)]  # R10, R11, ... next to R7/R8
    connection.executemany("INSERT INTO rooms (number, type) VALUES (?, ?)", extra)
    connection.commit()
    assert connection.execute("SELECT count(*) FROM rooms").fetchone()[0] == rooms
    connection.close()


def wait_until_up(port: int, process: subprocess.Popen[bytes], log: Path) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"the app stopped: {log.read_text()}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/stats", timeout=1) as answer:
                if answer.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("the app did not start")


def one_run(project: Path, scenario: Scenario, cache: str, round_number: int, redis_port: int, redis_pid: int,
            searches: int, work: Path) -> dict[str, object]:
    database = work / f"{scenario.name}-{cache}-{round_number}.sqlite3"
    create_database(database, project, scenario.rooms)
    port = free_port()
    log = work / f"{scenario.name}-{cache}-{round_number}.log"
    env = {**os.environ, "HOTEL_DB_PATH": str(database), "HOTEL_REDIS_PORT": str(redis_port), "PYTHONUNBUFFERED": "1"}
    with log.open("wb") as handle:
        app = subprocess.Popen([sys.executable, "main.py", "--port", str(port), "--cache", cache],
                               cwd=project, env=env, stdout=handle, stderr=subprocess.STDOUT)
    try:
        wait_until_up(port, app, log)
        url = f"http://localhost:{port}"
        tool = [sys.executable, "tools/measure.py", "--url", url, "--json"]
        subprocess.run([*tool, *WARM_UP_STAY, "--searches", "50"], cwd=project, check=True, capture_output=True)
        if cache == "redis":
            assert redis_cli(redis_port, "FLUSHALL") == "OK"
        app_before, redis_before = cpu_seconds(app.pid), cpu_seconds(redis_pid)
        measured = subprocess.run([*tool, "--searches", str(searches), "--clients", str(scenario.clients)],
                                  cwd=project, check=True, capture_output=True, text=True)
        app_cpu, redis_cpu = cpu_seconds(app.pid) - app_before, cpu_seconds(redis_pid) - redis_before
    finally:
        app.send_signal(signal.SIGINT)
        app.wait(timeout=10)
    lines = measured.stdout.strip().splitlines()
    result: dict[str, object] = json.loads(lines[-1])
    result.update(scenario=scenario.name, cache=cache, round=round_number, rooms=scenario.rooms,
                  app_cpu_s=round(app_cpu, 3), redis_cpu_s=round(redis_cpu, 3), report="\n".join(lines[:-1]))
    return result


def summary(results: list[dict[str, object]], scenarios: list[Scenario]) -> str:
    def med(values: list[float]) -> str:
        return f"{statistics.median(values):.2f} ({min(values):.2f}-{max(values):.2f})"

    rows = ["| Scenario | Cache | Runs | Database queries | Cache hits / misses | Average ms | p95 ms | p99 ms "
            "| Searches/s | App CPU s | Redis CPU s |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for scenario in scenarios:
        for cache in scenario.caches:
            runs = [r for r in results if r["scenario"] == scenario.name and r["cache"] == cache]
            stats = [r["stats_difference"] for r in runs]
            queries = sorted({s["databaseQueries"] for s in stats})  # type: ignore[index]
            hits = sorted({f'{s["cacheHits"]} / {s["cacheMisses"]}' for s in stats})  # type: ignore[index]
            rows.append(
                f"| {scenario.name} | {cache} | {len(runs)} | {', '.join(map(str, queries))} | {', '.join(hits)} | "
                f"{med([r['average_ms'] for r in runs])} | {med([r['p95_ms'] for r in runs])} | "  # type: ignore[misc]
                f"{med([r['p99_ms'] for r in runs])} | {med([r['throughput_per_s'] for r in runs])} | "  # type: ignore[misc]
                f"{med([r['app_cpu_s'] for r in runs])} | {med([r['redis_cpu_s'] for r in runs])} |")  # type: ignore[misc]
    return "\n".join(rows)


def environment() -> str:
    def version(command: list[str]) -> str:
        return subprocess.run(command, capture_output=True, text=True).stdout.strip().splitlines()[0]

    code = ("import starlette, pydantic, uvicorn, sqlite3; "
            "print(f'starlette {starlette.__version__}, pydantic {pydantic.VERSION}, uvicorn {uvicorn.__version__}, "
            "SQLite {sqlite3.sqlite_version}')")
    cpu = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")), "unknown")
    return "\n".join([
        f"Date (UTC): {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}",
        f"Machine: Linux container, kernel {platform.release()}, {os.cpu_count()} vCPU ({cpu}), "
        f"{os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') // 2**20} MiB RAM",
        f"Python {platform.python_version()}; {version([sys.executable, '-c', code])}",
        f"{version(['redis-server', '--version'])}",
        "App: python main.py (uvicorn, 1 process, access log on), database: SQLite file; "
        "measurement tool on the same machine (client and server share the CPUs)",
    ])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--searches", type=int, default=1000)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "logs")
    args = parser.parse_args(argv)
    project = args.project.resolve()
    scenarios = [
        Scenario("course", "2 rooms, 1 client: the course's workload", 2, 1, ("off", "redis", "memory"), args.rounds),
        Scenario("rooms40", "40 rooms (P07 estimate), 1 client", 40, 1, ("off", "redis"), max(args.rounds - 2, 1)),
        Scenario("clients8", "2 rooms, 8 clients at the same time", 2, 8, ("off", "redis"), max(args.rounds - 2, 1)),
    ]
    work = Path(tempfile.mkdtemp(prefix="p08-experiment-"))
    redis_port = free_port()
    redis = subprocess.Popen(["redis-server", "--port", str(redis_port), "--bind", "127.0.0.1", "--save", "",
                              "--appendonly", "no", "--dir", str(work)], stdout=subprocess.DEVNULL)
    time.sleep(0.3)
    assert redis_cli(redis_port, "PING") == "PONG"
    results: list[dict[str, object]] = []
    raw: list[str] = [environment(), ""]
    print(raw[0], flush=True)
    try:
        for scenario in scenarios:
            raw.append(f"=== Scenario {scenario.name}: {scenario.description}; {args.searches} searches for "
                       f"2026-11-12 to 2026-11-14 per run, {scenario.rounds} rounds, caches {', '.join(scenario.caches)}")
            for round_number in range(1, scenario.rounds + 1):
                for cache in scenario.caches:
                    result = one_run(project, scenario, cache, round_number, redis_port, redis.pid, args.searches, work)
                    results.append(result)
                    block = (f"--- {scenario.name} / cache {cache} / round {round_number} "
                             f"(app CPU {result['app_cpu_s']} s, redis CPU {result['redis_cpu_s']} s)\n{result['report']}")
                    raw.append(block)
                    print(block, flush=True)
    finally:
        redis.terminate()
        redis.wait(timeout=5)
    table = summary(results, scenarios)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "experiment-raw.txt").write_text("\n".join(raw) + "\n", encoding="utf-8")
    (args.out / "experiment-results.json").write_text(
        json.dumps({"environment": raw[0], "results": [{k: v for k, v in r.items() if k != "report"} for r in results]},
                   indent=1) + "\n", encoding="utf-8")
    (args.out / "experiment-summary.md").write_text(
        f"# P08 experiment summary (Observed)\n\n```text\n{raw[0]}\n```\n\nMedian (min-max) over the runs.\n\n{table}\n",
        encoding="utf-8")
    print("\n" + table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
