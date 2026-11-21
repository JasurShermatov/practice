"""Automated checks for the P09 documents, diagrams and evidence ("Check your project", activity sheet §10).

The code is checked by hotel-booking's own tests (the no-overlap promise on every store, the race over
HTTP, the PostgreSQL path, the contract, the borders). These checks cover what those tests cannot see:

- db/postgres/init.sql has what the sheet's checklist asks: btree_gist, the *named* constraint, the
  id sequence; the course's "finished P09 folder" is there (with the recorded substitutions);
- docs/interleaving.md has the course's sections, an eight-row trace, the anomaly named, and the
  four-repairs table whose numbers are the ones the logs recorded (nothing typed by hand);
- ADR-003 has the five headings, all three rejected repairs with their measured cost, the clean-up
  consequence and a revisit condition;
- the race results in the README are the ones in evidence/logs/race-results.json (20 of 20 before,
  0 of 20 after, for one and two instances, SQLite and PostgreSQL);
- every sequence diagram names real code (OverlapRejected, next_reservation_id, the constraint, the
  SQL the store sends); every Mermaid source has a rendered SVG and a clean mmdc run;
- design-notes.md has the P09 section; every relative link resolves; the evidence index labels
  every row; the root README has a P09 row.

Run from the portfolio root:
    python -m pytest -p no:cacheprovider practices/P09-protect-the-last-seat/checks -v
"""
from __future__ import annotations

import json
import re
import statistics
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


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    start = text.index(heading)
    following = re.search(r"^#{1,2} ", text[start + len(heading):], re.MULTILINE)
    return text[start:start + len(heading) + following.start()] if following else text[start:]


def race_results() -> dict[str, Any]:
    results: dict[str, Any] = json.loads(read(LOGS / "race-results.json"))
    return results


# --------------------------------------------------------------------------- the project


def test_init_sql_has_btree_gist_the_named_constraint_and_the_sequence() -> None:
    sql = read(PROJECT / "db" / "postgres" / "init.sql")
    assert "CREATE EXTENSION IF NOT EXISTS btree_gist;" in sql
    assert re.search(r"CONSTRAINT reservations_no_overlap EXCLUDE USING gist \(\s+room WITH =,\s+"
                     r"daterange\(check_in, check_out, '\[\)'\) WITH &&\s+\) WHERE \(status = 'Confirmed'\)", sql)
    assert "CREATE SEQUENCE reservation_ids START 101;" in sql


def test_project_folder_matches_the_finished_p09_folder() -> None:
    """The sheet's list for Python; substitutions: db/init.sql -> db/postgres/init.sql (+ db/sqlite/init.sql)."""
    expected = [
        "db/postgres/init.sql", "db/sqlite/init.sql", "docs/requests/maya-r7.json", "docs/requests/omar-r7.json",
        "docs/requests/omar-r8.json", "docs/adr-001-modular-monolith.md", "docs/adr-002-cache-availability.md",
        "docs/adr-003-booking-concurrency.md", "docs/interleaving.md", "docs/l05-notes.md", "docs/api-check.md",
        "docs/cache-experiment.md", "docs/capacity.md", "docs/contexts.md", "docs/design-notes.md",
        "docs/diagrams.drawio", "docs/openapi.yaml", "docs/quality-scenarios.md", "docs/requirements.md",
        "hotel_booking/reservations/__init__.py", "hotel_booking/reservations/booking.py",
        "hotel_booking/reservations/domain.py", "hotel_booking/reservations/internal.py", "hotel_booking/api.py",
        "hotel_booking/api_cache.py", "tools/measure.py", "tools/race_http.py", "docker-compose.yml", "main.py",
        "pyproject.toml", "requirements.txt", "test_api.py", "test_booking_service.py",
    ]
    missing = [path for path in expected if not (PROJECT / path).exists()]
    assert not missing, missing
    assert not list(PROJECT.glob("*.sqlite3")), "a local database file must not be handed in"


