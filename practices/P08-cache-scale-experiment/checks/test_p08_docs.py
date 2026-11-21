"""Automated checks for the P08 documents, diagrams and evidence ("Your P08 checklist", activity sheet §10).

The code is checked by hotel-booking's own tests (cache, API, Redis adapter, wiring, measurement
tool, contract, borders). These checks cover what those tests cannot see:

- the as-built module diagram shows exactly the imports the code has (incl. the three new edge files);
- the cache class diagram names only members the code really has, and its "implements" lines hold;
- the search sequence diagram uses the real key, commands and function names;
- every Mermaid source has a rendered SVG and a clean mmdc run;
- design-notes.md has the P08 sections (Cache rule with its one line, After with three lines);
- the project folder matches the course's "finished P08 folder" (with the recorded substitutions);
- docker-compose.yml has the course's cache service; the contract is 1.1.0 with GET /stats;
- cache-experiment.md has the course's sections and its measurement table equals the observed
  experiment summary (no number typed by hand that the run did not produce);
- the behaviour log shows the stale answer without invalidation and the fresh one with it;
- ADR-002 has the five sections and the three course alternatives;
- the evidence index labels every row; every relative link resolves; the root README has a P08 row.

Run from the portfolio root:
    python -m pytest -p no:cacheprovider practices/P08-cache-scale-experiment/checks -v
"""
from __future__ import annotations

import ast
import inspect
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
NODE_OF_MODULE = {"rooms": "rooms", "reservations": "res", "payments": "pay", "notifications": "ntf"}
EDGE_NODES = ("demo", "api", "api_stats", "api_cache", "api_redis")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- diagrams


def mermaid_edges(path: Path) -> list[tuple[str, str, str]]:
    return [match.groups() for line in read(path).splitlines()  # type: ignore[misc]
            if (match := EDGE.match(line))]


def node(module: str) -> str:
    parts = module.split(".")
    if parts[1] in EDGE_NODES:
        return parts[1]
    return NODE_OF_MODULE[parts[1]] + ("_i" if len(parts) > 2 and parts[2] == "internal" else "_c")


def real_edges() -> set[tuple[str, str]]:
    _, edges = build_import_graph(PROJECT / "hotel_booking")
    found = {(node(e.importer), node(e.imported)) for e in edges if e.importer != "hotel_booking"}
    for statement in ast.parse(read(PROJECT / "main.py")).body:
        if isinstance(statement, ast.ImportFrom) and (statement.module or "").startswith("hotel_booking."):
            found.add(("main", node(statement.module or "")))
    return {(a, b) for a, b in found if a != b}


# Imports that later practices added on purpose. The P08 diagram shows the code as built in P08;
# each later edge is listed here, must really exist, and is drawn on that practice's own diagram.
LATER_EDGES = {
    ("api", "ntf_c"),  # P10: GET /stats reads NotificationCounts from the Notifications contract
}


def test_as_built_diagram_shows_exactly_the_real_imports() -> None:
    """P10 change (deliberate): the P08 picture stays as built in P08; the edges added later are
    named in LATER_EDGES, must exist in the code, and are drawn on the P10 as-built diagram."""
    drawn = {(left, right) for left, _, right in mermaid_edges(DIAGRAMS / "module-dependencies.mmd")}
    assert LATER_EDGES <= real_edges()
    assert drawn == real_edges() - LATER_EDGES


def test_the_cache_reaches_no_module_on_the_diagram() -> None:
    drawn = {(left, right) for left, _, right in mermaid_edges(DIAGRAMS / "module-dependencies.mmd")}
    assert {right for left, right in drawn if left in ("api_cache", "api_redis")} <= {"api_cache"}
    assert {left for left, right in drawn if right in ("api", "api_stats", "api_cache", "api_redis")} <= {
        "main", "api", "api_redis"}


CLASS_HEADER = re.compile(r"^\s*class (\w+) \{")
MEMBER = re.compile(r"^\s*[+-](\w+)")
IMPLEMENTS = re.compile(r"^\s*(\w+) \.\.\|> (\w+)")


