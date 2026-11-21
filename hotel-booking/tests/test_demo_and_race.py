"""The program output (P03 Step 7 proof lines) and the race demo (P03 Step 8).

P04 change (deliberate, arrange part only): ``run_demo`` and ``run_race`` no
longer build their own store and sender - ``main.build_app`` (the composition
root) does - so the tests build the app first. Every expected output is unchanged.

P06 change (deliberate, arrange part only): ``run_demo`` takes a function that
reads the sender's counter instead of the internal sender class, so
``demo.py`` names no internal code. Expected outputs unchanged.
"""
from __future__ import annotations

import pytest

from hotel_booking.demo import run_demo, run_race
from main import build_app, main

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
    service, _, email = build_app()
    run_demo(service, lambda: email.sent)
    assert capsys.readouterr().out == EXPECTED_DEMO


def test_main_without_flags_runs_the_demo(capsys: pytest.CaptureFixture[str]) -> None:
    main([])
    assert capsys.readouterr().out == EXPECTED_DEMO


def test_main_race_flag_still_double_books(capsys: pytest.CaptureFixture[str]) -> None:
    """P04 Step 6: the composition root wires the race exactly as P03 did (0.5 s slow step)."""
    main(["--race"])
    assert capsys.readouterr().out.splitlines()[-2:] == [
        "Confirmed reservations for R7 on 12-14 Nov: 2",
        "Double booking! Both requests checked before either one saved.",
    ]


def test_race_double_books_r7_known_defect(capsys: pytest.CaptureFixture[str]) -> None:
    """KNOWN DEFECT, kept on purpose until P09.

    Two requests that both check before either saves are both accepted, so R7
    has two Confirmed reservations for the same nights and R3 is broken.
    This characterisation test pins today's behaviour; P09 must flip it to
    ``confirmed == 1``.
    """
    service, store, _ = build_app(slow_step_seconds=0.3)
    confirmed = run_race(service, store, stagger_seconds=0.05)
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
    service, store, _ = build_app(slow_step_seconds=0.05)
    confirmed = run_race(service, store, stagger_seconds=0.2)
    out = capsys.readouterr().out
    assert confirmed == 1
    assert "Omar: Unavailable" in out
    assert out.rstrip().endswith("Only one guest has R7.")
