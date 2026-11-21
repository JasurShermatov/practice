"""P10: the notification queue through the real wiring - main.build_api over a SQLite file.

What the unit tests of the queue cannot see:

- the booking answers at once with a one-second mail server, and the email follows the answer;
- the booking result does not depend on the email: 201 and a saved row when the queue is full
  (``notificationFailed: true``) and when the sender fails later (counted ``failed``);
- the email is handed over only after the COMMIT: the worker always finds the row committed, and a
  booking that rolls back is never emailed and gives its place back;
- P09 still holds with the queue in front: two simultaneous bookings for one room - one 201, one 409,
  one Confirmed row and exactly one email;
- GET /stats publishes the queue's counters only when the app has a queue;
- the shutdown hook: the drain runs when the server stops (lifespan), and ``shut_down_notifications``
  prints the course's Step 6 lines, with and without the drain;
- the settings reach the server from HOTEL_* variables and flags; a real ``python main.py`` process
  drains its queue on Ctrl+C (SIGINT) *and* on SIGTERM, which uvicorn re-raises after its shutdown.
"""
from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Iterator
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

import main
from hotel_booking.notifications import Confirmation, DeliveryStatus
from hotel_booking.notifications.internal import EmailNotificationSender, QueuedNotificationSender

from .conftest import free_port

PROJECT = Path(__file__).resolve().parents[1]


def booking(number: int, room: str = "R7") -> dict[str, str]:
    """Booking ``number``: one night in December, a different night each (all legal)."""
    return {"guestName": f"Guest{number}", "guestEmail": f"guest{number}@example.com", "room": room,
            "checkIn": f"2026-12-{number:02d}", "checkOut": f"2026-12-{number + 1:02d}"}


def nights(number: int) -> tuple[date, date]:
    first = date(2026, 12, 1) + timedelta(days=number)
    return first, first + timedelta(days=1)


def confirmed_rows(database: Path) -> int:
    with closing(sqlite3.connect(database)) as connection:
        return int(connection.execute("SELECT count(*) FROM reservations WHERE status = 'Confirmed'").fetchone()[0])


@pytest.fixture
def made() -> Iterator[list[QueuedNotificationSender]]:
    queues: list[QueuedNotificationSender] = []
    yield queues
    for queue in queues:
        queue.close(drain=False)


def app_with_queue(database: Path, queue: QueuedNotificationSender, made: list[QueuedNotificationSender],
                   slow_step_seconds: float = 0.0) -> TestClient:
    made.append(queue)
    app, _ = main.build_api(main.sqlite_connector(database), slow_step_seconds, notifications=queue)
    return TestClient(app, raise_server_exceptions=False)


# --------------------------------------------------------------------------- the booking does not wait


def test_a_booking_answers_at_once_with_a_one_second_mail_server(tmp_path: Path,
                                                                 made: list[QueuedNotificationSender]) -> None:
    email = EmailNotificationSender(send_seconds=1)
    queue = QueuedNotificationSender(email, capacity=10, workers=1)
    client = app_with_queue(tmp_path / "h.sqlite3", queue, made)
    client.get("/stats")  # warm-up
    started = time.perf_counter()
    response = client.post("/reservations", json=booking(1))
    took = time.perf_counter() - started
    assert response.status_code == 201 and response.json()["notificationFailed"] is False
    assert took < 0.3, f"the booking waited {took:.2f} s"
    assert email.sent == 0  # the answer came before the email
    queue.close(drain=True, timeout=5)
    assert email.sent == 1


def test_without_the_queue_the_booking_waits_for_the_email(tmp_path: Path) -> None:
    """The "before" of Step 1 (``--no-queue``): the same sender inside the request costs its full time."""
    app, _ = main.build_api(main.sqlite_connector(tmp_path / "h.sqlite3"),
                            sender=EmailNotificationSender(send_seconds=0.5))
    client = TestClient(app)
    started = time.perf_counter()
    assert client.post("/reservations", json=booking(1)).status_code == 201
    assert time.perf_counter() - started >= 0.5


# --------------------------------------------------------------------------- the booking result is independent


