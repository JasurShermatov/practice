"""The program output (P03 Step 7 proof lines) and the race demo (P03 Step 8).

P04 change (deliberate, arrange part only): ``run_demo`` and ``run_race`` no
longer build their own store and sender - ``main.build_app`` (the composition
root) does - so the tests build the app first. Every expected output is unchanged.

P06 change (deliberate, arrange part only): ``run_demo`` takes a function that
reads the sender's counter instead of the internal sender class, so
``demo.py`` names no internal code. Expected outputs unchanged.

P07 change (deliberate, as the P07 activity sheet says): ``python main.py``
without a flag now starts the web app, so the demo is ``--demo``. The test
"main without flags runs the demo" became "main --demo runs the demo"; that
no flag starts the server is checked in ``test_api_sqlite.py``. The race keeps
its lists and its output (still double-booked; P09).

P09 change (deliberate - the fix): the two race pins asserted the defect and
now assert the correct behaviour. ``test_main_race_flag_still_double_books``
-> ``test_main_race_flag_gives_r7_to_one_guest`` and
``test_race_double_books_r7_known_defect`` ->
``test_race_gives_r7_to_exactly_one_guest_regression``: same race, same
timing, now "Omar: Unavailable", one Confirmed reservation, "Only one guest
has R7." (the list store checks under its lock). The control case is unchanged.
New: the race repeated 20 times never double-books, and a lock-free store
(the version-5 save) still does - so the test can tell the two apart.
"""
from __future__ import annotations

import pytest

from hotel_booking.demo import HOTEL_ROOMS, run_demo, run_race
from hotel_booking.notifications.internal import EmailNotificationSender
from hotel_booking.reservations import BookingService, Reservation
from hotel_booking.reservations.internal import InMemoryReservationStore
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


def test_main_demo_flag_runs_the_demo(capsys: pytest.CaptureFixture[str]) -> None:
    main(["--demo"])
    assert capsys.readouterr().out == EXPECTED_DEMO


def test_main_race_flag_gives_r7_to_one_guest(capsys: pytest.CaptureFixture[str]) -> None:
    """P04 Step 6 wiring (0.5 s slow step); since P09 the activity sheet's Step 3 output."""
    main(["--race"])
    assert capsys.readouterr().out.splitlines() == [
        "Maya and Omar both book R7 for 12-14 Nov at the same moment...",
        "Maya: Accepted R101",
        "Omar: Unavailable",
        "Confirmed reservations for R7 on 12-14 Nov: 1",
        "Only one guest has R7.",
    ]


def test_race_gives_r7_to_exactly_one_guest_regression(capsys: pytest.CaptureFixture[str]) -> None:
    """REGRESSION (R3 under concurrency; a known defect from P03 to P08, fixed in P09).

    Both requests still pass the pre-check before either saves - the race still happens - but the
    list store's ``save`` checks again under its lock and refuses Omar's reservation.
    """
    service, store, _ = build_app(slow_step_seconds=0.3)
    confirmed = run_race(service, store, stagger_seconds=0.05)
    out = capsys.readouterr().out
    assert confirmed == 1
    assert out.splitlines() == [
        "Maya and Omar both book R7 for 12-14 Nov at the same moment...",
        "Maya: Accepted R101",
        "Omar: Unavailable",
        "Confirmed reservations for R7 on 12-14 Nov: 1",
        "Only one guest has R7.",
    ]


class LockFreeStore(InMemoryReservationStore):
    """The version-5 ``save`` (append, no check): proves the race test can still see a double booking."""

    def save(self, reservation: Reservation) -> None:
        self._rows.append(reservation)


@pytest.mark.parametrize(("store_class", "expected"), [(InMemoryReservationStore, 1), (LockFreeStore, 2)])
def test_twenty_races_never_double_book_and_the_test_would_notice(
    capsys: pytest.CaptureFixture[str], store_class: type[InMemoryReservationStore], expected: int,
) -> None:
    for _ in range(20):
        store = store_class()
        service = BookingService(HOTEL_ROOMS, store, EmailNotificationSender(), slow_step_seconds=0.02)
        assert run_race(service, store, stagger_seconds=0.005) == expected
    capsys.readouterr()


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
