"""P10: tools/burst.py against a real uvicorn server with the notification queue, plus its arithmetic.

The server runs in a background thread on a free port, over a SQLite file, wired by main.build_api
with a real ``QueuedNotificationSender`` (capacity 5, one worker, a 50 ms mail server), so a burst of
20 overflows the queue the way the course's burst of 30 overflows a queue of 10.
"""
from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

import main
from hotel_booking.notifications.internal import EmailNotificationSender, QueuedNotificationSender
from tools import burst

from .conftest import free_port


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    database = tmp_path_factory.mktemp("burst") / "hotel.sqlite3"
    queue = QueuedNotificationSender(EmailNotificationSender(send_seconds=0.05), capacity=5, workers=1)
    app, _ = main.build_api(main.sqlite_connector(database), notifications=queue)
    port = free_port()
    running = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=running.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not running.started and time.monotonic() < deadline:
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}"
    running.should_exit = True
    thread.join(timeout=5)
    queue.close(drain=False)


def test_stays_are_legal_and_all_different() -> None:
    stays = [burst.stay(index, 2026) for index in range(30)]
    assert stays[:3] == [("R7", "2026-12-01", "2026-12-02"), ("R8", "2026-12-01", "2026-12-02"),
                         ("R7", "2026-12-02", "2026-12-03")]
    assert len(set(stays)) == 30
    assert burst.stay(61, 2026) == ("R8", "2026-12-31", "2027-01-01")  # past the end of December


def test_percentile_is_nearest_rank() -> None:
    result = burst.BurstResult(count=4, latencies_ms=[4.0, 1.0, 3.0, 2.0])
    assert (result.percentile(0.5), result.percentile(0.95), result.percentile(1.0)) == (2.0, 4.0, 4.0)


def test_caught_up_needs_every_accepted_job_ended() -> None:
    base = {"notificationsAccepted": 6, "notificationsRejected": 14, "notificationsFailed": 1}
    assert not burst.caught_up({**base, "notificationsCompleted": 4, "notificationsQueued": 1})
    assert not burst.caught_up({**base, "notificationsCompleted": 4, "notificationsQueued": 0})  # one in flight
    assert burst.caught_up({**base, "notificationsCompleted": 5, "notificationsQueued": 0})
    assert burst.caught_up({"searches": 0})  # no queue at all


def test_a_burst_overflows_the_queue_and_every_booking_still_succeeds(
        server: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert burst.main([server, "--count", "20", "--wait"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[:4] == ["Sending 20 bookings, one after another...", "", "Accepted: 20", "Rejected: 0"]
    stats = json.loads(lines[lines.index("GET /stats") + 1])
    assert stats["notificationsAccepted"] + stats["notificationsRejected"] == 20
    assert stats["notificationsRejected"] > 0 and stats["notificationsQueued"] <= 5
    assert f"Answers with notificationFailed: true: {stats['notificationsRejected']}" in out
    assert "Everything the queue took, it finished." in out
    assert "Worker throughput:" in out


def test_json_output_and_a_second_year(server: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert burst.main([server, "--count", "4", "--year", "2027", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["accepted"] == 4 and len(result["latencies_ms"]) == 4


def test_the_same_nights_twice_are_refused_by_the_booking_rule(server: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert burst.main([server, "--count", "2", "--year", "2028"]) == 0
    assert burst.main([server, "--count", "2", "--year", "2028"]) == 1  # 409 x 2: the nights are taken
    assert "Rejected: 2" in capsys.readouterr().out