def class_diagram() -> dict[str, list[str]]:
    boxes: dict[str, list[str]] = {}
    current = None
    for line in read(DIAGRAMS / "cache-classes.mmd").splitlines():
        if header := CLASS_HEADER.match(line):
            current = header.group(1)
            boxes[current] = []
        elif line.strip() == "}":
            current = None
        elif current and (member := MEMBER.match(line)):
            boxes[current].append(member.group(1))
    return boxes


def code_class(name: str) -> type:
    import hotel_booking.api_cache
    import hotel_booking.api_redis
    import hotel_booking.api_stats
    import hotel_booking.reservations
    for module in (hotel_booking.api_cache, hotel_booking.api_redis, hotel_booking.api_stats, hotel_booking.reservations):
        if hasattr(module, name):
            found: type = getattr(module, name)
            return found
    raise AssertionError(f"{name} is drawn but not in the code")


def test_cache_class_diagram_members_exist_in_the_code() -> None:
    for name, members in class_diagram().items():
        cls = code_class(name)
        source = inspect.getsource(cls)
        for member in members:
            assert hasattr(cls, member) or f"self.{member}" in source, f"{name}.{member}"


def test_cache_class_diagram_implements_lines_hold() -> None:
    lines = [IMPLEMENTS.match(line) for line in read(DIAGRAMS / "cache-classes.mmd").splitlines()]
    pairs = [(m.group(1), m.group(2)) for m in lines if m]
    assert len(pairs) == 3
    for concrete, promise in pairs:
        wanted = {name for name in vars(code_class(promise)) if not name.startswith("_")}
        assert wanted <= set(dir(code_class(concrete))), (concrete, promise)


def test_search_sequence_uses_the_real_key_commands_and_names() -> None:
    text = read(DIAGRAMS / "search-through-cache.mmd")
    api = read(PROJECT / "hotel_booking" / "api.py") + read(PROJECT / "hotel_booking" / "api_cache.py")
    redis = read(PROJECT / "hotel_booking" / "api_redis.py")
    for name in ("search_free_rooms", "in_unit_of_work", "CountingReservationStore", "AvailabilityCache",
                 "availability:version", "availability:v0:2026-11-12:2026-11-14", "EX 30", "INCR", "X-Cache"):
        assert name in text, name
    for name in ("search_free_rooms", "in_unit_of_work", "invalidate_cache", "VERSION_KEY = \"availability:version\""):
        assert name in api, name
    assert '"SET", key, value, "EX"' in redis and '"INCR", key' in redis and '"GET", key' in redis


def test_svgs_exist_for_every_mermaid_source() -> None:
    sources = sorted(DIAGRAMS.glob("*.mmd"))
    assert {source.stem for source in sources} >= {"module-dependencies", "search-through-cache", "stale-result",
                                                   "cache-classes", "deployment-and-scale", "bottleneck-moves"}
    for source in sources:
        svg = source.with_suffix(".svg")
        assert svg.exists() and svg.stat().st_size > 1000, f"{svg.name} missing - run mmdc"
        assert svg.stat().st_mtime >= source.stat().st_mtime - 1, f"{svg.name} is older than its source"
    log = read(LOGS / "mmdc.txt")
    assert log.count("exit 0") == len(sources) and "Error" not in log


# --------------------------------------------------------------------------- the project


def test_design_notes_have_the_p08_sections() -> None:
    text = read(DOCS / "design-notes.md")
    p08 = text[text.index("# P08 design notes"):]
    found = re.findall(r"^## (.+)$", p08, re.MULTILINE)
    for section in ["Cache rule", "After"]:
        assert section in found, f"design-notes.md P08: missing ## {section}"
    rule = p08[p08.index("## Cache rule"):].split("\n\n")[1]
    assert rule.strip() == "Booking never reads the cache."
    after = p08[p08.index("## After"):p08.index("## Decisions made while building")]
    assert len(re.findall(r"^- ", after, re.MULTILINE)) == 3


