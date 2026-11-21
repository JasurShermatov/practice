"""Automated checks for the P10 documents, diagrams and evidence ("Check your project", activity sheet §10).

The code is checked by hotel-booking's own tests (the queue, the wiring, the burst tool, the
contract, the borders). These checks cover what those tests cannot see:

- the project folder matches the course's "end of P10" list (with the recorded substitutions);
- docs/queue-trace.md has the course's sections (before, queue, unbounded, bounded, shutdown, what it
  still loses), and every number it quotes from a run is in the experiment log (nothing typed by hand);
- ADR-004 has the five headings, all five rejected shapes, both uncomfortable consequences and at
  least two revisit conditions, with the measured numbers;
- design-notes.md has the P10 section with five rejections, the kept shape and its limit;
- the contract is 1.3.0 with five *optional* notification counters;
- the experiment results hold the sheet's "always true" facts (bound never exceeded, accepted +
  rejected = 30, every booking 201, accepted = completed after the catch-up, drain owes nobody,
  P09 race 0 of 20);
- the as-built module diagram shows exactly the real imports; the class diagram is the one the UML
  test reads; every Mermaid source has an SVG and a clean mmdc run;
- the evidence index labels every row; every relative link resolves; the root README has a P10 row.

Run from the portfolio root:
    python -m pytest -p no:cacheprovider practices/P10-bounded-async-processing/checks -v
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

PRACTICE = Path(__file__).resolve().parents[1]
PORTFOLIO = PRACTICE.parents[1]
PROJECT = PORTFOLIO / "hotel-booking"
DOCS = PROJECT / "docs"
DIAGRAMS = PRACTICE / "diagrams"
LOGS = PRACTICE / "evidence" / "logs"

sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PORTFOLIO / "practices" / "P08-cache-scale-experiment" / "checks"))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    start = text.index(heading)
    following = re.search(r"^#{1,2} ", text[start + len(heading):], re.MULTILINE)
    return text[start:start + len(heading) + following.start()] if following else text[start:]


def results() -> dict[str, Any]:
    found: dict[str, Any] = json.loads(read(LOGS / "queue-results.json"))
    return found


EXPERIMENT = read(LOGS / "queue-experiment.txt")


# --------------------------------------------------------------------------- the project


def test_project_folder_matches_the_end_of_p10_folder() -> None:
    """The sheet's Python list; substitution: db/init.sql -> db/postgres/init.sql (+ db/sqlite/init.sql)."""
    expected = [
        "db/postgres/init.sql", "db/sqlite/init.sql", "docs/requests/maya-r7.json", "docs/requests/omar-r7.json",
        "docs/requests/omar-r8.json", "docs/adr-001-modular-monolith.md", "docs/adr-002-cache-availability.md",
        "docs/adr-003-booking-concurrency.md", "docs/adr-004-notification-concurrency.md", "docs/queue-trace.md",
        "docs/interleaving.md", "docs/api-check.md", "docs/cache-experiment.md", "docs/capacity.md",
        "docs/contexts.md", "docs/design-notes.md", "docs/diagrams.drawio", "docs/l04-notes.md", "docs/openapi.yaml",
        "docs/quality-scenarios.md", "docs/requirements.md",
        "hotel_booking/notifications/__init__.py", "hotel_booking/notifications/internal.py",
        "hotel_booking/api.py", "hotel_booking/api_cache.py", "tools/burst.py", "tools/measure.py",
        "tools/race_http.py", "docker-compose.yml", "main.py", "pyproject.toml", "requirements.txt",
        "test_api.py", "test_booking_service.py",
    ]
    missing = [path for path in expected if not (PROJECT / path).exists()]
    assert not missing, missing
    assert not list(PROJECT.glob("*.sqlite3")), "a local database file must not be handed in"


def test_the_contract_is_1_3_0_with_five_optional_notification_counters() -> None:
    yaml = pytest.importorskip("yaml")
    contract = yaml.safe_load(read(DOCS / "openapi.yaml"))
    assert contract["info"]["version"] == "1.3.0"
    stats = contract["components"]["schemas"]["Stats"]
    notification = {name for name in stats["properties"] if name.startswith("notifications")}
    assert notification == {"notificationsAccepted", "notificationsRejected", "notificationsCompleted",
                            "notificationsQueued", "notificationsFailed"}
    assert not notification & set(stats["required"])


def test_the_wiring_reads_the_course_variables() -> None:
    wiring = read(PROJECT / "main.py")
    for name in ("HOTEL_EMAIL_SECONDS", "HOTEL_QUEUE_CAPACITY", "HOTEL_WORKERS", "HOTEL_SEND_ATTEMPTS",
                 "HOTEL_DRAIN_SECONDS", "HOTEL_EMAIL_TIMEOUT"):
        assert name in wiring, name


# --------------------------------------------------------------------------- docs/queue-trace.md


TRACE = read(DOCS / "queue-trace.md")


