"""Notifications' internal code: how a message travels. Only Notifications, the wiring and tests import this.

Both senders are simulated: they count what they would send and need no network, mail server or
SMS gateway. P10 gives the email sender the costs of a real one - it can be slow
(``send_seconds``, ``HOTEL_EMAIL_SECONDS``), it can time out (``timeout_seconds``) and it can fail
(``fail_every``) - and adds the two classes that take it off the booking request:

``QueuedNotificationSender``
    A **bounded** in-memory queue drained by a **fixed number of worker threads**. Handing it a
    confirmation never waits: the job either fits or is refused and counted (backpressure by
    refusal; ADR-004). It owns its threads from construction to ``close()``, and ``close()`` stops
    accepting first, drains with a time limit and then reports, by reservation id, whatever it
    could not finish. It is the only class in the package that starts a thread
    (``tests/test_architecture.py`` checks that).

``HeldConfirmations``
    The sender one booking request gets. It holds a place in the queue while the booking's
    transaction is open (so a full queue is known - and answered ``notificationFailed: true`` -
    before the guest is answered) and hands the confirmation over only after the commit. A booking
    that rolls back gives its place back, so no guest is ever emailed about a booking that was not
    saved, and the worker can never send before the row is committed.

Replacing the simulated senders with a real channel (or the in-memory queue with the transactional
outbox of P17) changes this file and the wiring, never Reservations.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from hotel_booking.notifications import (
    Confirmation,
    ConfirmationRefused,
    DeliveryStatus,
    NotificationCounts,
    NotificationSender,
)

logger = logging.getLogger(__name__)

ON_ITS_WAY = (DeliveryStatus.QUEUED, DeliveryStatus.SENDING, DeliveryStatus.SENT)
NAMED_IN_ONE_LINE = 100  # a shutdown log line lists at most this many reservation ids


def named(reservation_ids: tuple[str, ...]) -> str:
    """The ids for one log line: all of them up to NAMED_IN_ONE_LINE, then how many more (the report has all)."""
    shown = ", ".join(reservation_ids[:NAMED_IN_ONE_LINE])
    more = len(reservation_ids) - NAMED_IN_ONE_LINE
    return shown if more <= 0 else f"{shown} and {more} more"


class EmailNotificationSender:
    """Simulated email; keeps the ``NotificationSender`` promise by shape.

    ``send_seconds`` makes it as slow as a real mail server (P10 Step 1 turns it up to one second,
    which is how a booking of a few milliseconds became a one-second request). ``timeout_seconds``
    is the client's own limit, as an SMTP client has one: a send that would take longer gives up
    after that long with ``TimeoutError``. ``fail_every=n`` makes every n-th attempt fail with
    ``ConnectionError`` after its wait - a flaky mail server, for the retry policy. ``sent`` counts
    the messages that really went out. Safe to call from several worker threads at once.
    """

    def __init__(self, send_seconds: float = 0.0, timeout_seconds: float | None = None, fail_every: int = 0) -> None:
        self.sent = 0
        self._send_seconds = send_seconds
        self._timeout_seconds = timeout_seconds
        self._fail_every = fail_every
        self._attempts = 0
        self._lock = threading.Lock()

    def send_confirmation(self, confirmation: Confirmation) -> None:
        """'Send' the confirmation email for ``confirmation.reservation_id``."""
        with self._lock:
            self._attempts += 1
            attempt = self._attempts
        limit = self._timeout_seconds
        if limit is not None and self._send_seconds > limit:
            time.sleep(limit)
            raise TimeoutError(f"the mail server did not answer within {limit:g} s ({confirmation.reservation_id})")
        if self._send_seconds:
            time.sleep(self._send_seconds)
        if self._fail_every and attempt % self._fail_every == 0:
            raise ConnectionError(f"the mail server dropped the connection ({confirmation.reservation_id})")
        with self._lock:
            self.sent += 1


class SmsNotificationSender:
    """Simulated SMS (P04 Step 7); same promise as the email sender, so the wiring can pick either."""

    def __init__(self) -> None:
        self.sent = 0

    def send_confirmation(self, confirmation: Confirmation) -> None:
        """'Send' the confirmation text message for ``confirmation.reservation_id``."""
        self.sent += 1


@dataclass(frozen=True)
class ShutdownReport:
    """What ``QueuedNotificationSender.close`` did, for the log line the wiring prints at shutdown."""

    drained: bool                    # asked to finish the queue first?
    seconds: float                   # how long the close took
    counts: NotificationCounts       # the counters after the workers stopped
    dropped: tuple[str, ...]         # reservation ids cancelled from the queue - owed an email
    workers_still_running: int       # workers stuck in a send past the join limit (daemon threads)

    def owes_nobody(self) -> bool:
        """True when every confirmation the queue accepted was sent or definitely failed."""
        return not self.dropped and self.counts.in_flight == 0 and self.counts.queued == 0


class QueuedNotificationSender:
    """Takes confirmations off the request and gives them to a fixed pool of background workers.

    It keeps the ``NotificationSender`` promise, so ``BookingService`` cannot tell the difference:
    the booking hands over a ``Confirmation`` and carries on. What changes is *when* the email is
    sent, and what happens when there are more of them than the workers can keep up with.

    - **Bounded.** At most ``capacity`` confirmations wait (held places included). When it is full
      a new one is **refused and counted** (``rejected``) instead of waited for: waiting is what
      this class exists to stop, and a confirmation is not superseded by a newer one, so dropping
      an older job would be wrong too. ``send_confirmation`` never waits and never raises.
    - **Fixed workers.** ``workers`` threads, started here and stopped only by ``close``. Each takes
      one job at a time; the bound decides what is accepted, the workers how fast it is finished.
    - **Retry policy.** A send that raises is tried again up to ``max_attempts`` times in total,
      waiting ``retry_delay_seconds`` and then twice as long each time, in the same worker (it does
      not go back to the queue, so a retry can neither take another guest's place nor be sent
      twice). After the last attempt the job is ``failed``. The default, 1, is the course's
      policy: no retry. The send itself is bounded by the sender's own timeout.
    - **No duplicate sends.** A job is taken by exactly one worker, finished once, never put back;
      a confirmation whose reservation id is already queued, being sent or sent is not queued
      again.
    - **Delivery status.** ``status_of(reservation_id)`` answers for the last ``history_size``
      confirmations; every refusal, failure and drop is also logged with its reservation id.
    - **Shutdown.** ``close`` refuses new work at once, lets the workers finish the queue for at
      most ``timeout`` seconds (``drain=True``), then stops them - a retry that is waiting is
      cancelled at that moment - and drops what is left, reporting each reservation id. A send in
      progress cannot be interrupted (Python cannot stop a thread); it is bounded by the sender's
      timeout, and a worker still busy after ``join_seconds`` is reported, not waited for.
    """

    def __init__(
        self,
        sender: NotificationSender,
        capacity: int = 10,
        workers: int = 1,
        *,
        max_attempts: int = 1,
        retry_delay_seconds: float = 0.5,
        poll_seconds: float = 0.05,
        join_seconds: float = 5.0,
        history_size: int = 10_000,
    ) -> None:
        if capacity < 1 or workers < 1 or max_attempts < 1:
            raise ValueError("capacity, workers and max_attempts must each be at least 1")
        self._sender = sender
        self._queue: queue.Queue[Confirmation] = queue.Queue(maxsize=capacity)
        self._places = threading.BoundedSemaphore(capacity)  # one per waiting job, held places included
        self._lock = threading.Lock()
        self._finished = threading.Condition(self._lock)  # notified whenever a job reaches its end
        self._counters = {"accepted": 0, "rejected": 0, "completed": 0, "failed": 0, "dropped": 0}
        self._held: set[str] = set()  # reservation ids holding a place until their booking commits
        self._history: OrderedDict[str, DeliveryStatus] = OrderedDict()
        self._history_size = history_size
        self._max_attempts = max_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._poll_seconds = poll_seconds
        self._join_seconds = join_seconds
        self._closing = False                # no new work is accepted
        self._stopping = threading.Event()   # workers take no new job; waiting retries give up
        self._report: ShutdownReport | None = None
        self._workers = [threading.Thread(target=self._work, name=f"notifications-{number}", daemon=True)
                         for number in range(1, workers + 1)]
        for worker in self._workers:
            worker.start()

    # ------------------------------------------------------------------ the request side (never waits)

    def send_confirmation(self, confirmation: Confirmation) -> None:
        """Put the confirmation on the queue, or count it as refused. Never waits, never raises."""
        self.offer(confirmation)

    def offer(self, confirmation: Confirmation) -> bool:
        """One attempt that never waits: True if the confirmation is (or already was) on its way."""
        return self.reserve(confirmation) and self.publish(confirmation)

    def reserve(self, confirmation: Confirmation) -> bool:
        """Hold one place for ``confirmation`` (the booking has not committed yet). Never waits.

        False - counted as rejected - when the queue is full or closing. True without holding a
        second place when this reservation id is already held, queued, being sent or sent.
        """
        reservation_id = confirmation.reservation_id
        with self._lock:
            if reservation_id in self._held or self._history.get(reservation_id) in ON_ITS_WAY:
                logger.info("confirmation for %s is already on its way; not queued twice", reservation_id)
                return True
            if self._closing or not self._places.acquire(blocking=False):
                self._refuse(reservation_id, "the app is shutting down" if self._closing else "the queue is full")
                return False
            self._held.add(reservation_id)
            return True

    def publish(self, confirmation: Confirmation) -> bool:
        """The booking committed: put the held confirmation on the queue for a worker.

        False (and rejected) only if the app started shutting down in between; a confirmation that
        holds no place (a duplicate) is ignored and counts as on its way.
        """
        reservation_id = confirmation.reservation_id
        with self._lock:
            if reservation_id not in self._held:
                return self._history.get(reservation_id) in ON_ITS_WAY
            self._held.discard(reservation_id)
            if self._closing:
                self._places.release()
                self._refuse(reservation_id, "the app started shutting down before the booking committed")
                return False
            self._queue.put_nowait(confirmation)  # cannot be full: the place was held for it
            self._counters["accepted"] += 1
            self._remember(reservation_id, DeliveryStatus.QUEUED)
            return True

    def release(self, confirmation: Confirmation) -> None:
        """The booking rolled back: give the held place back; nothing is sent, nothing is counted."""
        with self._lock:
            if confirmation.reservation_id in self._held:
                self._held.discard(confirmation.reservation_id)
                self._places.release()

    # ------------------------------------------------------------------ what it reports

    def counts(self) -> NotificationCounts:
        """The counters of GET /stats, read as one consistent snapshot."""
        with self._lock:
            return NotificationCounts(queued=self._queue.qsize(), **self._counters)

    def status_of(self, reservation_id: str) -> DeliveryStatus | None:
        """What became of this reservation's confirmation, if it is among the recent ones."""
        with self._lock:
            return self._history.get(reservation_id)

    # ------------------------------------------------------------------ shutdown

    def close(self, drain: bool = True, timeout: float | None = None) -> ShutdownReport:
        """Stop accepting, finish (``drain``) for at most ``timeout`` seconds, stop the workers, report.

        Safe to call more than once: later calls return the first report.
        """
        started = time.monotonic()
        with self._lock:
            if self._report is not None:
                return self._report
            self._closing = True
        if drain:
            deadline = None if timeout is None else started + timeout
            with self._finished:
                while self._unfinished() > 0:
                    left = None if deadline is None else deadline - time.monotonic()
                    if left is not None and left <= 0:
                        break
                    self._finished.wait(left)
        self._stopping.set()
        for worker in self._workers:
            worker.join(timeout=self._join_seconds)
        dropped = self._cancel_waiting_jobs()
        still_running = sum(worker.is_alive() for worker in self._workers)
        report = ShutdownReport(drain, time.monotonic() - started, self.counts(), dropped, still_running)
        if dropped:
            logger.warning("shutdown cancelled %d queued confirmations, owed and not sent: %s",
                           len(dropped), named(dropped))
        if still_running:
            logger.warning("%d notification worker(s) still inside a send at shutdown", still_running)
        with self._lock:
            self._report = report
        return report

    def __enter__(self) -> QueuedNotificationSender:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close(drain=True)

    # ------------------------------------------------------------------ the worker side

    def _work(self) -> None:
        """One worker: take a job, deliver it (with the retry policy), record how it ended, repeat."""
        while not self._stopping.is_set():
            try:
                confirmation = self._queue.get(timeout=self._poll_seconds)  # wake up to notice a stop
            except queue.Empty:
                continue
            self._places.release()
            try:
                if self._stopping.is_set():  # taken in the same moment as the stop: not started
                    self._finish(confirmation, DeliveryStatus.DROPPED)
                    continue
                with self._lock:
                    self._remember(confirmation.reservation_id, DeliveryStatus.SENDING)
                self._finish(confirmation, self._deliver(confirmation))
            finally:
                self._queue.task_done()

    def _deliver(self, confirmation: Confirmation) -> DeliveryStatus:
        """Send, trying again after a failure while attempts are left; SENT, FAILED or DROPPED."""
        for attempt in range(1, self._max_attempts + 1):
            try:
                self._sender.send_confirmation(confirmation)
                return DeliveryStatus.SENT
            except Exception as error:  # noqa: BLE001 - any failure of the channel is the job's failure
                if attempt == self._max_attempts:
                    logger.warning("confirmation for %s failed after %d attempt(s): %s",
                                   confirmation.reservation_id, attempt, error)
                    return DeliveryStatus.FAILED
                delay = self._retry_delay_seconds * 2 ** (attempt - 1)
                logger.info("confirmation for %s: attempt %d failed (%s); retrying in %.2f s",
                            confirmation.reservation_id, attempt, error, delay)
                if self._stopping.wait(delay):  # a shutdown cancels the wait - and the job
                    return DeliveryStatus.DROPPED
        raise AssertionError("unreachable")  # pragma: no cover

    def _finish(self, confirmation: Confirmation, status: DeliveryStatus) -> None:
        with self._finished:
            self._counters[{DeliveryStatus.SENT: "completed", DeliveryStatus.FAILED: "failed",
                            DeliveryStatus.DROPPED: "dropped"}[status]] += 1
            self._remember(confirmation.reservation_id, status)
            self._finished.notify_all()

    def _cancel_waiting_jobs(self) -> tuple[str, ...]:
        """After the workers stopped: whatever is still queued is dropped, and named."""
        dropped: list[str] = []
        while True:
            try:
                confirmation = self._queue.get_nowait()
            except queue.Empty:
                return tuple(dropped)
            self._places.release()
            self._finish(confirmation, DeliveryStatus.DROPPED)
            self._queue.task_done()
            dropped.append(confirmation.reservation_id)

    # ------------------------------------------------------------------ helpers (call with the lock held)

    def _unfinished(self) -> int:
        """Accepted jobs that have not ended yet: queued plus in flight."""
        ended = self._counters["completed"] + self._counters["failed"] + self._counters["dropped"]
        return self._counters["accepted"] - ended

    def _refuse(self, reservation_id: str, reason: str) -> None:
        self._counters["rejected"] += 1
        self._remember(reservation_id, DeliveryStatus.REJECTED)
        logger.warning("confirmation for %s refused: %s (the booking itself is kept)", reservation_id, reason)

    def _remember(self, reservation_id: str, status: DeliveryStatus) -> None:
        self._history[reservation_id] = status
        self._history.move_to_end(reservation_id)
        while len(self._history) > self._history_size:
            self._history.popitem(last=False)