def test_project_folder_matches_the_finished_p08_folder() -> None:
    """The sheet's list; substitutions: db/init.sql -> db/postgres/init.sql (P07), + api_stats/api_redis."""
    expected = [
        "db/postgres/init.sql", "docs/requests/maya-r7.json", "docs/requests/omar-r7.json", "docs/requests/omar-r8.json",
        "docs/adr-001-modular-monolith.md", "docs/adr-002-cache-availability.md", "docs/api-check.md",
        "docs/cache-experiment.md", "docs/capacity.md", "docs/contexts.md", "docs/design-notes.md",
        "docs/diagrams.drawio", "docs/l04-notes.md", "docs/openapi.yaml", "docs/quality-scenarios.md",
        "docs/requirements.md", "hotel_booking/__init__.py", "hotel_booking/api_cache.py", "hotel_booking/api.py",
        "hotel_booking/api_stats.py", "hotel_booking/api_redis.py", "tools/measure.py",
        "docker-compose.yml", "main.py", "pyproject.toml", "requirements.txt", "test_api.py", "test_booking_service.py",
    ]
    missing = [path for path in expected if not (PROJECT / path).exists()]
    assert not missing, missing
    assert not list(PROJECT.glob("*.sqlite3")), "a local database file must not be handed in"


def test_docker_compose_has_the_course_cache_service() -> None:
    compose = yaml.safe_load(read(PROJECT / "docker-compose.yml"))
    cache = compose["services"]["cache"]
    assert cache["image"] == "redis:8" and cache["ports"] == ["6379:6379"]
    assert "volumes" not in cache  # copies only: nothing that must survive
    assert compose["services"]["db"]["image"] == "postgres:18"
    assert read(PROJECT / "docker-compose.yml").startswith("# The hotel booking app's database and cache")


def test_contract_is_1_1_0_with_get_stats() -> None:
    """P09 change (deliberate): P09 raised the contract to 1.2.0 (a promise added, no shape changed),
    so this P08 check now asks for "1.1.0 or a later 1.x" - GET /stats must still be there."""
    contract = yaml.safe_load(read(DOCS / "openapi.yaml"))
    major, minor, _ = (int(part) for part in contract["info"]["version"].split("."))
    assert major == 1 and minor >= 1
    assert contract["paths"]["/stats"]["get"]["operationId"] == "getStats"
    stats = contract["components"]["schemas"]["Stats"]
    assert {"searches", "databaseQueries", "cacheHits", "cacheMisses"} <= set(stats["required"])


def test_capacity_to_measure_later_is_answered() -> None:
    later = read(DOCS / "capacity.md").split("## To measure later")[1]
    assert later.count("Measured in P08") == 2


# --------------------------------------------------------------------------- the experiment


def summary_rows() -> dict[tuple[str, str], list[str]]:
    rows = {}
    for line in read(LOGS / "experiment-summary.md").splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 11 and cells[0] in ("course", "rooms40", "clients8"):
            rows[(cells[0], cells[1])] = cells
    return rows


def median(cell: str) -> str:
    return cell.split(" ")[0]


def test_cache_experiment_has_the_course_sections() -> None:
    text = read(DOCS / "cache-experiment.md")
    for heading in ["## Measurements", "## Stale result (Step 5, before invalidation)", "## After invalidation (Step 6)",
                    "## Hot key and the next bottleneck (Step 7)"]:
        assert heading in text, heading
    assert "| Run | Searches | Database queries | Cache hits | Average | p95 |" in text


def test_the_measurement_table_is_the_observed_summary() -> None:
    text = read(DOCS / "cache-experiment.md")
    rows = summary_rows()
    off, redis, memory = rows[("course", "off")], rows[("course", "redis")], rows[("course", "memory")]
    assert off[2] == redis[2] == memory[2] == "5"  # five runs each
    assert f"| No cache | 1,000 | 2,000 | 0 | {median(off[5])} ms | {median(off[6])} ms |" in text
    assert f"| Cache-aside, TTL 30 s (Redis) | 1,000 | 2 | 999 | {median(redis[5])} ms | {median(redis[6])} ms |" in text
    assert f"| 1,000 | 2 | 999 | {median(memory[5])} ms | {median(memory[6])} ms |" in text
    assert (off[3], redis[3], memory[3]) == ("2000", "2", "2") and redis[4] == "999 / 1"


