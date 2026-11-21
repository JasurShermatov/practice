"""P08 Steps 2, 3, 5, 6, 7 and 8, run for real against the app, redis-server, curl and redis-cli.

    python3 -I practices/P08-cache-scale-experiment/evidence/cache_behaviour.py hotel-booking

Every part starts the app the way a person would (``python main.py --port <port> [...]``) over a
fresh SQLite file, with a redis-server 7 started by this script (the Mac uses ``docker compose``
and redis:8 instead; the commands GET, SET EX, INCR, KEYS, TTL, FLUSHALL are the same). Each
command is printed with its real output:

A  Step 2: Redis answers PONG.
B  Step 3: two searches leave one key in Redis; its TTL is <= 30 s.
C  Step 5: the stale result, with ``--no-invalidation``: search, Maya books R7, search (R7 still
   listed), Omar asks for R7 (409).
D  Step 6: the same four requests with invalidation: the third answer is R8 only.
E  Step 7: the New Year hot key - 1,000 searches, KEYS, one New Year booking, one search, KEYS (two
   versions side by side), 31 s later KEYS again (the old copy expired by itself).
F  Step 7: a busy sale - 40 rooms, 1,000 New Year searches with a booking after every 50th: what
   the hit rate and the database queries become when every booking empties the copies.
G  Step 8: Redis stops while the app runs - search, booking, stats - and starts again.
"""
from __future__ import annotations

import json
import os
import shlex
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SEARCH = "/rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14"
NEW_YEAR = "/rooms/availability?checkIn=2026-12-31&checkOut=2027-01-02"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Lab:
    def __init__(self, project: Path) -> None:
        self.project = project
        self.work = Path(tempfile.mkdtemp(prefix="p08-behaviour-"))
        self.redis_port = free_port()
        self.redis: subprocess.Popen[bytes] | None = None
        self.app_port = 0
        self.runs = 0

    # ---------------------------------------------------------------- printing a command and its output

    def sh(self, command: str, show: str | None = None) -> str:
        """Run a shell command in the project folder; print it (as a person would type it) and its output."""
        result = subprocess.run(["bash", "-c", command], cwd=self.project, capture_output=True, text=True)
        output = (result.stdout + result.stderr).rstrip()
        print(f"$ {show or command}")
        if output:
            print(output)
        return output

    def curl(self, method: str, path: str, body_file: str | None = None) -> str:
        data = f' -H "Content-Type: application/json" --data "@{body_file}"' if body_file else ""
        verb = "" if method == "GET" else f" -X {method}"
        write_out = "%{http_code}  X-Cache: %header{x-cache}" if method == "GET" else "%{http_code}"
        command = (f'curl -s -w "\\n{write_out}\\n"{verb}{data} '
                   f'"http://localhost:{self.app_port}{path}"')
        return self.sh(command, show=command.replace(str(self.app_port), "5080"))

    def cli(self, *args: str) -> str:
        quoted = " ".join(shlex.quote(arg) for arg in args)
        return self.sh(f"redis-cli -p {self.redis_port} {quoted}", show=f"redis-cli {quoted}")

    # ---------------------------------------------------------------- Redis and the app

    def start_redis(self) -> None:
        self.redis = subprocess.Popen(["redis-server", "--port", str(self.redis_port), "--bind", "127.0.0.1",
                                       "--save", "", "--appendonly", "no", "--dir", str(self.work)],
                                      stdout=subprocess.DEVNULL)
        for _ in range(50):
            if subprocess.run(["redis-cli", "-p", str(self.redis_port), "PING"], capture_output=True,
                              text=True).stdout.strip() == "PONG":
                return
            time.sleep(0.1)
        raise RuntimeError("redis-server did not start")

    def stop_redis(self) -> None:
        if self.redis is not None:
            self.redis.terminate()
            self.redis.wait(timeout=5)
            self.redis = None

    @contextmanager
    def app(self, *flags: str, rooms: int = 2) -> Iterator[None]:
        self.runs += 1
        database = self.work / f"hotel-{self.runs}.sqlite3"
        if rooms > 2:
            connection = sqlite3.connect(database)
            connection.executescript((self.project / "db/postgres/init.sql").read_text(encoding="utf-8"))
            connection.executemany("INSERT INTO rooms VALUES (?, 'Standard')",
                                   [(f"R{n}",) for n in range(10, 10 + rooms - 2)])
            connection.commit()
            connection.close()
        self.app_port = free_port()
        log = self.work / f"app-{self.runs}.log"
        env = {**os.environ, "HOTEL_DB_PATH": str(database), "HOTEL_REDIS_PORT": str(self.redis_port),
               "PYTHONUNBUFFERED": "1"}
        print(f"\n(app started: python main.py {' '.join(flags)}".rstrip() + f", fresh database, {rooms} rooms)")
        with log.open("wb") as handle:
            process = subprocess.Popen([sys.executable, "main.py", "--port", str(self.app_port), *flags],
                                       cwd=self.project, env=env, stdout=handle, stderr=subprocess.STDOUT)
        try:
            for _ in range(150):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{self.app_port}/stats", timeout=1):
                        break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError(log.read_text())
                    time.sleep(0.1)
            yield
        finally:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=10)
            warnings = [line for line in log.read_text().splitlines() if "failed" in line or "ERROR" in line]
            for line in warnings:
                print(f"(app log) {line}")

    def get_json(self, path: str) -> dict[str, object]:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.app_port}{path}") as answer:
            body: dict[str, object] = json.load(answer)
            return body

    def post(self, body: dict[str, str]) -> int:
        request = urllib.request.Request(f"http://127.0.0.1:{self.app_port}/reservations", method="POST",
                                         data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request) as answer:
            return answer.status


