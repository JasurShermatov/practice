"""P10: a burst of bookings as fast as one client can send them, then what the notification queue did.

    python tools/burst.py                         30 bookings to http://localhost:5080, then GET /stats
    python tools/burst.py --wait                  ... then wait for the workers and print the drain time
                                                  and their throughput (emails per second)
    python tools/burst.py http://localhost:5081 --count 100 --year 2027 --json

Start the app with ``HOTEL_EMAIL_SECONDS=1`` first (``HOTEL_EMAIL_SECONDS=1 python main.py``), so the
confirmation sender is as slow as a real mail server.

Every booking is for a different room and night - R7 and R8, one night each from 1 December of
``--year`` on - so all of them are legal under P09's no-overlap rule and none is refused by the
booking rule. Whatever is refused here was refused by the notification queue, which is the thing
being measured. (Run it a second time against the same database with another ``--year``: the
nights of the first run are taken.)

The bookings are sent one after another, as in the course. The first lines are the course's
(Accepted / Rejected / Slowest booking / Total, then GET /stats); the lines after them add the
latency distribution of the booking requests and how many answers said ``notificationFailed``.
With ``--wait`` the tool keeps reading GET /stats until every accepted confirmation has ended
(completed + failed == accepted, queued == 0) and prints how long that took after the burst and how
many emails per second the workers finished.

Exit status: 0 when every booking was answered 201, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

BASE = "http://localhost:5080"
BURST = 30
TIMEOUT_SECONDS = 60.0


@dataclass
class BurstResult:
    """What one burst produced; ``--json`` prints it."""

    count: int
    accepted: int = 0                 # answered 201 - the guest has the room
    rejected: int = 0                 # any other answer
    notification_failed: int = 0      # 201 answers that said notificationFailed: true
    latencies_ms: list[float] = field(default_factory=list)
    total_seconds: float = 0.0
    stats: dict[str, Any] = field(default_factory=dict)
    drained_after_seconds: float | None = None    # --wait: burst end -> nothing left queued or in flight
    final_stats: dict[str, Any] | None = None
    throughput_per_second: float | None = None    # --wait: finished emails / (burst start -> drained)

    def percentile(self, share: float) -> float:
        """Nearest-rank percentile of the booking latencies, in milliseconds."""
        ordered = sorted(self.latencies_ms)
        return ordered[max(1, math.ceil(share * len(ordered))) - 1] if ordered else 0.0


def stay(index: int, year: int) -> tuple[str, str, str]:
    """Booking ``index``: R7 or R8 alternately, one night each, 1 December onwards."""
    night = date(year, 12, 1) + timedelta(days=index // 2)
    return ("R7" if index % 2 == 0 else "R8"), night.isoformat(), (night + timedelta(days=1)).isoformat()


def book(base: str, index: int, year: int) -> tuple[int, dict[str, Any], float]:
    room, check_in, check_out = stay(index, year)
    body = {"guestName": f"Guest{index + 1}", "guestEmail": f"guest{index + 1}@example.com",
            "room": room, "checkIn": check_in, "checkOut": check_out}
    request = urllib.request.Request(f"{base}/reservations", method="POST", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            answer = json.loads(response.read() or b"{}")
            return response.status, answer, time.perf_counter() - started
    except urllib.error.HTTPError as error:
        error.read()
        return error.code, {}, time.perf_counter() - started


def read_stats(base: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{base}/stats", timeout=TIMEOUT_SECONDS) as response:
        stats: dict[str, Any] = json.loads(response.read())
        return stats


def caught_up(stats: dict[str, Any]) -> bool:
    """Every confirmation the queue took has ended (sent or failed) and none is waiting."""
    if "notificationsAccepted" not in stats:
        return True  # no queue: the emails were sent inside the requests
    ended = int(stats["notificationsCompleted"]) + int(stats.get("notificationsFailed", 0))
    return int(stats["notificationsQueued"]) == 0 and ended >= int(stats["notificationsAccepted"])


def run(base: str, count: int, year: int, wait: bool, wait_limit: float = 600.0) -> BurstResult:
    result = BurstResult(count)
    started = time.perf_counter()
    for index in range(count):
        status, answer, seconds = book(base, index, year)
        result.latencies_ms.append(seconds * 1000)
        if status == 201:
            result.accepted += 1
            result.notification_failed += bool(answer.get("notificationFailed"))
        else:
            result.rejected += 1
    burst_ended = time.perf_counter()
    result.total_seconds = burst_ended - started
    result.stats = read_stats(base)
    if wait:
        deadline = burst_ended + wait_limit
        stats = result.stats
        while not caught_up(stats) and time.perf_counter() < deadline:
            time.sleep(0.05)
            stats = read_stats(base)
        drained = time.perf_counter()
        result.final_stats = stats
        result.drained_after_seconds = drained - burst_ended
        finished = stats.get("notificationsCompleted", 0) + stats.get("notificationsFailed", 0)
        result.throughput_per_second = finished / (drained - started) if finished else 0.0
    return result


def as_text(seconds: float) -> str:
    """The course's style: milliseconds under a second, seconds with two decimals above."""
    return f"{seconds * 1000:.0f} ms" if seconds < 1 else f"{seconds:.2f} s"