def test_the_contract_adds_the_race_example_and_is_1_2_0() -> None:
    yaml = pytest.importorskip("yaml")
    contract = yaml.safe_load(read(DOCS / "openapi.yaml"))
    assert contract["info"]["version"] == "1.2.0"
    conflict = contract["paths"]["/reservations"]["post"]["responses"]["409"]
    examples = conflict["content"]["application/problem+json"]["examples"]
    assert set(examples) == {"sharedNight", "lostTheRace"}
    assert "same moment" in conflict["description"]


def test_design_notes_have_the_p09_sections() -> None:
    text = read(DOCS / "design-notes.md")
    p09 = text[text.index("# P09 design notes"):]
    found = re.findall(r"^## (.+)$", p09, re.MULTILINE)
    for heading in ("The race, reproduced", "Where the rule lives", "After", "Decisions made while building"):
        assert heading in found, f"design-notes.md P09: missing ## {heading}"


def test_l05_notes_have_three_answers() -> None:
    assert len(re.findall(r"^\d\. \*\*", read(DOCS / "l05-notes.md"), re.MULTILINE)) == 3


# --------------------------------------------------------------------------- docs/interleaving.md


def test_interleaving_has_the_course_sections() -> None:
    text = read(DOCS / "interleaving.md")
    assert text.startswith("# The interleaving that double-books R7")
    found = re.findall(r"^## (.+)$", text, re.MULTILINE)
    for heading in ("What I ran", "The interleaving, statement by statement", "Which anomaly this is",
                    "The invariant this breaks", "Why locking the reservation rows cannot fix it",
                    "The four repairs, and what each one cost", "What it took to turn the constraint on",
                    "What I kept"):
        assert heading in found, f"interleaving.md: missing ## {heading}"


def test_the_trace_has_eight_rows_and_names_the_anomaly() -> None:
    text = read(DOCS / "interleaving.md")
    trace = section(text, "## The interleaving, statement by statement")
    assert len(re.findall(r"^\| [1-8] \|", trace, re.MULTILINE)) == 8
    anomaly = section(text, "## Which anomaly this is")
    assert "Write skew" in anomaly and "Repeatable Read" in anomaly


def test_what_i_ran_is_my_own_race_output() -> None:
    ran = section(read(DOCS / "interleaving.md"), "## What I ran")
    log = read(LOGS / "race-http-before-after.txt")
    for line in ('Omar -> 201 Created   {"id":"R102","status":"Confirmed","notificationFailed":false}',
                 "DOUBLE BOOKED: the room has two confirmed reservations for the same nights."):
        assert line in ran and line in log


def test_the_four_repairs_table_uses_the_measured_numbers() -> None:
    repairs = section(read(DOCS / "interleaving.md"), "## The four repairs, and what each one cost")
    rows = [line for line in repairs.splitlines() if line.startswith("| ") and not line.startswith(("| Repair", "|---"))]
    assert len(rows) == 4
    names = ["In-process lock", "SELECT ... FOR UPDATE", "Optimistic version", "Exclusion constraint"]
    for name, row in zip(names, rows):
        assert name in row
    pg = read(LOGS / "postgres-repairs.txt")
    waits = [float(value) for value in re.search(r"Omar's wait at FOR UPDATE, \d+ runs \(s\): ([\d., ]+);", pg)
             .group(1).split(", ")]  # type: ignore[union-attr]
    assert f"{statistics.median(waits):.2f} s" in rows[1]
    results = race_results()
    assert f"{results['v5-lock-2']['course']['double_booked']} of {results['v5-lock-2']['course']['rounds']}" in rows[0]
    assert f"0 of {results['v6-pg-2']['course']['rounds']}" in rows[3]


