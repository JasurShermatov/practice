"""Send searches to the running app and print how long they took and what they cost (P08 Step 1).

    python tools/measure.py                           1,000 searches for 12-14 Nov, one after another
    python tools/measure.py 2026-12-31 2027-01-02     other dates (Step 7: the New Year hot key)
    python tools/measure.py --clients 8               the same 1,000 searches from 8 clients at once
    python tools/measure.py --json                    one JSON line at the end, for scripts

It reads GET /stats, sends the searches and times each one, reads GET /stats again and prints the
average, p95, total and the difference of the counters - what the searches cost the database and
the cache. Standard library only. Each client keeps ONE HTTP connection open for all its requests,
so the times show the app, not the opening of new connections. A search that does not answer 200
stops the tool (a wrong answer must never be counted as a fast one).

p95 is the nearest-rank percentile: sort the times, take the ceil(0.95 * n)-th - for 1,000
searches the 950th; only 50 searches were slower. The average hides slow searches; p95 shows what
an unlucky guest waits (S1: p95 <= 1 s).
"""
from __future__ import annotations

import argparse
import http.client
import json
import math
import sys
import threading
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

DEFAULT_URL = "http://localhost:5080"
DEFAULT_STAY = ("2026-11-12", "2026-11-14")


class MeasureError(Exception):
    """The app did not answer as expected; the run is not valid."""


@dataclass(frozen=True)
class Result:
    searches: int
    clients: int
    check_in: str
    check_out: str
    average_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    total_s: float
    throughput_per_s: float
    stats_difference: dict[str, int]
    x_cache: dict[str, int]  # how many answers said hit / miss / bypass


def percentile(sorted_times: Sequence[float], share: float) -> float:
    """Nearest-rank percentile of already sorted values: the ceil(share * n)-th value."""
    if not sorted_times:
        raise ValueError("no times")
    return sorted_times[max(math.ceil(share * len(sorted_times)), 1) - 1]


def difference(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    """What the run added to every counter (the app's counters only grow)."""
    return {name: after[name] - before.get(name, 0) for name in after}


class Client:
    """One keep-alive HTTP connection to the app."""

    def __init__(self, url: str) -> None:
        parts = urlsplit(url)
        self._connection = http.client.HTTPConnection(parts.hostname or "localhost", parts.port or 80, timeout=10)

    def get(self, path: str) -> tuple[str, str | None]:
        self._connection.request("GET", path)
        response = self._connection.getresponse()
        body = response.read().decode("utf-8")
        if response.status != 200:
            raise MeasureError(f"GET {path} answered {response.status}: {body}")
        return body, response.getheader("X-Cache")

    def stats(self) -> dict[str, int]:
        body, _ = self.get("/stats")
        counters: dict[str, int] = json.loads(body)
        return counters

    def close(self) -> None:
        self._connection.close()


def measure(url: str, check_in: str, check_out: str, searches: int = 1000, clients: int = 1) -> Result:
    if searches < 1 or clients < 1 or clients > searches:
        raise ValueError("need 1 <= clients <= searches")
    path = f"/rooms/availability?checkIn={check_in}&checkOut={check_out}"
    counter = Client(url)
    before = counter.stats()

    shares = [searches // clients + (1 if index < searches % clients else 0) for index in range(clients)]
    times: list[list[float]] = [[] for _ in range(clients)]
    labels: list[dict[str, int]] = [{} for _ in range(clients)]
    errors: list[BaseException] = []
    start_together = threading.Barrier(clients + 1)

    def run(index: int) -> None:
        client = Client(url)
        try:
            start_together.wait()
            for _ in range(shares[index]):
                started = time.perf_counter()
                _, label = client.get(path)
                times[index].append((time.perf_counter() - started) * 1000)
                key = label or "none"
                labels[index][key] = labels[index].get(key, 0) + 1
        except BaseException as error:  # noqa: BLE001 - reported after the run
            errors.append(error)
        finally:
            client.close()

    threads = [threading.Thread(target=run, args=(index,)) for index in range(clients)]
    for thread in threads:
        thread.start()
    start_together.wait()
    started = time.perf_counter()
    for thread in threads:
        thread.join()
    total = time.perf_counter() - started
    if errors:
        raise MeasureError(str(errors[0]))
    after = counter.stats()
    counter.close()

    all_times = sorted(t for client_times in times for t in client_times)
    x_cache: dict[str, int] = {}
    for client_labels in labels:
        for key, count in client_labels.items():
            x_cache[key] = x_cache.get(key, 0) + count
    return Result(
        searches=searches, clients=clients, check_in=check_in, check_out=check_out,
        average_ms=sum(all_times) / len(all_times), p50_ms=percentile(all_times, 0.50),
        p95_ms=percentile(all_times, 0.95), p99_ms=percentile(all_times, 0.99), max_ms=all_times[-1],
        total_s=total, throughput_per_s=searches / total, stats_difference=difference(before, after),
        x_cache=dict(sorted(x_cache.items())),
    )


def report(result: Result) -> str:
    """The course's five lines first, then the extra ones."""
    counters = json.dumps(result.stats_difference, separators=(",", ":"))
    return "\n".join([
        f"{result.searches} searches for {result.check_in} to {result.check_out}",
        f"Average: {result.average_ms:.1f} ms",
        f"p95: {result.p95_ms:.1f} ms",
        f"Total: {result.total_s:.1f} s",
        f"GET /stats difference: {counters}",
        f"Clients: {result.clients}   Throughput: {result.throughput_per_s:.0f} searches/s",
        f"p50: {result.p50_ms:.2f} ms   p95: {result.p95_ms:.2f} ms   p99: {result.p99_ms:.2f} ms   "
        f"max: {result.max_ms:.2f} ms   average: {result.average_ms:.2f} ms",
        f"X-Cache answers: {json.dumps(result.x_cache, separators=(',', ':'))}",
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Time searches against the running hotel app.")
    parser.add_argument("stay", nargs="*", default=list(DEFAULT_STAY), metavar="DATE",
                        help="check-in and check-out (default: 2026-11-12 2026-11-14)")
    parser.add_argument("--searches", type=int, default=1000)
    parser.add_argument("--clients", type=int, default=1, help="clients searching at the same time (default 1)")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--json", action="store_true", help="also print the result as one JSON line")
    args = parser.parse_args(argv)
    if len(args.stay) != 2:
        parser.error("give both dates: CHECK_IN CHECK_OUT")
    try:
        result = measure(args.url, args.stay[0], args.stay[1], args.searches, args.clients)
    except (MeasureError, OSError) as error:
        print(f"measure: {error}", file=sys.stderr)
        return 1
    print(report(result))
    if args.json:
        print(json.dumps(asdict(result), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