def test_queue_trace_has_the_course_sections_in_order() -> None:
    assert TRACE.startswith("# The confirmation email, taken out of the request")
    headings = ["## What the email was costing the guest", "## With a queue in front of the sender",
                "## Why an unbounded queue is not the answer", "## With a bound, and counted rejections",
                "## What stopping the app does", "## What this design still loses"]
    positions = [TRACE.index(heading) for heading in headings]
    assert positions == sorted(positions)


def test_what_it_still_loses_names_kill_9_and_the_outbox() -> None:
    last = section(TRACE, "## What this design still loses")
    assert "kill -9" in last and "transactional outbox" in last and "P17" in last


def test_every_quoted_output_line_is_in_the_experiment_log() -> None:
    """Each line of every ```text block in queue-trace.md was printed by a real run (or is elided with ...)."""
    blocks = re.findall(r"```text\n(.*?)```", TRACE, re.DOTALL)
    assert len(blocks) >= 8
    for block in blocks:
        for line in block.splitlines():
            if not line.strip() or "..." in line:
                continue
            assert line in EXPERIMENT, f"not in the experiment log: {line}"


def test_the_numbers_in_the_text_are_the_measured_ones() -> None:
    measured = results()
    bounded = measured["bounded"]["burst"]
    assert (bounded["notificationsAccepted"], bounded["notificationsRejected"], bounded["notificationsQueued"]) == (
        11, 19, 10)
    assert "**accepted 30, rejected 0, queued 29**" in TRACE
    assert measured["unbounded"]["notificationsQueued"] == 29
    assert "Total: 30.2 s" in EXPERIMENT and "30.2 s" in TRACE
    assert "9.8 MB" in TRACE and "9.8 MB" in read(LOGS / "unbounded-30000.txt")
    assert "8.3 hours" in TRACE and "8.3 hours" in read(LOGS / "unbounded-30000.txt")
    for workers, label, drained, throughput in [(1, "1 s sender, capacity 10, burst 30", "10.9 s", "0.99"),
                                                 (2, "1 s sender, capacity 10, burst 30", "5.9 s", "1.98"),
                                                 (4, "1 s sender, capacity 10, burst 30", "3.9 s", "3.44"),
                                                 (4, "0.2 s sender, capacity 100, burst 50", "2.5 s", "18.75")]:
        row = measured["workers"][f"{workers}|{label}"]
        assert f"{row['drained_after']} s" == drained and f"{row['throughput']:.2f}" == throughput
        assert f"| {workers} |" in TRACE and drained in TRACE and throughput in TRACE


def test_the_three_things_that_are_always_true_held_in_every_run() -> None:
    measured = results()
    bursts = [measured["bounded"]["burst"], *[{"notificationsAccepted": r["accepted"],
                                              "notificationsRejected": r["rejected"],
                                              "notificationsQueued": r["queued"]} for r in measured["bounded_repeats"]]]
    for burst in bursts:
        assert burst["notificationsQueued"] <= 10
        assert burst["notificationsAccepted"] + burst["notificationsRejected"] == 30
    assert measured["bounded"]["rows"] == 30 and measured["bounded"]["refused_answers"] == 19
    later = measured["bounded"]["later"]
    assert later["notificationsAccepted"] == later["notificationsCompleted"] and later["notificationsQueued"] == 0
    assert max(point["queued"] for point in measured["bounded"]["series"]) <= 10


def test_the_shutdown_runs_show_drain_no_drain_sigterm_and_kill() -> None:
    measured = results()
    for key in ("stop_drain", "stop_sigterm"):
        assert "Nobody was owed an email." in measured[key]["shutdown"]
        assert any("completed=10" in line for line in measured[key]["shutdown"])
    assert any(line.startswith("7 guests are owed") for line in measured["stop_no_drain"]["shutdown"])
    assert measured["stop_kill9"]["shutdown"] == [] and measured["stop_kill9"]["rows"] == 10


def test_p09_still_holds_with_the_queue() -> None:
    race = results()["race"]
    postgres = results()["postgres"]
    for summary in (race["one_instance"]["summary"], race["two_instances"]["summary"],
                    postgres["race_two_instances"]["summary"]):
        assert summary.startswith("Double bookings: 0 of 20 rounds; one 201 and one 409: 20")
    assert postgres["double_booked_pairs"] == "none"


# --------------------------------------------------------------------------- ADR-004 and the design notes


ADR = read(DOCS / "adr-004-notification-concurrency.md")


def test_adr_004_has_the_five_sections() -> None:
    assert ADR.startswith("# ADR-004")
    for heading in ("## Context", "## Decision", "## Alternatives considered", "## Consequences", "## When to revisit"):
        assert heading in ADR, heading