def test_a_full_queue_never_fails_a_booking(tmp_path: Path, made: list[QueuedNotificationSender]) -> None:
    """Thirty bookings into a queue of ten with a one-second sender: 30 x 201, 30 rows, and the
    refused emails are visible twice - in the answers and in the counters."""
    database = tmp_path / "h.sqlite3"
    queue = QueuedNotificationSender(EmailNotificationSender(send_seconds=1), capacity=10, workers=1)
    client = app_with_queue(database, queue, made)
    answers = [client.post("/reservations", json=booking(1 + number // 2, "R7" if number % 2 == 0 else "R8"))
               for number in range(30)]
    assert [answer.status_code for answer in answers] == [201] * 30
    assert confirmed_rows(database) == 30
    refused = sum(answer.json()["notificationFailed"] for answer in answers)
    stats = client.get("/stats").json()
    assert stats["notificationsRejected"] == refused > 0
    assert stats["notificationsAccepted"] + stats["notificationsRejected"] == 30
    assert stats["notificationsQueued"] <= 10


def test_a_failing_mail_server_never_fails_a_booking(tmp_path: Path, made: list[QueuedNotificationSender]) -> None:
    database = tmp_path / "h.sqlite3"
    queue = QueuedNotificationSender(EmailNotificationSender(fail_every=1), capacity=10, workers=1)
    client = app_with_queue(database, queue, made)
    response = client.post("/reservations", json=booking(1))
    assert response.status_code == 201 and response.json()["notificationFailed"] is False
    queue.close(drain=True, timeout=5)
    assert confirmed_rows(database) == 1
    assert queue.status_of("R101") is DeliveryStatus.FAILED
    assert queue.counts().failed == 1


def test_refused_and_invalid_bookings_never_reach_the_queue(tmp_path: Path,
                                                            made: list[QueuedNotificationSender]) -> None:
    queue = QueuedNotificationSender(EmailNotificationSender(), capacity=10, workers=1)
    client = app_with_queue(tmp_path / "h.sqlite3", queue, made)
    assert client.post("/reservations", json=booking(1)).status_code == 201
    assert client.post("/reservations", json=booking(1)).status_code == 409             # same night
    assert client.post("/reservations", json={**booking(2), "checkOut": "2026-12-02"}).status_code == 400
    assert client.delete("/reservations/R101").status_code == 204
    queue.close(drain=True, timeout=5)
    assert queue.counts().accepted == 1 and queue.counts().rejected == 0


# --------------------------------------------------------------------------- only after the commit


def test_the_worker_only_ever_sees_committed_bookings(tmp_path: Path, made: list[QueuedNotificationSender]) -> None:
    database = tmp_path / "h.sqlite3"
    seen: dict[str, bool] = {}

    class Inspector:
        """Opens its own connection at send time: is the reservation committed yet?"""

        def send_confirmation(self, confirmation: Confirmation) -> None:
            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute("SELECT status FROM reservations WHERE id = ?",
                                         (confirmation.reservation_id,)).fetchone()
            seen[confirmation.reservation_id] = row == ("Confirmed",)

    queue = QueuedNotificationSender(Inspector(), capacity=50, workers=4)
    client = app_with_queue(database, queue, made, slow_step_seconds=0.0)
    for number in range(1, 21):
        assert client.post("/reservations", json=booking(number)).status_code == 201
    queue.close(drain=True, timeout=10)
    assert len(seen) == 20 and all(seen.values())


def test_a_booking_that_rolls_back_is_never_emailed(tmp_path: Path, made: list[QueuedNotificationSender]) -> None:
    """The commit fails after the reservation was saved and the confirmation held: 500, no row, no
    email, and the place is free again for the next guest (capacity 1)."""
    database = tmp_path / "h.sqlite3"
    main.sqlite_connector(database)  # creates the schema
    failures = {"left": 1}

    class FailingCommit(sqlite3.Connection):
        """A real SQLite connection whose first COMMIT fails, as a full disk would make it."""

        def commit(self) -> None:
            if failures["left"]:
                failures["left"] -= 1
                raise sqlite3.OperationalError("disk I/O error (simulated)")
            super().commit()

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database, timeout=5.0, factory=FailingCommit)

    sent: list[str] = []

    class Recorder:
        def send_confirmation(self, confirmation: Confirmation) -> None:
            sent.append(confirmation.reservation_id)

    queue = QueuedNotificationSender(Recorder(), capacity=1, workers=1)
    made.append(queue)
    app, _ = main.build_api(connect, notifications=queue)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.post("/reservations", json=booking(1)).status_code == 500
    assert confirmed_rows(database) == 0
    second = client.post("/reservations", json=booking(1))
    assert second.status_code == 201 and second.json()["notificationFailed"] is False
    queue.close(drain=True, timeout=5)
    assert sent == [second.json()["id"]]
    assert queue.counts().accepted == 1 and queue.counts().rejected == 0


# --------------------------------------------------------------------------- P09 still holds


def test_the_race_still_gives_the_room_to_one_guest_and_one_email(tmp_path: Path,
                                                                  made: list[QueuedNotificationSender]) -> None:
    database = tmp_path / "h.sqlite3"
    sent: list[str] = []

    class Recorder:
        def send_confirmation(self, confirmation: Confirmation) -> None:
            sent.append(confirmation.reservation_id)

    queue = QueuedNotificationSender(Recorder(), capacity=10, workers=2)
    client = app_with_queue(database, queue, made, slow_step_seconds=0.3)
    maya = booking(12)
    omar = {**maya, "guestName": "Omar", "guestEmail": "omar@example.com"}
    answers: list[Any] = []
    threads = [threading.Thread(target=lambda body=body: answers.append(client.post("/reservations", json=body)))
               for body in (maya, omar)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    queue.close(drain=True, timeout=5)
    assert sorted(answer.status_code for answer in answers) == [201, 409]
    assert confirmed_rows(database) == 1
    winner = next(answer.json()["id"] for answer in answers if answer.status_code == 201)
    assert sent == [winner]  # the loser's reservation was refused before any email was held


# --------------------------------------------------------------------------- GET /stats


def test_stats_show_the_queue_only_when_there_is_one(tmp_path: Path, made: list[QueuedNotificationSender]) -> None:
    without, _ = main.build_api(main.sqlite_connector(tmp_path / "a.sqlite3"))
    assert "notificationsAccepted" not in TestClient(without).get("/stats").json()
    queue = QueuedNotificationSender(EmailNotificationSender(), capacity=3, workers=1)
    stats = app_with_queue(tmp_path / "b.sqlite3", queue, made).get("/stats").json()
    assert {key: value for key, value in stats.items() if key.startswith("notifications")} == {
        "notificationsAccepted": 0, "notificationsRejected": 0, "notificationsCompleted": 0,
        "notificationsQueued": 0, "notificationsFailed": 0}


# --------------------------------------------------------------------------- shutdown


def test_stopping_the_server_runs_the_drain(tmp_path: Path) -> None:
    """The lifespan hook: leaving the TestClient block is the server shutting down."""
    lines: list[str] = []
    email = EmailNotificationSender(send_seconds=0.05)
    queue = QueuedNotificationSender(email, capacity=10, workers=1)
    app, _ = main.build_api(main.sqlite_connector(tmp_path / "h.sqlite3"), notifications=queue,
                            on_shutdown=lambda: main.shut_down_notifications(queue, say=lines.append))
    with TestClient(app) as client:
        for number in range(1, 6):
            client.post("/reservations", json=booking(number))
    assert email.sent == 5
    assert lines[0].startswith("Stopping the app with 5 confirmations accepted and ")
    assert lines[1].startswith("Draining the notification queue: ") and lines[1].endswith("(at most 30 s)")
    assert lines[-2] == ("accepted=5  rejected=0  completed=5  failed=0  dropped=0  queued=0  in_flight=0")
    assert lines[-1] == "Nobody was owed an email."


def test_shutdown_without_the_drain_names_who_is_owed(made: list[QueuedNotificationSender]) -> None:
    gate = threading.Event()

    class Held:
        def send_confirmation(self, confirmation: Confirmation) -> None:
            gate.wait(5)

    queue = QueuedNotificationSender(Held(), capacity=10, workers=1)
    made.append(queue)
    for number in range(10):
        queue.send_confirmation(Confirmation(f"R{101 + number}", "g@example.com", "R7",
                                             *nights(number)))
    lines: list[str] = []
    threading.Timer(0.2, gate.set).start()
    main.shut_down_notifications(queue, drain=False, say=lines.append)
    assert lines[0] == "Stopping the app with 10 confirmations accepted and 0 sent so far..."
    assert lines[1] == "(no drain) 10 confirmations are queued or being sent"
    assert lines[-1].startswith("9 guests are owed an email that will not be sent: R102, R103")


# --------------------------------------------------------------------------- settings and the real process


def test_the_queue_settings_come_from_the_environment_and_the_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {"HOTEL_EMAIL_SECONDS": "1", "HOTEL_QUEUE_CAPACITY": "10000", "HOTEL_WORKERS": "3",
                        "HOTEL_SEND_ATTEMPTS": "2", "HOTEL_DRAIN_SECONDS": "5", "HOTEL_EMAIL_TIMEOUT": "3",
                        "HOTEL_EMAIL_FAIL_EVERY": "4"}.items():
        monkeypatch.setenv(name, value)
    started: list[main.ServerOptions] = []
    main.main([], serve=started.append)
    main.main(["--no-queue", "--no-drain", "--workers", "2", "--queue-capacity", "5"], serve=started.append)
    assert started[0].notifications == main.NotificationOptions(
        queue=True, email_seconds=1.0, email_timeout=3.0, email_fail_every=4, capacity=10000, workers=3,
        send_attempts=2, drain=True, drain_seconds=5.0)
    assert started[1].notifications == main.NotificationOptions(
        queue=False, email_seconds=1.0, email_timeout=3.0, email_fail_every=4, capacity=5, workers=2,
        send_attempts=2, drain=False, drain_seconds=5.0)


def test_build_notifications_makes_the_queue_the_options_describe() -> None:
    queue = main.build_notifications(main.NotificationOptions(email_seconds=0.0, capacity=3, workers=2,
                                                              send_attempts=2))
    try:
        assert len(queue._workers) == 2  # noqa: SLF001
        assert [queue.offer(Confirmation(f"R{n}", "g@example.com", "R7", *nights(n)))
                for n in range(3)].count(True) >= 3
    finally:
        queue.close(drain=True, timeout=5)


@pytest.mark.parametrize("stop", [signal.SIGINT, signal.SIGTERM], ids=["ctrl-c", "sigterm"])
def test_the_real_server_drains_its_queue_when_it_is_stopped(tmp_path: Path, stop: signal.Signals) -> None:
    """``python main.py`` as a process: 6 bookings with a 0.2 s mail server, then the stop signal.
    The output must show the drain and nobody owed - for SIGTERM too, which uvicorn re-raises."""
    port = free_port()
    environment = {**os.environ, "HOTEL_DB_PATH": str(tmp_path / "h.sqlite3"), "HOTEL_EMAIL_SECONDS": "0.2",
                   "PYTHONUNBUFFERED": "1"}
    server = subprocess.Popen([sys.executable, "main.py", "--cache", "memory", "--port", str(port)], cwd=PROJECT,
                              env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        base = f"http://localhost:{port}"
        deadline = time.monotonic() + 15
        while True:
            try:
                urllib.request.urlopen(f"{base}/stats", timeout=1).read()
                break
            except OSError:
                assert time.monotonic() < deadline, "the server did not start"
                time.sleep(0.1)
        for number in range(1, 7):
            request = urllib.request.Request(f"{base}/reservations", method="POST",
                                             data=json.dumps(booking(number)).encode(),
                                             headers={"Content-Type": "application/json"})
            assert urllib.request.urlopen(request, timeout=5).status == 201
        server.send_signal(stop)
        output, _ = server.communicate(timeout=30)
    finally:
        if server.poll() is None:
            server.kill()
            server.communicate()
    assert "Stopping the app with 6 confirmations accepted and" in output
    assert "Draining the notification queue:" in output
    assert "accepted=6  rejected=0  completed=6  failed=0  dropped=0  queued=0  in_flight=0" in output
    assert "Nobody was owed an email." in output