def report(result: BurstResult) -> str:
    stats = result.stats
    lines = [f"Sending {result.count} bookings, one after another...", "",
             f"Accepted: {result.accepted}", f"Rejected: {result.rejected}",
             f"Slowest booking: {as_text(max(result.latencies_ms, default=0) / 1000)}",
             f"Total: {result.total_seconds:.1f} s", "",
             "GET /stats", json.dumps(stats, separators=(",", ":")), "",
             f"Booking latency: p50 {result.percentile(0.50):.1f} ms, p95 {result.percentile(0.95):.1f} ms, "
             f"max {max(result.latencies_ms, default=0):.1f} ms",
             f"Answers with notificationFailed: true: {result.notification_failed}"]
    if "notificationsAccepted" in stats:
        lines.append(f"accepted + rejected = {stats['notificationsAccepted'] + stats['notificationsRejected']}"
                     f" (bookings: {result.accepted}); queued {stats['notificationsQueued']}")
    if result.final_stats is not None and result.drained_after_seconds is not None:
        final = result.final_stats
        lines += ["", f"GET /stats, {result.drained_after_seconds:.1f} seconds later",
                  json.dumps(final, separators=(",", ":"))]
        if "notificationsAccepted" in final:
            accepted, completed = final["notificationsAccepted"], final["notificationsCompleted"]
            failed, queued = final.get("notificationsFailed", 0), final["notificationsQueued"]
            verdict = ("Everything the queue took, it finished." if accepted == completed + failed + queued
                       else "The two sides do not balance: work was lost.")
            lines += ["", f"accepted {accepted} = completed {completed} + failed {failed} + queued {queued}. {verdict}",
                      f"Worker throughput: {completed + failed} emails in "
                      f"{result.total_seconds + result.drained_after_seconds:.1f} s = "
                      f"{result.throughput_per_second or 0:.2f} per second"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base", nargs="?", default=BASE, help=f"the app (default {BASE})")
    parser.add_argument("--count", type=int, default=BURST, help=f"bookings in the burst (default {BURST})")
    parser.add_argument("--year", type=int, default=2026, help="December of this year (default 2026)")
    parser.add_argument("--wait", action="store_true", help="wait for the workers to catch up and time them")
    parser.add_argument("--json", action="store_true", help="print the result as JSON instead of text")
    args = parser.parse_args(argv)
    result = run(args.base.rstrip("/"), args.count, args.year, args.wait)
    print(json.dumps(asdict(result)) if args.json else report(result))
    return 0 if result.rejected == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