def test_adr_004_rejects_the_five_shapes_with_reasons_about_the_work() -> None:
    alternatives = section(ADR, "## Alternatives considered")
    for shape in ("An actor per room", "A reactive pipeline", "Fork-join", "Structured concurrency",
                  "Software transactional memory", "An unbounded queue", "No queue"):
        assert f"**{shape}" in alternatives, shape
    assert len(re.findall(r"^\*\*", alternatives, re.MULTILINE)) >= 7


def test_adr_004_writes_both_uncomfortable_consequences_and_two_revisit_conditions() -> None:
    consequences = section(ADR, "## Consequences")
    assert "some guests get a room and no email" in consequences
    assert "killed process loses the queue" in consequences
    revisit = section(ADR, "## When to revisit")
    assert len(re.findall(r"^- \*\*", revisit, re.MULTILINE)) >= 2 and "P17" in revisit


def test_adr_004_numbers_are_the_measured_ones() -> None:
    sources = EXPERIMENT + read(LOGS / "unbounded-30000.txt")
    for number in ("1.04 s", "30.2 s", "9.8 MB", "p50 3.4 ms", "7.3 s", "7.2 s", "0.99", "1.98", "3.44"):
        assert number in ADR, number
        assert number in sources, number


def test_design_notes_have_the_p10_section_with_six_lines() -> None:
    text = read(DOCS / "design-notes.md")
    p10 = text[text.index("# P10 design notes"):]
    shapes = section(p10, "## Six shapes, one line each")
    assert len(re.findall(r"^- .+ - rejected: ", shapes, re.MULTILINE)) == 5
    assert re.search(r"^- Kept: a bounded queue", shapes, re.MULTILINE)
    assert re.search(r"^- What it still cannot do: ", shapes, re.MULTILINE)


# --------------------------------------------------------------------------- diagrams


def test_as_built_module_diagram_shows_exactly_the_real_imports() -> None:
    from test_p08_docs import mermaid_edges, real_edges

    drawn = {(left, right) for left, _, right in mermaid_edges(DIAGRAMS / "module-dependencies.mmd")}
    assert drawn == real_edges()
    assert ("api", "ntf_c") in drawn


def test_the_uml_test_reads_the_p10_class_diagram() -> None:
    conformance = read(PROJECT / "tests" / "test_uml_conformance.py")
    assert '"P10-bounded-async-processing" / "diagrams" / "class-diagram.mmd"' in conformance
    classes = read(DIAGRAMS / "class-diagram.mmd")
    for name in ("QueuedNotificationSender", "HeldConfirmations", "NotificationCounts", "DeliveryStatus",
                 "ConfirmationRefused", "ShutdownReport"):
        assert f"class {name} {{" in classes, name


def test_sequence_diagrams_name_the_real_code() -> None:
    queued = read(DIAGRAMS / "booking-with-queue.mmd")
    for name in ("HeldConfirmations", "reserve(confirmation)", "publish", "release", "ConfirmationRefused",
                 "save_changes", "notification_failed=True", "get(timeout=0.05)"):
        assert name in queued, name
    assert "send_confirmation" in read(DIAGRAMS / "booking-before.mmd")


def test_svgs_exist_for_every_mermaid_source() -> None:
    sources = sorted(DIAGRAMS.glob("*.mmd"))
    assert {source.stem for source in sources} >= {
        "booking-before", "booking-with-queue", "delivery-states", "shutdown", "concurrency-shapes",
        "class-diagram", "module-dependencies"}
    for source in sources:
        svg = source.with_suffix(".svg")
        assert svg.exists() and svg.stat().st_size > 1000, f"{svg.name} missing - run mmdc"
        assert svg.stat().st_mtime >= source.stat().st_mtime - 1, f"{svg.name} is older than its source"
    log = read(LOGS / "mmdc.txt")
    assert log.count("exit 0") == len(sources) and "Error" not in log


# --------------------------------------------------------------------------- links, index, portfolio


def test_evidence_index_labels_every_row() -> None:
    rows = [line for line in read(PRACTICE / "evidence" / "Index.md").splitlines() if re.match(r"^\| E\d+ ", line)]
    assert len(rows) >= 15
    for row in rows:
        assert re.search(r"\| \*\*(Observed|Simulated|Proposed)\*\* \|", row), row


LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def markdown_files() -> list[Path]:
    return sorted([*PRACTICE.rglob("*.md"), *DOCS.glob("*.md"), PROJECT / "README.md", PORTFOLIO / "README.md"])


@pytest.mark.parametrize("path", markdown_files(), ids=lambda path: str(path.relative_to(PORTFOLIO)))
def test_every_relative_link_resolves(path: Path) -> None:
    for target in LINK.findall(read(path)):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        assert (path.parent / target).exists(), f"{path.name}: broken link {target}"


def test_portfolio_readme_has_a_p10_row() -> None:
    assert re.search(
        r"^\| P10 \| .+\| \[practices/P10-bounded-async-processing\]\(practices/P10-bounded-async-processing\) \|",
        read(PORTFOLIO / "README.md"), re.MULTILINE)