def heading(text: str) -> None:
    print(f"\n{'=' * 100}\n{text}\n{'=' * 100}")


def main(argv: list[str]) -> int:
    lab = Lab(Path(argv[0]).resolve())
    print(f"Date (UTC): {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}; Linux container; "
          f"Python {sys.version.split()[0]}; {subprocess.run(['redis-server', '--version'], capture_output=True, text=True).stdout.split()[2]}; "
          f"{subprocess.run(['curl', '--version'], capture_output=True, text=True).stdout.split()[1]} (curl)")
    print("Ports: the app runs on a free port and Redis on another; both are shown as 5080 / the default port.")
    lab.start_redis()
    try:
        heading("A  Step 2 - Redis answers (here: redis-server started by this script; on the Mac: docker compose exec cache redis-cli ping)")
        lab.cli("ping")

        heading("B  Step 3 - search 12-14 Nov twice: one key in Redis, kept for at most 30 s")
        lab.cli("FLUSHALL")
        with lab.app():
            lab.curl("GET", SEARCH)
            lab.curl("GET", SEARCH)
            lab.cli("KEYS", "availability:*")
            lab.cli("GET", "availability:v0:2026-11-12:2026-11-14")
            lab.cli("TTL", "availability:v0:2026-11-12:2026-11-14")
            lab.sh(f"curl -s http://localhost:{lab.app_port}/stats", show="curl -s http://localhost:5080/stats")

        heading("C  Step 5 - the stale result: empty database, empty cache, app WITHOUT invalidation")
        lab.cli("FLUSHALL")
        with lab.app("--no-invalidation"):
            lab.curl("GET", SEARCH)
            lab.curl("POST", "/reservations", "docs/requests/maya-r7.json")
            lab.curl("GET", SEARCH)
            lab.curl("POST", "/reservations", "docs/requests/omar-r7.json")
            lab.cli("KEYS", "availability:*")

        heading("D  Step 6 - the same four requests with invalidation (empty database, empty cache)")
        lab.cli("FLUSHALL")
        with lab.app():
            lab.curl("GET", SEARCH)
            lab.curl("POST", "/reservations", "docs/requests/maya-r7.json")
            lab.curl("GET", SEARCH)
            lab.curl("POST", "/reservations", "docs/requests/omar-r7.json")
            lab.cli("KEYS", "availability:*")
            lab.cli("GET", "availability:version")
            lab.curl("DELETE", "/reservations/R101")
            lab.curl("GET", SEARCH)
            lab.cli("GET", "availability:version")

        heading("E  Step 7 - the New Year hot key: 1,000 searches, a booking, the versions side by side, expiry")
        lab.cli("FLUSHALL")
        with lab.app():
            lab.sh(f"python3 tools/measure.py 2026-12-31 2027-01-02 --url http://localhost:{lab.app_port}",
                   show="python3 tools/measure.py 2026-12-31 2027-01-02")
            lab.cli("KEYS", "availability:*")
            lab.curl("POST", "/reservations", "docs/requests/maya-newyear.json")
            lab.curl("GET", NEW_YEAR)
            lab.cli("KEYS", "availability:*")
            lab.cli("TTL", "availability:v0:2026-12-31:2027-01-02")
            print("(waiting 31 seconds: longer than the TTL)")
            time.sleep(31)
            lab.cli("KEYS", "availability:*")
            lab.curl("GET", NEW_YEAR)
            lab.sh(f"curl -s http://localhost:{lab.app_port}/stats", show="curl -s http://localhost:5080/stats")

        heading("F  Step 7 - a busy New Year sale: 40 rooms, 1,000 searches, a booking after every 50th search")
        lab.cli("FLUSHALL")
        with lab.app(rooms=40):
            before = lab.get_json("/stats")
            booked = 0
            started = time.perf_counter()
            for number in range(1, 1001):
                lab.get_json(NEW_YEAR)
                if number % 50 == 0:
                    room = f"R{10 + booked}"
                    assert lab.post({"guestName": f"Guest {booked}", "guestEmail": f"g{booked}@example.com",
                                     "room": room, "checkIn": "2026-12-31", "checkOut": "2027-01-02"}) == 201
                    booked += 1
            elapsed = time.perf_counter() - started
            after = lab.get_json("/stats")
            difference = {name: int(after[name]) - int(before[name]) for name in after}  # type: ignore[call-overload]
            print(f"1000 New Year searches and {booked} bookings in {elapsed:.1f} s")
            print(f"GET /stats difference: {json.dumps(difference, separators=(',', ':'))}")
            hits = difference["cacheHits"]
            print(f"Hit rate: {hits}/{difference['searches']} = {hits / difference['searches']:.1%}; "
                  f"database queries: {difference['databaseQueries']} "
                  f"(searches {difference['cacheMisses']} misses x 40 rooms = {difference['cacheMisses'] * 40}, "
                  f"bookings {booked} x 3 = {booked * 3})")
            print("Without the cache the same 1,000 searches would ask 1000 x 40 = 40000 questions.")
            lab.cli("GET", "availability:version")

        heading("G  Step 8 - Redis stops while the app runs, then starts again")
        lab.cli("FLUSHALL")
        with lab.app():
            lab.curl("GET", SEARCH)
            lab.curl("GET", SEARCH)
            print("(redis-server stopped - on the Mac: docker compose stop cache)")
            lab.stop_redis()
            lab.curl("GET", SEARCH)
            lab.curl("POST", "/reservations", "docs/requests/maya-r7.json")
            lab.curl("GET", SEARCH)
            lab.curl("POST", "/reservations", "docs/requests/maya-r7.json")
            lab.sh(f"curl -s http://localhost:{lab.app_port}/stats", show="curl -s http://localhost:5080/stats")
            print("(redis-server started again, empty - on the Mac: docker compose start cache)")
            lab.start_redis()
            lab.curl("GET", SEARCH)
            lab.curl("GET", SEARCH)
            lab.cli("KEYS", "availability:*")
            lab.sh(f"curl -s http://localhost:{lab.app_port}/stats", show="curl -s http://localhost:5080/stats")
    finally:
        lab.stop_redis()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
