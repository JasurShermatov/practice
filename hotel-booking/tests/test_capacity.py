"""The capacity estimate (P07 Step 1): the arithmetic, and the document that shows it.

- The numbers of the course's worked example (L04 / P07 activity sheet) come out of capacity.py.
- Every row of the two results tables in docs/capacity.md is exactly what capacity.py computes,
  so the document cannot keep a stale number after an assumption changes.
- The assumptions table states the same values as the constants.
- The peak agrees with the first answer in docs/l04-notes.md (activity sheet Step 1, item 5).
"""
from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path

import pytest

import capacity

DOCS = Path(__file__).resolve().parents[1] / "docs"
CAPACITY_MD = (DOCS / "capacity.md").read_text(encoding="utf-8")


def test_the_course_numbers() -> None:
    e = capacity.estimate()
    assert e.searches_per_day == 28_800
    assert e.average == pytest.approx(1 / 3)
    assert e.peak == pytest.approx(10 / 3)
    assert e.peak_per_minute == 200  # S1: 200 searches within one minute
    assert e.queries_at_peak == pytest.approx(400 / 3)
    assert e.storage_mb_per_year == pytest.approx(4.38)
    assert e.search_kb_per_s == pytest.approx(20 / 3)
    assert e.visitors_at_peak == pytest.approx(1 / 6)
    assert e.photos_kb_per_s == pytest.approx(1000 / 3)
    assert e.searches_per_booking == 1440


def test_the_arithmetic_with_exact_fractions() -> None:
    """The "Checked by hand" section: no floating point at all."""
    peak = Fraction(capacity.VISITORS_PER_DAY * capacity.SEARCHES_PER_VISITOR, capacity.SECONDS_PER_DAY) * capacity.PEAK_FACTOR
    assert peak == Fraction(10, 3) and peak * 60 == 200
    assert peak * capacity.ROOMS == Fraction(400, 3)
    assert Fraction(capacity.BOOKINGS_PER_DAY, capacity.SECONDS_PER_DAY) * capacity.PEAK_FACTOR == Fraction(1, 432)
    assert capacity.BOOKINGS_PER_DAY * 365 * capacity.ROW_BYTES == 4_380_000


def test_the_course_six_lines() -> None:
    assert capacity.lines(capacity.estimate())[:6] == [
        "Searches per day: 1440 visitors x 20 = 28800",
        "Searches per second: average 0.33, peak 3.33 (200 per minute)",
        "Bookings: 20 per day, 0.0023 per second at peak, 1440 searches per booking",
        "Database queries at peak: 3.33 searches/s x 40 rooms = 133.33 per second",
        "Reservation storage: 20 x 365 x 600 bytes = 4.38 MB per year",
        "Bandwidth at peak: search answers 6.67 KB/s, room photos 333.33 KB/s",
    ]


@pytest.mark.parametrize("row", capacity.markdown(capacity.results(capacity.estimate()))
                         + capacity.markdown(capacity.extra_results(capacity.estimate())))
def test_every_result_row_in_the_document_is_computed(row: str) -> None:
    assert row in CAPACITY_MD.splitlines()


def test_the_document_has_exactly_the_computed_result_rows() -> None:
    section = CAPACITY_MD[CAPACITY_MD.index("## Results"):CAPACITY_MD.index("## Checked by hand")]
    rows = [line for line in section.splitlines() if line.startswith("| ") and not line.startswith(("| Number", "|---"))]
    expected = capacity.markdown(capacity.results(capacity.estimate())) + capacity.markdown(capacity.extra_results(capacity.estimate()))
    assert rows == expected


@pytest.mark.parametrize(("label", "value"), [
    ("Visitors per day", f"{capacity.VISITORS_PER_DAY:,}"),
    ("Searches per visitor", str(capacity.SEARCHES_PER_VISITOR)),
    ("Bookings per day", str(capacity.BOOKINGS_PER_DAY)),
    ("Peak factor", str(capacity.PEAK_FACTOR)),
    ("Queries per search", str(capacity.ROOMS)),
    ("Bytes per reservation", str(capacity.ROW_BYTES)),
    ("Search answer", f"{capacity.ANSWER_KB} KB"),
    ("Room photos per visit", f"{capacity.PHOTOS_KB // 1000} MB"),
    ("Statements per booking", str(capacity.STATEMENTS_PER_BOOKING)),
    ("Retention", f"{capacity.YEARS} years"),
    ("Growth factor", str(capacity.GROWTH)),
])
def test_the_assumptions_table_states_the_constants(label: str, value: str) -> None:
    assert re.search(rf"^\| {re.escape(label)} \| {re.escape(value)} \|", CAPACITY_MD, re.MULTILINE), label


def test_the_document_keeps_the_course_frame() -> None:
    assert CAPACITY_MD.startswith("# Capacity estimate: hotel booking app\n\nThese are estimates from assumptions, "
                                  "not measurements. P08 measures the real app.")
    to_measure = CAPACITY_MD[CAPACITY_MD.index("## To measure later"):]
    assert "p95 of 1,000 searches for 12–14 Nov, target ≤ 1 s (S1): P08." in to_measure
    assert "Database queries per search (GET /stats): P08." in to_measure


def test_the_peak_agrees_with_the_l04_notes() -> None:
    first_answer = next(line for line in (DOCS / "l04-notes.md").read_text(encoding="utf-8").splitlines()
                        if line.startswith("1. "))
    e = capacity.estimate()
    assert f"{e.peak:.2f} searches per second ({e.peak_per_minute} a minute)" in first_answer


def test_capacity_script_prints_the_lines_and_the_table(capsys: pytest.CaptureFixture[str]) -> None:
    capacity.main([])
    assert capsys.readouterr().out.splitlines() == capacity.lines(capacity.estimate())
    capacity.main(["--table"])
    assert "| Searches, peak | 0.33 × 10 | 3.33 per second = 200 a minute (S1) |" in capsys.readouterr().out
