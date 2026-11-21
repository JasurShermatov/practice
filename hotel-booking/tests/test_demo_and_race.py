"""The program output (Step 7 proof lines) and the race demo (Step 8)."""
from __future__ import annotations

import pytest

from hotel_booking.demo import run_demo, run_race
from main import main

EXPECTED_DEMO = """\
Free rooms 12-14 Nov: R7, R8
Maya books R7 12-14 Nov: Accepted R101
Omar books R7 13-15 Nov: Unavailable
Nora books R7 14-16 Nov: Accepted R102
Omar books R8 15-15 Nov: InvalidDates
Free rooms 12-14 Nov: R8
Maya cancels R101: True
Free rooms 12-14 Nov: R7, R8
Confirmation emails sent: 2
"""


def test_demo_prints_the_nine_expected_lines(capsys: pytest.CaptureFixture[str]) -> None:
    run_demo()
    assert capsys.readouterr().out == EXPECTED_DEMO


def test_main_without_flags_runs_the_demo(capsys: pytest.CaptureFixture[str]) -> None:
    main([])
    assert capsys.readouterr().out == EXPECTED_DEMO


def test_race_double_books_r7_known_defect(capsys: pytest.CaptureFixture[str]) -> None:
    """KNOWN DEFECT, kept on purpose until P09.

    Two requests that both check before either saves are both accepted, so R7
    has two Confirmed reservations for the same nights and R3 is broken.
    This characterisation test pins today's behaviour; P09 must flip it to
    ``confirmed == 1``.
    """
    confirmed = run_race(slow_step_seconds=0.3, stagger_seconds=0.05)
    out = capsys.readouterr().out
    assert confirmed == 2
    assert out.splitlines() == [
        "Maya and Omar both book R7 for 12-14 Nov at the same moment...",
        "Maya: Accepted R101",
        "Omar: Accepted R102",
        "Confirmed reservations for R7 on 12-14 Nov: 2",
        "Double booking! Both requests checked before either one saved.",
    ]


def test_without_overlap_in_time_the_second_request_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Control case: if Omar starts after Maya has saved, the check works."""
    confirmed = run_race(slow_step_seconds=0.05, stagger_seconds=0.2)
    out = capsys.readouterr().out
    assert confirmed == 1
    assert "Omar: Unavailable" in out
    assert out.rstrip().endswith("Only one guest has R7.")