class HeldConfirmations:
    """The sender of ONE booking request: a place in the queue now, the confirmation after the commit.

    ``BookingService.reserve`` calls ``send_confirmation`` after saving the reservation but before
    the unit of work commits. This class only *holds a place* then - so a full or closing queue is
    reported at once, the R6 way (``ConfirmationRefused`` -> ``notificationFailed: true``, booking
    kept) - and the wiring calls ``publish`` after the commit or ``discard`` after a rollback.
    """

    def __init__(self, queue: QueuedNotificationSender) -> None:
        self._queue = queue
        self._held: list[Confirmation] = []

    def send_confirmation(self, confirmation: Confirmation) -> None:
        """Hold a place for the confirmation, or raise ``ConfirmationRefused``. Never waits."""
        if not self._queue.reserve(confirmation):
            raise ConfirmationRefused(f"no place in the notification queue for {confirmation.reservation_id}")
        self._held.append(confirmation)

    def publish(self) -> None:
        """The booking is committed: hand every held confirmation to the workers."""
        held, self._held = self._held, []
        for confirmation in held:
            self._queue.publish(confirmation)

    def discard(self) -> None:
        """The booking rolled back: give the places back; no guest hears about a booking that does not exist."""
        held, self._held = self._held, []
        for confirmation in held:
            self._queue.release(confirmation)
