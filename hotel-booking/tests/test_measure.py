"""P08: the measurement tool (tools/measure.py) against a real uvicorn server, plus its arithmetic.

The server runs in a background thread on a free port, over a SQLite file, wired by main.build_api
exactly like ``python main.py`` (with the in-process cache, so no Redis is needed here).
"""
from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

import main
from hotel_booking.api_cache import AvailabilityCache, InMemoryKeyValueStore
from tools import measure

from .conftest import free_port


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    database = tmp_path_factory.mktemp("measure") / "hotel.sqlite3"
    app, _ = main.build_api(main.sqlite_connector(database), cache=AvailabilityCache(InMemoryKeyValueStore()))
    port = free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    running = uvicorn.Server(config)
    thread = threading.Thread(target=running.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not running.started and time.monotonic() < deadline:
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}"
    running.should_exit = True
    thread.join(timeout=5)


def test_percentile_is_nearest_rank() -> None:
    times = [float(n) for n in range(1, 1001)]
    assert measure.percentile(times, 0.95) == 950.0  # the 950th of 1,000
    assert measure.percentile(times, 0.50) == 500.0
    assert measure.percentile([7.0], 0.95) == 7.0
    with pytest.raises(ValueError):
        measure.percentile([], 0.95)


def test_difference_of_the_counters() -> None:
    assert measure.difference({"searches": 3, "cacheHits": 1}, {"searches": 1003, "cacheHits": 1000}) == {
        "searches": 1000, "cacheHits": 999}


def test_one_client_first_search_misses_the_rest_hit(server: str) -> None:
    result = measure.measure(server, "2026-03-01", "2026-03-03", searches=50)
    assert result.stats_difference == {"searches": 50, "databaseQueries": 2, "cacheHits": 49,
                                       "cacheMisses": 1, "cacheErrors": 0}
    assert result.x_cache == {"hit": 49, "miss": 1}
    assert 0 < result.p50_ms <= result.p95_ms <= result.p99_ms <= result.max_ms
    assert result.throughput_per_s > 0


def test_several_clients_share_the_searches(server: str) -> None:
    result = measure.measure(server, "2026-04-01", "2026-04-03", searches=31, clients=4)
    assert result.stats_difference["searches"] == 31
    assert sum(result.x_cache.values()) == 31


def test_the_report_starts_with_the_course_lines(server: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert measure.main(["2026-05-01", "2026-05-03", "--searches", "20", "--url", server, "--json"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "20 searches for 2026-05-01 to 2026-05-03"
    assert [line.split(":")[0] for line in lines[1:5]] == ["Average", "p95", "Total", "GET /stats difference"]
    assert lines[4] == ('GET /stats difference: {"searches":20,"databaseQueries":2,"cacheHits":19,'
                        '"cacheMisses":1,"cacheErrors":0}')
    assert lines[-1].startswith('{"searches":20,"clients":1,')


def test_a_wrong_answer_stops_the_tool(server: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert measure.main(["2026-05-03", "2026-05-01", "--searches", "5", "--url", server]) == 1
    assert "answered 400" in capsys.readouterr().err


def test_nothing_listening_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    assert measure.main(["--searches", "1", "--url", f"http://127.0.0.1:{free_port()}"]) == 1
    assert "measure:" in capsys.readouterr().err
