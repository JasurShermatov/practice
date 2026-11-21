"""Automated checks for the P07 documents, diagrams and evidence ("Your P07 checklist", activity sheet §10).

The code is checked by hotel-booking's own tests (API, contract, SQL store, capacity). These checks
cover what those tests cannot see:

- the as-built module diagram shows exactly the imports the code has (same ast graph as
  tests/test_architecture.py, plus main.py), now including the HTTP edge;
- every Mermaid source has a rendered SVG;
- design-notes.md has the P07 sections the sheet asks for (API decisions, API tests, After);
- the project folder matches the course's "finished P07 folder" (with the recorded substitutions);
- api-check.md has the course's seven requests with exactly the course's answers, uses request
  files that exist, and its SQLite column is backed by the observed run log;
- the course's request bodies are byte-for-byte the activity sheet's;
- docker-compose.yml is the sheet's service (postgres:18, user/db/password hotel, 5432, init.sql
  mounted, data volume) with the portfolio's schema path;
- the contract has the course's three operations and five error titles;
- capacity.md has five assumptions, five results and the two P08 measurements (course checklist);
- every relative link in the P07 docs and the project docs resolves; the root README has a P07 row.

Run from the portfolio root:
    python -m pytest -p no:cacheprovider practices/P07-capacity-api-design/checks -v
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

PRACTICE = Path(__file__).resolve().parents[1]
PORTFOLIO = PRACTICE.parents[1]
PROJECT = PORTFOLIO / "hotel-booking"
DOCS = PROJECT / "docs"
DIAGRAMS = PRACTICE / "diagrams"
LOGS = PRACTICE / "evidence" / "logs"

sys.path.insert(0, str(PROJECT))
from tests.test_architecture import build_import_graph  # noqa: E402

yaml = pytest.importorskip("yaml")

EDGE = re.compile(r"^\s*(\w+)\s+-\.?->?\|([^|]+)\|\s+(\w+)\s*$")


# --------------------------------------------------------------------------- diagrams


def mermaid_edges(path: Path) -> list[tuple[str, str, str]]:
    return [match.groups() for line in path.read_text(encoding="utf-8").splitlines()  # type: ignore[misc]
            if (match := EDGE.match(line))]


NODE_OF_MODULE = {"rooms": "rooms", "reservations": "res", "payments": "pay", "notifications": "ntf"}


def node(module: str) -> str:
    parts = module.split(".")
    if parts[1] in ("demo", "api"):
        return parts[1]
    return NODE_OF_MODULE[parts[1]] + ("_i" if len(parts) > 2 and parts[2] == "internal" else "_c")


def real_edges() -> set[tuple[str, str]]:
    _, edges = build_import_graph(PROJECT / "hotel_booking")
    found = {(node(e.importer), node(e.imported)) for e in edges if e.importer != "hotel_booking"}
    for statement in ast.parse((PROJECT / "main.py").read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.ImportFrom) and (statement.module or "").startswith("hotel_booking."):
            found.add(("main", node(statement.module or "")))
    return {(a, b) for a, b in found if a != b}


def test_as_built_diagram_shows_exactly_the_real_imports() -> None:
    drawn = {(left, right) for left, _, right in mermaid_edges(DIAGRAMS / "module-dependencies.mmd")}
    assert drawn == real_edges()


def test_the_api_reaches_only_contracts_on_the_diagram() -> None:
    drawn = {(left, right) for left, _, right in mermaid_edges(DIAGRAMS / "module-dependencies.mmd")}
    assert {right for left, right in drawn if left == "api"} == {"res_c", "rooms_c"}
    assert not {left for left, right in drawn if right == "api"} - {"main"}


def test_svgs_exist_for_every_mermaid_source() -> None:
    sources = sorted(DIAGRAMS.glob("*.mmd"))
    assert {source.stem for source in sources} >= {"class-diagram", "module-dependencies", "cancel-sequence",
                                                   "book-request-flow", "deployment"}
    for source in sources:
        svg = source.with_suffix(".svg")
        assert svg.exists() and svg.stat().st_size > 1000, f"{svg.name} missing - run mmdc"
    log = (LOGS / "mmdc.txt").read_text(encoding="utf-8")
    assert log.count("exit 0") == len(sources)


def test_cancel_sequence_follows_the_code() -> None:
    """The sequence diagram names the real classes and SQL of the cancel path."""
    text = (DIAGRAMS / "cancel-sequence.mmd").read_text(encoding="utf-8")
    store = (PROJECT / "hotel_booking" / "reservations" / "internal.py").read_text(encoding="utf-8")
    for name in ("SqlReservationStore", "BookingService", "unit_of_work", "save_changes", "in_unit_of_work"):
        assert name in text
    assert "UPDATE reservations SET status = ? WHERE id = ?" in store
    assert "SELECT ... FROM reservations WHERE id = ?" in text


# --------------------------------------------------------------------------- documents


def test_design_notes_have_the_p07_sections() -> None:
    text = (DOCS / "design-notes.md").read_text(encoding="utf-8")
    p07 = text[text.index("# P07 design notes"):]
    found = re.findall(r"^## (.+)$", p07, re.MULTILINE)
    for section in ["API decisions", "API tests", "After"]:
        assert section in found, f"design-notes.md P07: missing ## {section}"
    api_tests = p07[p07.index("## API tests"):p07.index("## After")]
    assert len(re.findall(r"^\| (Search|Book, then book again|Wrong dates|Cancel twice) \|", api_tests, re.MULTILINE)) == 4


def test_project_folder_matches_the_finished_p07_folder() -> None:
    """The sheet's list; substitutions: db/init.sql -> db/postgres/init.sql (task brief)."""
    expected = [
        "db/postgres/init.sql",
        "docs/requests/maya-r7.json", "docs/requests/omar-r7.json", "docs/requests/omar-r8.json",
        "docs/adr-001-modular-monolith.md", "docs/api-check.md", "docs/capacity.md", "docs/contexts.md",
        "docs/design-notes.md", "docs/diagrams.drawio", "docs/l04-notes.md", "docs/openapi.yaml",
        "docs/quality-scenarios.md", "docs/requirements.md",
        "hotel_booking/__init__.py", "hotel_booking/api.py",
        "hotel_booking/notifications/__init__.py", "hotel_booking/notifications/internal.py",
        "hotel_booking/payments/__init__.py", "hotel_booking/payments/internal.py",
        "hotel_booking/reservations/__init__.py", "hotel_booking/reservations/booking.py",
        "hotel_booking/reservations/domain.py", "hotel_booking/reservations/internal.py",
        "hotel_booking/rooms/__init__.py", "hotel_booking/rooms/catalog.py", "hotel_booking/rooms/internal.py",
        "docker-compose.yml", "main.py", "pyproject.toml", "requirements.txt", "test_api.py",
        "test_booking_service.py",
    ]
    missing = [path for path in expected if not (PROJECT / path).exists()]
    assert not missing, missing
    assert not (PROJECT / "hotel.sqlite3").exists(), "a local database file must not be handed in"


