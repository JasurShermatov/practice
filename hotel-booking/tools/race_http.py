"""P09 Step 1: two POST /reservations for the same room and nights at the same moment, and what each got.

    python tools/race_http.py                          both bookings to http://localhost:5080
    python tools/race_http.py http://localhost:5081    Omar's booking to a second instance (Step 4)
    python tools/race_http.py --repeat 20              20 rounds; after each round the accepted
                                                       bookings are cancelled, so every round starts
                                                       with R7 free; a summary line at the end
    python tools/race_http.py --repeat 100 --stagger 0 --json   both at once, machine-readable summary

Start the app with ``HOTEL_SLOW_STEP=1`` first (``HOTEL_SLOW_STEP=1 python main.py``). The slow step
does not make the bug possible - checking and saving are two statements, and the gap between them
is there in every booking - it only makes the gap wide enough to land in on every run.

Maya's request is sent first and Omar's ``--stagger`` seconds later (0.5 s, as in the course): both
reach the gap, and they leave it in a known order, so the output is the same on every run. A warm-up
GET /stats is sent first, so the very first request does not pay for start-up work and lose its
head start.

The number of confirmed reservations is counted from the answers: every 201 is a committed
Confirmed reservation (the API answers 201 only after the unit of work has committed). The table
itself is the stronger evidence - the P09 evidence scripts also count the rows in the database.

Exit status: 0 when no round double-booked, 1 when at least one did, 2 when an answer was neither
201 nor 409 (for example 500, or no answer within 30 s) - so a script can tell the three apart.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import Counter
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

MAYA = {"guestName": "Maya", "guestEmail": "maya@example.com", "room": "R7",
        "checkIn": "2026-11-12", "checkOut": "2026-11-14"}
OMAR = {**MAYA, "guestName": "Omar", "guestEmail": "omar@example.com"}
REASONS = {201: "201 Created", 204: "204 No Content", 400: "400 Bad Request", 404: "404 Not Found",
           409: "409 Conflict", 500: "500 Internal Server Error"}
TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class Answer:
    """One booking's answer: status code, body text, and the id when it was created."""

    status: int
    body: str

    @property
    def reservation_id(self) -> str | None:
        if self.status != 201:
            return None
        created = json.loads(self.body)
        return str(created["id"]) if isinstance(created, dict) and "id" in created else None

    def line(self) -> str:
        """``201 Created   {...}`` / ``409 Conflict  {...}`` - the course's two columns."""
        reason = REASONS.get(self.status, str(self.status))
        return f"{reason}{' ' * max(2, 14 - len(reason))}{self.body}"


@dataclass(frozen=True)
class Round:
    maya: Answer
    omar: Answer

    @property
    def accepted(self) -> int:
        return sum(1 for answer in (self.maya, self.omar) if answer.status == 201)

    @property
    def verdict(self) -> str:
        statuses = sorted((self.maya.status, self.omar.status))
        if statuses == [201, 201]:
            return "double-booked"
        if statuses == [201, 409]:
            return "correct"
        return "unexpected"


@dataclass(frozen=True)
class Summary:
    rounds: int
    double_booked: int
    correct: int
    unexpected: int
    maya_base: str
    omar_base: str
    stagger_seconds: float


