"""Step 3's question "what would a burst of 30,000 do to an unbounded queue?", measured in-process.

    python3 practices/P10-bounded-async-processing/evidence/unbounded_30000.py hotel-booking

A queue of capacity 30,000 (the course's "HOTEL_QUEUE_CAPACITY=10000", made big enough) and one worker
held inside its first send: every confirmation is accepted and kept in memory. tracemalloc measures
what the queue and its delivery history hold. The close at the end drops them, and its log line names
the first 100 ids and counts the rest.
"""
from __future__ import annotations

import logging
import platform
import sys
import threading
import time
import tracemalloc
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from hotel_booking.notifications import Confirmation  # noqa: E402
from hotel_booking.notifications.internal import QueuedNotificationSender  # noqa: E402

logging.basicConfig(stream=sys.stdout, format="%(levelname)s %(message)s")
gate = threading.Event()


class Held:
    def send_confirmation(self, confirmation: Confirmation) -> None:
        gate.wait(30)


print(f"# Linux container, Python {platform.python_version()}; one worker held inside its first send")
tracemalloc.start()
queue = QueuedNotificationSender(Held(), capacity=30_000, workers=1)
base = tracemalloc.get_traced_memory()[0]
started = time.perf_counter()
for number in range(30_000):
    night = date(2026, 12, 1) + timedelta(days=number % 365)
    queue.send_confirmation(Confirmation(f"R{101 + number}", f"guest{number}@example.com",
                                         "R7" if number % 2 == 0 else "R8", night, night + timedelta(days=1)))
took = time.perf_counter() - started
used = tracemalloc.get_traced_memory()[0] - base
counts = queue.counts()
print(f"offered 30000 in {took:.2f} s: accepted={counts.accepted} rejected={counts.rejected} "
      f"queued={counts.queued} in_flight={counts.in_flight}")
print(f"memory held by the queue and its delivery history: {used / 1e6:.1f} MB ({used / 30000:.0f} bytes per job)")
print(f"time for one worker at 1 email per second to send them: {counts.accepted / 3600:.1f} hours")
gate.set()
report = queue.close(drain=False)
print(f"close(drain=False): dropped {len(report.dropped)}")