COURSE_BODIES = {
    "maya-r7.json": '{"guestName":"Maya","guestEmail":"maya@example.com","room":"R7","checkIn":"2026-11-12","checkOut":"2026-11-14"}',
    "omar-r7.json": '{"guestName":"Omar","guestEmail":"omar@example.com","room":"R7","checkIn":"2026-11-13","checkOut":"2026-11-15"}',
    "omar-r8.json": '{"guestName":"Omar","guestEmail":"omar@example.com","room":"R8","checkIn":"2026-11-15","checkOut":"2026-11-15"}',
}


@pytest.mark.parametrize("name", sorted(COURSE_BODIES))
def test_course_request_bodies_are_exactly_the_sheets(name: str) -> None:
    assert (DOCS / "requests" / name).read_text(encoding="utf-8").strip() == COURSE_BODIES[name]


def test_every_request_file_is_a_json_object() -> None:
    for path in (DOCS / "requests").glob("*.json"):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict), path.name


COURSE_ANSWERS = [  # "The seven answers, in every language" (activity sheet §9), in order
    ('{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R7","type":"Standard"},{"number":"R8","type":"Deluxe"}],"next":null}', "200"),
    ('{"id":"R101","status":"Confirmed","notificationFailed":false}', "201"),
    ('{"title":"Unavailable","status":409,"detail":"The room is booked for at least one night of this stay."}', "409"),
    ('{"title":"InvalidDates","status":400,"detail":"checkOut must be after checkIn."}', "400"),
    ('{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R8","type":"Deluxe"}],"next":null}', "200"),
    ("", "204"),
    ('{"title":"NotFound","status":404,"detail":"There is no confirmed reservation R101."}', "404"),
]


def api_check_sections() -> dict[int, str]:
    text = (DOCS / "api-check.md").read_text(encoding="utf-8")
    parts = re.split(r"^## (\d+)\. ", text, flags=re.MULTILINE)
    return {int(number): body for number, body in zip(parts[1::2], parts[2::2])}


def expected_block(section: str) -> list[str]:
    block = re.findall(r"```text\n(.*?)```", section[section.index("Expected:"):], re.DOTALL)[0]
    return [line for line in block.splitlines() if line.strip()]


@pytest.mark.parametrize("number", range(1, 8))
def test_api_check_has_the_course_seven_answers(number: int) -> None:
    body, status = COURSE_ANSWERS[number - 1]
    assert expected_block(api_check_sections()[number]) == ([body, status] if body else [status])


