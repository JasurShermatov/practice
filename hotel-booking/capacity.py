"""The capacity estimate of the hotel booking app (L04 T10, P07 Step 1), as a program.

    python capacity.py            -> the estimate, line by line (the course's six lines + checks)
    python capacity.py --table    -> the "Results" rows of docs/capacity.md, in Markdown

Arithmetic on written-down assumptions, not a measurement: P08 measures the running app. Every
number in docs/capacity.md comes from ``results()`` below, and tests/test_capacity.py fails when
the document and this file disagree, so a changed assumption cannot leave a stale number behind.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

# --- Assumptions: our guesses, written down so anyone can check them and change them. -------------
VISITORS_PER_DAY = 1440      # people who open the hotel's booking page (about one a minute)
SEARCHES_PER_VISITOR = 20    # each one tries several dates
BOOKINGS_PER_DAY = 20        # 40 rooms, most stays are two nights
PEAK_FACTOR = 10             # the busiest minutes (Friday evening, holiday sale) vs the average
ROOMS = 40                   # one availability query per room per search (BookingService.find_free_rooms)
ROW_BYTES = 600              # one reservation row plus its index entry
ANSWER_KB = 2                # one search answer as JSON
PHOTOS_KB = 2000             # ten room photos of 200 KB on the booking page
SECONDS_PER_DAY = 86_400

# --- Assumptions added in this portfolio (labelled as such in docs/capacity.md). ------------------
STATEMENTS_PER_BOOKING = 3   # reserve: EXISTS overlap + count(*) for the id + INSERT (SqlReservationStore)
S1_SECONDS = 1.0             # S1: p95 of a search <= 1 s (docs/quality-scenarios.md)
YEARS = 5                    # how long reservations are kept (history is never deleted)
GROWTH = 10                  # "what if" factor for visitors


@dataclass(frozen=True)
class Estimate:
    searches_per_day: int
    average: float                # searches per second
    peak: float                   # searches per second at the peak
    peak_per_minute: int
    bookings_at_peak: float       # per second
    searches_per_booking: int
    queries_at_peak: float        # database queries per second from searches
    storage_mb_per_year: float
    search_kb_per_s: float
    visitors_at_peak: float       # per second
    photos_kb_per_s: float
    # portfolio additions
    writes_at_peak: float         # SQL statements per second from bookings
    in_flight_at_s1: float        # Little's law: requests in the system if each took the full S1 second
    storage_mb_total: float
    queries_at_growth: float


def estimate() -> Estimate:
    searches_per_day = VISITORS_PER_DAY * SEARCHES_PER_VISITOR
    average = searches_per_day / SECONDS_PER_DAY
    peak = average * PEAK_FACTOR
    bookings_at_peak = BOOKINGS_PER_DAY / SECONDS_PER_DAY * PEAK_FACTOR
    visitors_at_peak = VISITORS_PER_DAY / SECONDS_PER_DAY * PEAK_FACTOR
    storage_mb = BOOKINGS_PER_DAY * 365 * ROW_BYTES / 1_000_000
    return Estimate(
        searches_per_day=searches_per_day,
        average=average,
        peak=peak,
        peak_per_minute=searches_per_day * PEAK_FACTOR // 1440,
        bookings_at_peak=bookings_at_peak,
        searches_per_booking=searches_per_day // BOOKINGS_PER_DAY,
        queries_at_peak=peak * ROOMS,
        storage_mb_per_year=storage_mb,
        search_kb_per_s=peak * ANSWER_KB,
        visitors_at_peak=visitors_at_peak,
        photos_kb_per_s=visitors_at_peak * PHOTOS_KB,
        writes_at_peak=bookings_at_peak * STATEMENTS_PER_BOOKING,
        in_flight_at_s1=peak * S1_SECONDS,
        storage_mb_total=storage_mb * YEARS,
        queries_at_growth=peak * GROWTH * ROOMS,
    )


def lines(e: Estimate) -> list[str]:
    """The course's six lines (L04 / P07 Step 1), then the portfolio's checks."""
    return [
        f"Searches per day: {VISITORS_PER_DAY} visitors x {SEARCHES_PER_VISITOR} = {e.searches_per_day}",
        f"Searches per second: average {e.average:.2f}, peak {e.peak:.2f} ({e.peak_per_minute} per minute)",
        f"Bookings: {BOOKINGS_PER_DAY} per day, {e.bookings_at_peak:.4f} per second at peak, "
        f"{e.searches_per_booking} searches per booking",
        f"Database queries at peak: {e.peak:.2f} searches/s x {ROOMS} rooms = {e.queries_at_peak:.2f} per second",
        f"Reservation storage: {BOOKINGS_PER_DAY} x 365 x {ROW_BYTES} bytes = {e.storage_mb_per_year:.2f} MB per year",
        f"Bandwidth at peak: search answers {e.search_kb_per_s:.2f} KB/s, room photos {e.photos_kb_per_s:.2f} KB/s",
        f"Database writes at peak: {e.bookings_at_peak:.4f} bookings/s x {STATEMENTS_PER_BOOKING} statements "
        f"= {e.writes_at_peak:.4f} per second",
        f"Searches in flight at peak if each took the whole S1 second: {e.peak:.2f}/s x {S1_SECONDS:.0f} s "
        f"= {e.in_flight_at_s1:.2f}",
        f"Storage after {YEARS} years: {e.storage_mb_per_year:.2f} MB x {YEARS} = {e.storage_mb_total:.2f} MB",
        f"Database queries at peak with {GROWTH}x visitors: {e.peak:.2f} x {GROWTH} x {ROOMS} = {e.queries_at_growth:.2f} per second",
    ]


def results(e: Estimate) -> list[tuple[str, str, str]]:
    """(number, calculation, result): the "Results" table of docs/capacity.md, row by row."""
    return [
        ("Searches, average", f"{VISITORS_PER_DAY:,} × {SEARCHES_PER_VISITOR} = {e.searches_per_day:,} a day; "
                              f"{e.searches_per_day:,} ÷ {SECONDS_PER_DAY:,} s", f"{e.average:.2f} per second"),
        ("Searches, peak", f"{e.average:.2f} × {PEAK_FACTOR}",
         f"{e.peak:.2f} per second = {e.peak_per_minute} a minute (S1)"),
        ("Database queries, peak", f"{e.peak:.2f} × {ROOMS} rooms", f"{e.queries_at_peak:.0f} per second"),
        ("Storage", f"{BOOKINGS_PER_DAY} bookings × 365 days × {ROW_BYTES} bytes", f"{e.storage_mb_per_year:.2f} MB a year"),
        ("Bandwidth, peak", f"{e.peak:.2f} × {ANSWER_KB} KB search answers; {e.visitors_at_peak:.2f} × {PHOTOS_KB // 1000} MB photos",
         f"search {e.search_kb_per_s:.2f} KB/s, photos {e.photos_kb_per_s:.0f} KB/s"),
    ]


def extra_results(e: Estimate) -> list[tuple[str, str, str]]:
    """Portfolio additions: the write side, concurrency, retention and growth."""
    return [
        ("Bookings, peak", f"{BOOKINGS_PER_DAY} ÷ {SECONDS_PER_DAY:,} s × {PEAK_FACTOR}",
         f"{e.bookings_at_peak:.4f} per second (one every {1 / e.bookings_at_peak:.0f} s)"),
        ("Reads per write", f"{e.searches_per_day:,} searches ÷ {BOOKINGS_PER_DAY} bookings",
         f"{e.searches_per_booking:,} searches per booking"),
        ("Database writes, peak", f"{e.bookings_at_peak:.4f} × {STATEMENTS_PER_BOOKING} statements",
         f"{e.writes_at_peak:.4f} per second"),
        ("Searches in flight, peak", f"{e.peak:.2f} per second × {S1_SECONDS:.0f} s (Little's law, worst S1 case)",
         f"{e.in_flight_at_s1:.2f} requests at once"),
        ("Storage, retention", f"{e.storage_mb_per_year:.2f} MB × {YEARS} years", f"{e.storage_mb_total:.2f} MB"),
        ("Database queries, growth", f"{e.peak:.2f} × {GROWTH} (visitors) × {ROOMS} rooms",
         f"{e.queries_at_growth:,.0f} per second"),
    ]


def markdown(rows: list[tuple[str, str, str]]) -> list[str]:
    return [f"| {name} | {calculation} | {result} |" for name, calculation, result in rows]


def main(argv: list[str]) -> None:
    e = estimate()
    if "--table" in argv:
        print("\n".join(markdown(results(e)) + [""] + markdown(extra_results(e))))
    else:
        print("\n".join(lines(e)))


if __name__ == "__main__":
    main(sys.argv[1:])