def test_adr_003_has_the_five_sections_the_alternatives_and_their_costs() -> None:
    text = read(DOCS / "adr-003-booking-concurrency.md")
    assert text.startswith("# ADR-003: Protect the booking rule in the database")
    found = re.findall(r"^## (.+)$", text, re.MULTILINE)
    assert found == ["Context", "Decision", "Alternatives considered", "Consequences", "When to revisit"]
    alternatives = section(text, "## Alternatives considered")
    for option in ("**An in-process lock.**", "**`SELECT ... FOR UPDATE` on a guard row.**",
                   "**Optimistic version checking.**", "**Serializable isolation.**"):
        assert option in alternatives
    assert re.search(r"\d+\.\d\d s", alternatives), "the measured wait must be in the ADR"
    consequences = section(text, "## Consequences")
    assert "could not be added" in consequences and "R102" in consequences


# --------------------------------------------------------------------------- the race results


def test_before_double_books_every_round_after_never() -> None:
    results = race_results()
    for key in ("v5-sqlite-1", "v5-sqlite-2", "v5-lock-2", "v6-pg-norule-1", "v6-pg-norule-2"):
        course = results[key]["course"]
        assert course["double_booked"] == course["rounds"] == 20, key
    for key in ("v5-lock-1", "v6-sqlite-1", "v6-sqlite-2", "v6-pg-1", "v6-pg-2"):
        course, burst = results[key]["course"], results[key]["burst"]
        assert course["double_booked"] == 0 and course["one_201_one_409"] == course["rounds"] == 20, key
        assert burst["double_booked"] == 0, key
        # the first PostgreSQL run found deadlock 500s (40P01); the rerun after the retry fix has none
        assert burst["other"] == 0 or key.startswith("v6-pg"), key
    rerun: dict[str, Any] = json.loads(read(LOGS / "race-results-postgres-after-the-retry.json"))
    for key in ("v6-pg-1", "v6-pg-2"):
        burst = rerun[key]["burst"]
        assert burst["double_booked"] == burst["other"] == 0 and burst["one_201_one_409"] == burst["rounds"] == 300
        assert burst["postgres_40P01"] > 0  # deadlocks did happen - and were retried, not answered 500


def test_readme_race_table_is_the_observed_summary() -> None:
    text = read(PRACTICE / "README.md")
    table = section(text, "## Race results")
    for key, value in race_results().items():
        row = next(line for line in table.splitlines() if f"`{key}`" in line)
        course = value["course"]
        assert f"{course['double_booked']} of {course['rounds']}" in row, key
        burst = value["burst"]
        assert f"{burst['double_booked']} / {burst['other']} (of {burst['rounds']})" in row, key


# --------------------------------------------------------------------------- diagrams


def test_sequence_diagrams_name_the_real_code() -> None:
    from hotel_booking.reservations import internal

    fixed = read(DIAGRAMS / "race-fixed-exclusion-constraint.mmd")
    assert internal.NO_OVERLAP_CONSTRAINT in fixed and internal.EXCLUSION_VIOLATION in fixed
    assert "OverlapRejected" in fixed and "SAVEPOINT" in fixed and "nextval" in fixed
    sqlite = read(DIAGRAMS / "race-fixed-sqlite-trigger.mmd")
    assert "reservations_no_overlap_insert" in sqlite and "UPDATE reservation_ids" in sqlite
    assert internal.SQLITE_TRIGGER_REFUSAL in sqlite
    assert "nextval('reservation_ids')" in read(DIAGRAMS / "id-allocation.mmd")
    assert "has_overlap" in read(DIAGRAMS / "race-double-booking.mmd")


def test_svgs_exist_for_every_mermaid_source() -> None:
    sources = sorted(DIAGRAMS.glob("*.mmd"))
    assert {source.stem for source in sources} >= {
        "race-double-booking", "race-fixed-exclusion-constraint", "race-fixed-sqlite-trigger",
        "in-process-lock-two-instances", "guard-row-for-update", "optimistic-version", "id-allocation",
        "four-repairs", "class-diagram"}
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


def test_portfolio_readme_has_a_p09_row() -> None:
    assert re.search(r"^\| P09 \| .+\| \[practices/P09-protect-the-last-seat\]\(practices/P09-protect-the-last-seat\) \|",
                     read(PORTFOLIO / "README.md"), re.MULTILINE)
