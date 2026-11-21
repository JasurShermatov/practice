"""Shared test fixtures: a fresh hotel with rooms R7 and R8 and an empty store.

P08 addition: ``redis_server`` - a real, throw-away redis-server for the cache tests.

P06 change (deliberate, imports only): the classes now come from their modules;
the tests, like the wiring, may name internal classes.
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from hotel_booking.demo import HOTEL_ROOMS
from hotel_booking.notifications.internal import EmailNotificationSender
from hotel_booking.reservations import BookingService
from hotel_booking.reservations.internal import InMemoryReservationStore


@dataclass
class Hotel:
    service: BookingService
    store: InMemoryReservationStore
    email: EmailNotificationSender


@pytest.fixture
def hotel() -> Hotel:
    store = InMemoryReservationStore()
    email = EmailNotificationSender()
    return Hotel(BookingService(HOTEL_ROOMS, store, email), store, email)


# --------------------------------------------------------------------------- P08: a real Redis for the cache tests


@dataclass
class RedisServer:
    """A throw-away redis-server on a free port (no persistence); ``stop``/``start`` simulate an outage."""

    port: int
    directory: Path
    process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        self.process = subprocess.Popen(
            ["redis-server", "--port", str(self.port), "--bind", "127.0.0.1", "--save", "", "--appendonly", "no",
             "--dir", str(self.directory)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2) as probe:
                    probe.sendall(b"PING\r\n")
                    if probe.recv(16).startswith(b"+PONG"):
                        return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("redis-server did not start")

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="session")
def redis_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RedisServer]:
    """Skipped where redis-server is not installed (the build environment has Redis 7.0)."""
    if shutil.which("redis-server") is None:
        pytest.skip("redis-server is not installed")
    server = RedisServer(free_port(), tmp_path_factory.mktemp("redis"))
    server.start()
    yield server
    server.stop()