def test_api_check_restart_and_table() -> None:
    sections = api_check_sections()
    assert "start it again" in sections[9].splitlines()[0]
    assert expected_block(sections[10])[0].endswith('"rooms":[{"number":"R8","type":"Deluxe"}],"next":null}')
    assert expected_block(sections[11]) == ["R101 | Maya | R7 | 2026-11-12 | 2026-11-14 | Cancelled",
                                            "R102 | Maya | R7 | 2026-11-12 | 2026-11-14 | Confirmed"]


def test_api_check_uses_request_files_that_exist() -> None:
    text = (DOCS / "api-check.md").read_text(encoding="utf-8")
    used = set(re.findall(r'--data "@docs/requests/([\w-]+\.json)"', text))
    assert used and all((DOCS / "requests" / name).exists() for name in used)
    assert used == {path.name for path in (DOCS / "requests").glob("*.json")}


def test_api_check_ticks_are_backed_by_the_observed_run() -> None:
    sections = api_check_sections()
    with_command = [number for number, body in sections.items() if "Expected:" in body]
    log = (LOGS / "api-check-sqlite.txt").read_text(encoding="utf-8")
    assert f"Result: {len(with_command)} of {len(with_command)} answers exactly as expected, 1 restart." in log
    assert log.count("✓ matches Expected") == len(with_command) and "✗" not in log
    for number in with_command:
        assert "SQLite: ✓" in sections[number], number
        assert "PostgreSQL: ☐" in sections[number], number  # not claimed: to do on the Mac


def test_docker_compose_is_the_sheets_service() -> None:
    compose = yaml.safe_load((PROJECT / "docker-compose.yml").read_text(encoding="utf-8"))
    db = compose["services"]["db"]
    assert db["image"] == "postgres:18"
    assert db["environment"] == {"POSTGRES_DB": "hotel", "POSTGRES_USER": "hotel", "POSTGRES_PASSWORD": "hotel"}
    assert db["ports"] == ["5432:5432"]
    assert db["volumes"] == ["./db/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro",
                             "hotel-data:/var/lib/postgresql"]
    assert "hotel-data" in compose["volumes"]


def test_init_sql_has_the_two_tables_and_the_rules() -> None:
    sql = (PROJECT / "db" / "postgres" / "init.sql").read_text(encoding="utf-8")
    assert re.search(r"CREATE TABLE rooms \(\s+number text PRIMARY KEY", sql)
    assert "id          text PRIMARY KEY" in sql
    assert "CHECK (status IN ('Confirmed', 'Cancelled'))" in sql and "CHECK (check_out > check_in)" in sql
    assert "REFERENCES" not in sql.upper().replace("-- ", "")  # no foreign key between the modules' tables
    assert "INSERT INTO rooms (number, type) VALUES ('R7', 'Standard'), ('R8', 'Deluxe');" in sql


def test_contract_has_the_course_operations_and_titles() -> None:
    contract = yaml.safe_load((DOCS / "openapi.yaml").read_text(encoding="utf-8"))
    operations = {(method.upper(), path) for path, item in contract["paths"].items() for method in item}
    assert {("GET", "/rooms/availability"), ("POST", "/reservations"), ("DELETE", "/reservations/{id}")} <= operations
    titles = contract["components"]["schemas"]["Problem"]["properties"]["title"]["enum"]
    assert {"Unavailable", "InvalidDates", "UnknownRoom", "InvalidRequest", "NotFound"} <= set(titles)


def test_capacity_has_the_course_checklist_parts() -> None:
    text = (DOCS / "capacity.md").read_text(encoding="utf-8")
    assumptions = text[text.index("## Assumptions"):text.index("Added in this portfolio")]
    assert len(re.findall(r"^\| (?!Assumption|---)", assumptions, re.MULTILINE)) >= 5
    results = text[text.index("## Results"):text.index("Further results")]
    assert len(re.findall(r"^\| (?!Number|---)", results, re.MULTILINE)) == 5
    later = text[text.index("## To measure later"):]
    assert later.count("P08") >= 2


# --------------------------------------------------------------------------- links and the index


LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def markdown_files() -> list[Path]:
    return sorted([*PRACTICE.rglob("*.md"), *DOCS.glob("*.md"), PROJECT / "README.md", PORTFOLIO / "README.md"])


@pytest.mark.parametrize("path", markdown_files(), ids=lambda p: str(p.relative_to(PORTFOLIO)))
def test_every_relative_link_resolves(path: Path) -> None:
    broken = []
    for target in LINK.findall(path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if not (path.parent / target).exists():
            broken.append(target)
    assert not broken, f"{path.relative_to(PORTFOLIO)}: broken links {broken}"


def test_portfolio_readme_has_a_p07_row() -> None:
    text = (PORTFOLIO / "README.md").read_text(encoding="utf-8")
    assert re.search(r"^\| P07 \| .*\(practices/P07-capacity-api-design\)", text, re.MULTILINE)