def test_the_scale_table_is_the_observed_summary() -> None:
    text = read(DOCS / "cache-experiment.md")
    rows = summary_rows()
    for (scenario, cache), cells in rows.items():
        if scenario == "course":
            continue
        cell = f"| {median(cells[5])} ({cells[5].split('(')[1].replace('-', '–')} | {median(cells[6])} ({cells[6].split('(')[1].replace('-', '–')} |"
        assert cell in text, (scenario, cache, cell)


def test_every_run_has_the_expected_counts() -> None:
    raw = read(LOGS / "experiment-raw.txt")
    no_cache = '{"searches":1000,"databaseQueries":2000,"cacheHits":0,"cacheMisses":0,"cacheErrors":0}'
    cached = '{"searches":1000,"databaseQueries":2,"cacheHits":999,"cacheMisses":1,"cacheErrors":0}'
    assert raw.count(f"GET /stats difference: {no_cache}") == 5 + 3  # course + clients8, cache off
    assert raw.count(f"GET /stats difference: {cached}") == 5 + 5  # course redis + memory
    assert raw.count('"databaseQueries":40000') == 3 and raw.count('"databaseQueries":40,') == 3


def test_behaviour_log_shows_stale_then_fresh() -> None:
    log = read(LOGS / "cache-behaviour.txt")
    both, only_r8 = '"rooms":[{"number":"R7","type":"Standard"},{"number":"R8","type":"Deluxe"}]', '"rooms":[{"number":"R8","type":"Deluxe"}]'
    stale = log[log.index("C  Step 5"):log.index("D  Step 6")]
    fresh = log[log.index("D  Step 6"):log.index("E  Step 7")]
    assert re.search(re.escape(both) + r'.*\n200  X-Cache: miss\n.*\n.*R101.*\n201\n.*\n.*' + re.escape(both)
                     + r'.*\n200  X-Cache: hit\n.*\n.*Unavailable.*\n409', stale)
    assert re.search(re.escape(only_r8) + r'.*\n200  X-Cache: miss', fresh) and "Unavailable" in fresh
    assert log.rstrip().endswith("exit 0")


def test_adr_002_has_the_five_sections_and_the_course_alternatives() -> None:
    text = read(DOCS / "adr-002-cache-availability.md")
    assert text.startswith("# ADR-002: Cache the free-room search in Redis")
    found = re.findall(r"^## (.+)$", text, re.MULTILINE)
    assert found == ["Context", "Decision", "Alternatives considered", "Consequences", "Revisit when"]
    alternatives = text[text.index("## Alternatives considered"):text.index("## Consequences")]
    for option in ("**No cache.**", "**TTL only.**", "**Invalidation only (no TTL).**"):
        assert option in alternatives
    assert "2 database queries instead of 2,000" in text


def test_evidence_index_labels_every_row() -> None:
    rows = [line for line in read(PRACTICE / "evidence" / "Index.md").splitlines() if re.match(r"^\| E\d+ ", line)]
    assert len(rows) >= 15
    for row in rows:
        assert re.search(r"\| \*\*(Observed|Simulated|Proposed)\*\* \|", row), row


# --------------------------------------------------------------------------- links and the index


LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def markdown_files() -> list[Path]:
    return sorted([*PRACTICE.rglob("*.md"), *DOCS.glob("*.md"), PROJECT / "README.md", PORTFOLIO / "README.md"])


@pytest.mark.parametrize("path", markdown_files(), ids=lambda path: str(path.relative_to(PORTFOLIO)))
def test_every_relative_link_resolves(path: Path) -> None:
    for target in LINK.findall(read(path)):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        assert (path.parent / target).exists(), f"{path.name}: broken link {target}"


def test_portfolio_readme_has_a_p08_row() -> None:
    assert re.search(r"^\| P08 \| .+\| \[practices/P08-cache-scale-experiment\]\(practices/P08-cache-scale-experiment\) \|",
                     read(PORTFOLIO / "README.md"), re.MULTILINE)
