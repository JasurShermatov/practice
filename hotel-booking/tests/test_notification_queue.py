"""P10: the bounded notification queue on its own - bound, backpressure, workers, retry policy,
timeouts, cancellation, shutdown and drain, delivery status, no duplicate sends.

The queue is driven in-process, as the course's Step 5 tests drive it. Timing is controlled with
events (a sender that waits until the test lets it go), not with sleeps, wherever an exact count
is asserted; where a sleep is unavoidable (the queue's own retry delay, the sender's own timeout)
the assertion has a wide margin. Every queue is closed in a ``finally``/fixture, so no test leaves
worker threads behind (``test_closing_stops_every_worker_thread`` checks that it can).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import date, timedelta

import pytest

from hotel_booking.notifications import Confirmation, ConfirmationRefused, DeliveryStatus, NotificationCounts
from hotel_booking.notifications.internal import (
    EmailNotificationSender,
    HeldConfirmations,
    QueuedNotificationSender,
    SmsNotificationSender,
)


def confirmation(number: int) -> Confirmation:
    night = date(2026, 12, 1) + timedelta(days=number)
    return Confirmation(f"R{100 + number}", f"guest{number}@example.com", "R7", night, night + timedelta(days=1))


class Recorder:
    """A sender that records every reservation id it sent, from any number of workers at once."""

    def __init__(self, seconds: float = 0.0) -> None:
        self.sent: list[str] = []
        self._seconds = seconds
        self._lock = threading.Lock()

    def send_confirmation(self, message: Confirmation) -> None:
        if self._seconds:
            time.sleep(self._seconds)
        with self._lock:
            self.sent.append(message.reservation_id)


class Gate:
    """A sender that blocks inside the send until the test opens the gate; ``entered`` tells the test
    that a worker has taken a job and is inside the send (so it is in flight, not queued)."""

    def __init__(self) -> None:
        self.entered = threading.Semaphore(0)
        self.open = threading.Event()
        self.sent: list[str] = []

    def send_confirmation(self, message: Confirmation) -> None:
        self.entered.release()
        self.open.wait(10)
        self.sent.append(message.reservation_id)

    def wait_until_inside(self, workers: int = 1) -> None:
        for _ in range(workers):
            assert self.entered.acquire(timeout=5), "no worker took a job"


class Flaky:
    """Fails the first ``failures`` attempts of every confirmation, then sends it."""

    def __init__(self, failures: int, error: type[Exception] = ConnectionError) -> None:
        self.attempts: Counter[str] = Counter()
        self.sent: list[str] = []
        self._failures = failures
        self._error = error
        self._lock = threading.Lock()

    def send_confirmation(self, message: Confirmation) -> None:
        with self._lock:
            self.attempts[message.reservation_id] += 1
            if self.attempts[message.reservation_id] <= self._failures:
                raise self._error(f"mail server refused {message.reservation_id}")
            self.sent.append(message.reservation_id)


@pytest.fixture
def queues() -> Iterator[list[QueuedNotificationSender]]:
    """Queues made by a test; whatever the test did, they are closed (without draining) at the end."""
    made: list[QueuedNotificationSender] = []
    yield made
    for queue in made:
        queue.close(drain=False)


def wait_for(condition: Callable[[], bool], seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "condition not reached in time"
        time.sleep(0.005)


# --------------------------------------------------------------------------- bound and backpressure


def test_handing_over_never_waits_even_for_a_one_second_sender(queues: list[QueuedNotificationSender]) -> None:
    slow = EmailNotificationSender(send_seconds=1)
    queue = QueuedNotificationSender(slow, capacity=10, workers=1)
    queues.append(queue)
    started = time.monotonic()
    for number in range(30):  # 30 hand-overs, 20 of them into a full queue
        queue.send_confirmation(confirmation(number))
    assert time.monotonic() - started < 0.1
    assert slow.sent == 0


def test_a_full_queue_refuses_counts_and_never_waits(queues: list[QueuedNotificationSender]) -> None:
    """The exact course numbers, made deterministic: the worker is held inside job 1, ten wait,
    nineteen are refused - 11 accepted and 19 rejected, the split the course saw over HTTP."""
    gate = Gate()
    queue = QueuedNotificationSender(gate, capacity=10, workers=1)
    queues.append(queue)
    queue.send_confirmation(confirmation(0))
    gate.wait_until_inside()
    results = [queue.offer(confirmation(number)) for number in range(1, 30)]
    counts = queue.counts()
    assert results == [True] * 10 + [False] * 19
    assert counts == NotificationCounts(accepted=11, rejected=19, completed=0, queued=10)
    assert counts.in_flight == 1
    assert queue.status_of("R111") is DeliveryStatus.REJECTED
    gate.open.set()
    wait_for(lambda: queue.counts().completed == 11)
    final = queue.counts()
    assert (final.accepted, final.completed, final.queued, final.in_flight) == (11, 11, 0, 0)


def test_the_bound_holds_and_the_sums_balance_under_many_producers(queues: list[QueuedNotificationSender]) -> None:
    """8 producer threads x 50 confirmations into a queue of 10 with 3 workers, read 200 times meanwhile:
    queued never above 10, in flight never above 3, and accepted + rejected = 400 at the end."""
    recorder = Recorder(seconds=0.002)
    queue = QueuedNotificationSender(recorder, capacity=10, workers=3)
    queues.append(queue)
    snapshots: list[NotificationCounts] = []
    go = threading.Event()

    def produce(first: int) -> None:
        go.wait()
        for number in range(first, first + 50):
            queue.send_confirmation(confirmation(number))

    producers = [threading.Thread(target=produce, args=(start * 50,)) for start in range(8)]
    for producer in producers:
        producer.start()
    go.set()
    for _ in range(200):
        snapshots.append(queue.counts())
    for producer in producers:
        producer.join()
    queue.close(drain=True, timeout=10)
    final = queue.counts()
    assert all(snap.queued <= 10 and 0 <= snap.in_flight <= 3 for snap in snapshots)
    assert final.accepted + final.rejected == 400
    assert final.rejected > 0
    assert final.accepted == final.completed and final.queued == 0
    assert sorted(recorder.sent) == sorted(set(recorder.sent))  # nobody got two emails
    assert len(recorder.sent) == final.completed


def test_workers_are_a_fixed_pool_that_drains_in_parallel(queues: list[QueuedNotificationSender]) -> None:
    """The bound decides what is accepted; the workers decide how fast it is finished."""
    timings = {}
    for workers in (1, 3):
        recorder = Recorder(seconds=0.05)
        queue = QueuedNotificationSender(recorder, capacity=12, workers=workers)
        queues.append(queue)
        assert sum(thread.name.startswith("notifications-") and thread.is_alive()
                   for thread in queue._workers) == workers  # noqa: SLF001 - the pool itself
        started = time.monotonic()
        accepted = sum(queue.offer(confirmation(number)) for number in range(12))
        queue.close(drain=True, timeout=10)
        timings[workers] = time.monotonic() - started
        assert accepted == 12 and len(recorder.sent) == 12
    assert timings[3] < timings[1] * 0.6  # 12 x 50 ms: about 0.6 s alone, about 0.2 s with three


def test_constructor_refuses_a_queue_without_room_or_workers() -> None:
    for bad in ({"capacity": 0}, {"workers": 0}, {"max_attempts": 0}):
        with pytest.raises(ValueError):
            QueuedNotificationSender(Recorder(), **bad)


# --------------------------------------------------------------------------- failures and the retry policy


def test_without_retry_a_failed_send_is_counted_logged_and_the_worker_goes_on(
        queues: list[QueuedNotificationSender], caplog: pytest.LogCaptureFixture) -> None:
    """The course's policy (max_attempts=1): no retry. The failure is not lost silently - it is
    counted (failed), recorded (FAILED) and logged with the reservation id - and the next job is sent."""
    flaky = Flaky(failures=1)
    queue = QueuedNotificationSender(flaky, capacity=5, workers=1)
    queues.append(queue)
    with caplog.at_level(logging.WARNING, logger="hotel_booking.notifications.internal"):
        queue.send_confirmation(confirmation(1))
        queue.close(drain=True, timeout=5)
    assert queue.counts() == NotificationCounts(accepted=1, rejected=0, completed=0, queued=0, failed=1)
    assert queue.status_of("R101") is DeliveryStatus.FAILED
    assert flaky.attempts["R101"] == 1 and flaky.sent == []
    assert "R101 failed after 1 attempt(s)" in caplog.text


def test_a_failing_job_does_not_stop_the_worker(queues: list[QueuedNotificationSender]) -> None:
    class FirstFails(Recorder):
        def send_confirmation(self, message: Confirmation) -> None:
            if message.reservation_id == "R101":
                raise RuntimeError("bad address")
            super().send_confirmation(message)

    sender = FirstFails()
    queue = QueuedNotificationSender(sender, capacity=5, workers=1)
    queues.append(queue)
    for number in (1, 2, 3):
        queue.send_confirmation(confirmation(number))
    queue.close(drain=True, timeout=5)
    assert sender.sent == ["R102", "R103"]
    counts = queue.counts()
    assert (counts.completed, counts.failed, counts.in_flight) == (2, 1, 0)


def test_retry_sends_once_after_two_failures(queues: list[QueuedNotificationSender]) -> None:
    flaky = Flaky(failures=2)
    queue = QueuedNotificationSender(flaky, capacity=5, workers=1, max_attempts=3, retry_delay_seconds=0.01)
    queues.append(queue)
    queue.send_confirmation(confirmation(1))
    queue.close(drain=True, timeout=5)
    assert flaky.attempts["R101"] == 3
    assert flaky.sent == ["R101"]  # sent exactly once
    assert queue.status_of("R101") is DeliveryStatus.SENT
    assert queue.counts().completed == 1 and queue.counts().failed == 0


def test_retry_gives_up_after_the_last_attempt_and_waits_longer_each_time(
        queues: list[QueuedNotificationSender]) -> None:
    flaky = Flaky(failures=10)
    queue = QueuedNotificationSender(flaky, capacity=5, workers=1, max_attempts=3, retry_delay_seconds=0.05)
    queues.append(queue)
    started = time.monotonic()
    queue.send_confirmation(confirmation(1))
    queue.close(drain=True, timeout=5)
    elapsed = time.monotonic() - started
    assert flaky.attempts["R101"] == 3 and flaky.sent == []
    assert queue.status_of("R101") is DeliveryStatus.FAILED
    assert queue.counts().failed == 1
    assert 0.15 - 0.02 <= elapsed < 2.0  # waits 0.05 s, then 0.10 s (backoff doubles)


def test_a_retry_never_takes_another_guests_place(queues: list[QueuedNotificationSender]) -> None:
    """Retries happen inside the worker, not by putting the job back: a full queue stays full."""
    flaky = Flaky(failures=1)
    queue = QueuedNotificationSender(flaky, capacity=1, workers=1, max_attempts=2, retry_delay_seconds=0.2)
    queues.append(queue)
    queue.send_confirmation(confirmation(1))
    wait_for(lambda: flaky.attempts["R101"] == 1)  # R101 failed once and is waiting to retry
    assert queue.offer(confirmation(2)) is True     # the one place is free for R102
    assert queue.offer(confirmation(3)) is False    # and R101's retry did not take it back
    queue.close(drain=True, timeout=5)
    assert sorted(flaky.sent) == ["R101", "R102"]


def test_the_senders_own_timeout_bounds_a_hanging_mail_server(queues: list[QueuedNotificationSender]) -> None:
    """A mail server that would take 10 s is given up after the client's 0.2 s timeout, and the
    worker is free for the next job: the timeout is what keeps one bad send from blocking the queue."""
    email = EmailNotificationSender(send_seconds=10, timeout_seconds=0.2)
    with pytest.raises(TimeoutError):
        email.send_confirmation(confirmation(0))
    queue = QueuedNotificationSender(email, capacity=5, workers=1)
    queues.append(queue)
    started = time.monotonic()
    queue.send_confirmation(confirmation(1))
    queue.send_confirmation(confirmation(2))
    report = queue.close(drain=True, timeout=5)
    assert time.monotonic() - started < 1.5
    assert report.counts.failed == 2 and email.sent == 0


def test_a_flaky_mail_server_fails_every_nth_attempt() -> None:
    email = EmailNotificationSender(fail_every=3)
    outcomes = []
    for number in range(6):
        try:
            email.send_confirmation(confirmation(number))
            outcomes.append("sent")
        except ConnectionError:
            outcomes.append("failed")
    assert outcomes == ["sent", "sent", "failed", "sent", "sent", "failed"]
    assert email.sent == 4


# --------------------------------------------------------------------------- no duplicate sends


def test_the_same_confirmation_offered_twice_is_sent_once(queues: list[QueuedNotificationSender]) -> None:
    recorder = Recorder()
    queue = QueuedNotificationSender(recorder, capacity=5, workers=2)
    queues.append(queue)
    assert queue.offer(confirmation(1)) is True
    assert queue.offer(confirmation(1)) is True  # already on its way: not queued again
    wait_for(lambda: queue.status_of("R101") is DeliveryStatus.SENT)
    assert queue.offer(confirmation(1)) is True  # already sent: not sent again
    queue.close(drain=True, timeout=5)
    assert recorder.sent == ["R101"]
    assert queue.counts().accepted == 1


def test_many_workers_and_retries_still_send_every_email_exactly_once(queues: list[QueuedNotificationSender]) -> None:
    flaky = Flaky(failures=1)
    queue = QueuedNotificationSender(flaky, capacity=300, workers=4, max_attempts=2, retry_delay_seconds=0.001)
    queues.append(queue)
    for number in range(300):
        queue.send_confirmation(confirmation(number))
    queue.close(drain=True, timeout=20)
    assert len(flaky.sent) == 300 and len(set(flaky.sent)) == 300
    assert set(flaky.attempts.values()) == {2}
    assert queue.counts().completed == 300


# --------------------------------------------------------------------------- shutdown, drain, cancellation


def test_close_with_drain_finishes_everything_and_reports_nobody_owed(queues: list[QueuedNotificationSender]) -> None:
    recorder = Recorder(seconds=0.01)
    queue = QueuedNotificationSender(recorder, capacity=10, workers=1)
    queues.append(queue)
    for number in range(10):
        queue.send_confirmation(confirmation(number))
    report = queue.close(drain=True, timeout=5)
    assert report.drained and report.owes_nobody() and report.dropped == ()
    assert report.counts.completed == 10 and len(recorder.sent) == 10


def test_close_without_drain_cancels_the_queue_and_names_every_guest_owed(
        queues: list[QueuedNotificationSender], caplog: pytest.LogCaptureFixture) -> None:
    """The course's "without the drain": 10 accepted, the worker busy with one. Here the six-or-so
    left behind are not silently queued in a dying process - they are dropped, named and logged."""
    gate = Gate()
    queue = QueuedNotificationSender(gate, capacity=10, workers=1)
    queues.append(queue)
    for number in range(10):
        queue.send_confirmation(confirmation(number))
    gate.wait_until_inside()                    # R100 is being sent
    with caplog.at_level(logging.WARNING, logger="hotel_booking.notifications.internal"):
        threading.Timer(0.1, gate.open.set).start()  # the send in progress finishes during the close
        report = queue.close(drain=False)
    assert report.dropped == tuple(f"R{100 + number}" for number in range(1, 10))
    assert report.counts == NotificationCounts(accepted=10, rejected=0, completed=1, queued=0, failed=0, dropped=9)
    assert not report.owes_nobody()
    assert gate.sent == ["R100"]
    assert all(queue.status_of(f"R{100 + number}") is DeliveryStatus.DROPPED for number in range(1, 10))
    assert "shutdown cancelled 9 queued confirmations" in caplog.text and "R109" in caplog.text


def test_a_drain_has_a_time_limit(queues: list[QueuedNotificationSender]) -> None:
    """A shutdown must not drain for ever: after the limit the rest is dropped and reported."""
    recorder = Recorder(seconds=0.1)
    queue = QueuedNotificationSender(recorder, capacity=20, workers=1)
    queues.append(queue)
    for number in range(20):  # 2 s of work
        queue.send_confirmation(confirmation(number))
    started = time.monotonic()
    report = queue.close(drain=True, timeout=0.35)
    took = time.monotonic() - started
    assert took < 0.35 + 0.1 + 0.3            # the limit, plus at most the one send in progress
    assert 2 <= report.counts.completed <= 5
    assert len(report.dropped) == 20 - report.counts.completed
    assert report.counts.accepted == report.counts.completed + report.counts.dropped


def test_closing_refuses_new_work_at_once(queues: list[QueuedNotificationSender]) -> None:
    gate = Gate()
    queue = QueuedNotificationSender(gate, capacity=5, workers=1)
    queues.append(queue)
    queue.send_confirmation(confirmation(1))
    gate.wait_until_inside()
    closer = threading.Thread(target=queue.close, kwargs={"drain": True, "timeout": 5})
    closer.start()
    wait_for(lambda: queue._closing)  # noqa: SLF001 - the moment the close has begun
    assert queue.offer(confirmation(2)) is False
    with pytest.raises(ConfirmationRefused):
        HeldConfirmations(queue).send_confirmation(confirmation(3))
    gate.open.set()
    closer.join()
    assert queue.counts() == NotificationCounts(accepted=1, rejected=2, completed=1, queued=0)
    assert queue.status_of("R102") is DeliveryStatus.REJECTED


def test_shutdown_cancels_a_waiting_retry_at_once(queues: list[QueuedNotificationSender]) -> None:
    flaky = Flaky(failures=1)
    queue = QueuedNotificationSender(flaky, capacity=5, workers=1, max_attempts=3, retry_delay_seconds=30)
    queues.append(queue)
    queue.send_confirmation(confirmation(1))
    wait_for(lambda: flaky.attempts["R101"] == 1)  # now waiting 30 s before the second attempt
    started = time.monotonic()
    report = queue.close(drain=False)
    assert time.monotonic() - started < 1.0
    assert queue.status_of("R101") is DeliveryStatus.DROPPED
    assert report.counts.dropped == 1 and report.workers_still_running == 0


def test_a_send_that_will_not_end_is_reported_not_waited_for(queues: list[QueuedNotificationSender]) -> None:
    """Python cannot interrupt a thread. A worker stuck in a send past ``join_seconds`` is reported,
    and the close returns; the thread is a daemon and ends with the process."""
    gate = Gate()
    queue = QueuedNotificationSender(gate, capacity=5, workers=1, join_seconds=0.2)
    queues.append(queue)
    queue.send_confirmation(confirmation(1))
    gate.wait_until_inside()
    started = time.monotonic()
    report = queue.close(drain=False)
    assert time.monotonic() - started < 1.0
    assert report.workers_still_running == 1 and report.counts.in_flight == 1
    assert not report.owes_nobody()
    gate.open.set()


def test_close_is_idempotent_and_the_context_manager_drains(queues: list[QueuedNotificationSender]) -> None:
    recorder = Recorder()
    with QueuedNotificationSender(recorder, capacity=5, workers=2) as queue:
        for number in range(5):
            queue.send_confirmation(confirmation(number))
    assert len(recorder.sent) == 5
    first = queue.close(drain=True)
    assert queue.close(drain=False) is first


def test_closing_stops_every_worker_thread() -> None:
    queue = QueuedNotificationSender(Recorder(), capacity=5, workers=3)
    workers = list(queue._workers)  # noqa: SLF001
    assert all(worker.is_alive() and worker.daemon for worker in workers)
    queue.close(drain=True, timeout=5)
    assert not any(worker.is_alive() for worker in workers)


# --------------------------------------------------------------------------- the request-scoped sender


def test_held_confirmations_reach_the_workers_only_after_publish(queues: list[QueuedNotificationSender]) -> None:
    recorder = Recorder()
    queue = QueuedNotificationSender(recorder, capacity=2, workers=1)
    queues.append(queue)
    held = HeldConfirmations(queue)
    held.send_confirmation(confirmation(1))
    time.sleep(0.1)  # a worker that could see it would have sent it by now
    assert recorder.sent == [] and queue.counts().accepted == 0
    held.publish()
    queue.close(drain=True, timeout=5)
    assert recorder.sent == ["R101"]


def test_a_held_place_counts_against_the_bound_and_a_discard_gives_it_back(
        queues: list[QueuedNotificationSender]) -> None:
    recorder = Recorder()
    queue = QueuedNotificationSender(recorder, capacity=1, workers=1)
    queues.append(queue)
    first = HeldConfirmations(queue)
    first.send_confirmation(confirmation(1))                 # holds the only place
    with pytest.raises(ConfirmationRefused):
        HeldConfirmations(queue).send_confirmation(confirmation(2))
    first.discard()                                          # rolled back: place free, nothing sent
    second = HeldConfirmations(queue)
    second.send_confirmation(confirmation(3))
    second.publish()
    queue.close(drain=True, timeout=5)
    assert recorder.sent == ["R103"]
    assert queue.counts() == NotificationCounts(accepted=1, rejected=1, completed=1, queued=0)
    assert queue.status_of("R101") is None  # never promised, never counted


def test_delivery_status_follows_a_job_and_the_history_is_bounded(queues: list[QueuedNotificationSender]) -> None:
    gate = Gate()
    queue = QueuedNotificationSender(gate, capacity=1, workers=1, history_size=3)
    queues.append(queue)
    queue.send_confirmation(confirmation(1))
    gate.wait_until_inside()
    assert queue.status_of("R101") is DeliveryStatus.SENDING
    queue.send_confirmation(confirmation(2))
    assert queue.status_of("R102") is DeliveryStatus.QUEUED
    queue.send_confirmation(confirmation(3))
    assert queue.status_of("R103") is DeliveryStatus.REJECTED
    gate.open.set()
    queue.close(drain=True, timeout=5)
    assert queue.status_of("R101") is DeliveryStatus.SENT
    for number in range(4, 8):
        queue.send_confirmation(confirmation(number))  # closed: refused, and remembered
    assert queue.status_of("R101") is None  # only the last three are kept
    assert queue.status_of("R107") is DeliveryStatus.REJECTED


def test_a_shutdown_log_line_names_at_most_a_hundred_guests() -> None:
    """Found by the 30,000-job measurement: one log line with 29,999 ids. The report keeps them all."""
    from hotel_booking.notifications.internal import named

    ids = tuple(f"R{number}" for number in range(250))
    assert named(ids[:3]) == "R0, R1, R2"
    line = named(ids)
    assert line.endswith("R99 and 150 more") and line.count(",") == 99


def test_the_sms_sender_counts_exactly_when_several_threads_send_at_once() -> None:
    """8 threads x 2,000 SMS, released together by a barrier: ``sent`` is exactly 16,000 (its lock)."""
    sender = SmsNotificationSender()
    threads, per_thread = 8, 2000
    barrier = threading.Barrier(threads)

    def send_many(first: int) -> None:
        barrier.wait()
        for number in range(first, first + per_thread):
            sender.send_confirmation(confirmation(number))

    workers = [threading.Thread(target=send_many, args=(index * per_thread,)) for index in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert sender.sent == threads * per_thread