def send(method: str, url: str, body: dict[str, str] | None = None) -> Answer:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, method=method, data=data,
                                     headers={} if body is None else {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return Answer(response.status, response.read().decode())
    except urllib.error.HTTPError as error:
        return Answer(error.code, error.read().decode())
    except OSError as error:  # refused, reset, timed out: no HTTP answer at all - reported, never hidden
        return Answer(0, f"no answer: {error}")


def race_once(maya_base: str, omar_base: str, stagger_seconds: float) -> Round:
    """Maya's booking now, Omar's ``stagger_seconds`` later, both in flight together."""
    answers: dict[str, Answer] = {}
    maya = threading.Thread(target=lambda: answers.update(Maya=send("POST", f"{maya_base}/reservations", MAYA)))
    omar = threading.Thread(target=lambda: answers.update(Omar=send("POST", f"{omar_base}/reservations", OMAR)))
    maya.start()
    if stagger_seconds:
        time.sleep(stagger_seconds)  # Omar clicks a moment after Maya
    omar.start()
    maya.join()
    omar.join()
    return Round(answers["Maya"], answers["Omar"])


def cancel_accepted(base: str, result: Round) -> None:
    """Give R7 back (Cancelled rows block nothing), so the next round starts from a free room."""
    for answer in (result.maya, result.omar):
        if answer.reservation_id is not None:
            cancelled = send("DELETE", f"{base}/reservations/{answer.reservation_id}")
            if cancelled.status != 204:
                raise SystemExit(f"Could not cancel {answer.reservation_id}: {cancelled.line()}")


def print_round(result: Round, maya_base: str, omar_base: str) -> None:
    print("Two bookings for R7, 2026-11-12 to 2026-11-14, sent at the same moment.")
    if omar_base != maya_base:
        print(f"Maya -> {maya_base}   Omar -> {omar_base}")
    print()
    print(f"Maya -> {result.maya.line()}")
    print(f"Omar -> {result.omar.line()}")
    print()
    print(f"Confirmed reservations for R7 on 12-14 Nov: {result.accepted}")
    if result.verdict == "double-booked":
        print("DOUBLE BOOKED: the room has two confirmed reservations for the same nights.")
    elif result.verdict == "correct":
        print("CORRECT: one booking was accepted and one was refused.")
    else:
        print("UNEXPECTED: an answer was neither 201 Created nor 409 Conflict.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Two bookings for R7 at the same moment (P09 Step 1).")
    parser.add_argument("omar_base", nargs="?", help="where Omar's booking goes (default: Maya's address)")
    parser.add_argument("--maya", dest="maya_base", default="http://localhost:5080", help="where Maya's booking goes")
    parser.add_argument("--stagger", type=float, default=0.5, help="seconds between Maya's and Omar's request (0.5)")
    parser.add_argument("--repeat", type=int, default=1, help="rounds to run; accepted bookings are cancelled between rounds")
    parser.add_argument("--json", action="store_true", help="print only the summary, as JSON")
    args = parser.parse_args(argv)
    maya_base: str = args.maya_base.rstrip("/")
    omar_base: str = (args.omar_base or maya_base).rstrip("/")

    send("GET", f"{maya_base}/stats")  # the warm-up: see the module docstring
    if omar_base != maya_base:
        send("GET", f"{omar_base}/stats")

    rounds: list[Round] = []
    for number in range(1, args.repeat + 1):
        result = race_once(maya_base, omar_base, args.stagger)
        rounds.append(result)
        if args.repeat == 1 and not args.json:
            print_round(result, maya_base, omar_base)
        elif not args.json:
            print(f"Round {number:3}: Maya {result.maya.status} {result.maya.reservation_id or '-':5} "
                  f"Omar {result.omar.status} {result.omar.reservation_id or '-':5} -> {result.verdict}")
        if args.repeat > 1:
            cancel_accepted(maya_base, result)

    summary = Summary(len(rounds), sum(r.verdict == "double-booked" for r in rounds),
                      sum(r.verdict == "correct" for r in rounds), sum(r.verdict == "unexpected" for r in rounds),
                      maya_base, omar_base, args.stagger)
    if args.json:
        print(json.dumps(asdict(summary)))
    elif args.repeat > 1:
        odd = Counter(answer.status for r in rounds if r.verdict == "unexpected" for answer in (r.maya, r.omar)
                      if answer.status not in (201, 409))
        which = f" ({', '.join(f'{count} x {REASONS.get(status, status)}' for status, count in sorted(odd.items()))})" if odd else ""
        print(f"\nDouble bookings: {summary.double_booked} of {summary.rounds} rounds; one 201 and one 409: "
              f"{summary.correct}; anything else: {summary.unexpected}{which}.")
    if summary.unexpected:
        return 2
    return 1 if summary.double_booked else 0


if __name__ == "__main__":
    sys.exit(main())
