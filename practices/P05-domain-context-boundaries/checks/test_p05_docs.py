"""Automated checks for the P05 design documents (Step 8: "check every file against the list").

P05 changes no application code, so these tests check the *documents*: the counts the activity
sheet asks for (18 words, 4 contexts, 8 rule cards, 3 borders, 6 scenarios with 7 lines), that the
context map has the required shape in both the Mermaid source and the draw.io page, and that
every code name in the Words table really exists in ``hotel-booking/hotel_booking``.

The code is only *parsed* with ``ast`` (never imported), so running these checks writes nothing
into the hotel-booking folder.

Run from the portfolio root:
    python -m pytest -p no:cacheprovider practices/P05-domain-context-boundaries/checks -v
"""
from __future__ import annotations

import ast
import re
import xml.etree.ElementTree as ET
from functools import cache
from pathlib import Path

import pytest

PRACTICE = Path(__file__).resolve().parents[1]
PORTFOLIO = PRACTICE.parents[1]
CODE = PORTFOLIO / "hotel-booking" / "hotel_booking"

CONTEXTS_MD = PRACTICE / "docs" / "contexts.md"
SCENARIOS_MD = PRACTICE / "docs" / "quality-scenarios.md"
MAP_MMD = PRACTICE / "diagrams" / "context-map.mmd"
MAP_DRAWIO = PRACTICE / "diagrams" / "context-map.drawio"

CONTEXTS = ("Rooms", "Reservations", "Payments", "Notifications")
EXPECTED_PLACEMENT = {
    "Rooms": {"Room", "Room type", "Nightly price", "Out of service"},
    "Reservations": {
        "Guest", "Stay", "Reservation", "Confirmed", "Cancelled", "Book", "Cancel", "Free rooms",
    },
    "Payments": {"Deposit", "Paid", "Declined"},
    "Notifications": {"Confirmation message", "Sent", "Failed"},
}
EXPECTED_OWNERS = {
    1: "Reservations", 2: "Reservations", 3: "Reservations", 4: "Rooms",
    5: "Rooms", 6: "Payments", 7: "Payments", 8: "Notifications",
}
SCENARIO_PARTS = [
    "Source", "Stimulus", "Environment", "Artifact", "Response", "Measure", "Checked in",
]


# --------------------------------------------------------------------------- Markdown helpers

def sections(text: str, level: int) -> dict[str, str]:
    """Map each heading of exactly ``level`` (#'s) to the text up to the next heading of that level or higher."""
    pattern = re.compile(rf"^{'#' * level} (.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    result: dict[str, str] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.end():end]
        stop = re.search(rf"^#{{1,{level}}} ", body, re.MULTILINE)
        result[match.group(1).strip()] = body[: stop.start()] if stop else body
    return result


def tables(text: str) -> list[list[list[str]]]:
    """All Markdown tables in ``text`` as rows of cells, header row first, separator row removed."""
    found: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in [*text.splitlines(), ""]:
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                current.append(cells)
        elif current:
            found.append(current)
            current = []
    return found


@cache
def contexts_md() -> str:
    return CONTEXTS_MD.read_text(encoding="utf-8")


def words_table() -> list[list[str]]:
    return tables(sections(contexts_md(), 2)["Words"])[0]


# --------------------------------------------------------------------------- code index (ast)

@cache
def code_index() -> dict[str, set[str]]:
    """Every class under hotel_booking/ (any sub-package) with the names of its members."""
    index: dict[str, set[str]] = {}
    for path in CODE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            members = index.setdefault(node.name, set())
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    members.add(item.name)
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    members.add(item.target.id)
                elif isinstance(item, ast.Assign):
                    members.update(t.id for t in item.targets if isinstance(t, ast.Name))
    return index


def code_names() -> list[str]:
    names: list[str] = []
    for row in words_table()[1:]:
        names.extend(re.findall(r"`([A-Za-z_][\w.]*)`", row[2]))
    return names


# --------------------------------------------------------------------------- Step 2: Words

def test_words_table_has_18_rows_each_with_a_meaning_and_a_code_name() -> None:
    header, *rows = words_table()
    assert header == ["Word", "Meaning here", "Name in our code"]
    assert len(rows) == 18
    words = [row[0] for row in rows]
    assert len(set(words)) == 18, "a word appears twice"
    for word, meaning, code in rows:
        assert len(meaning.split()) >= 4, f"{word}: meaning too short"
        assert code, f"{word}: no code name"
        assert code == "not in code yet" or "`" in code, f"{word}: code name must be `Name` or 'not in code yet'"
    assert set(words) == set().union(*EXPECTED_PLACEMENT.values())


@pytest.mark.parametrize("name", code_names())
def test_every_code_name_in_the_words_table_exists_in_the_code(name: str) -> None:
    class_name, _, member = name.partition(".")
    index = code_index()
    assert class_name in index, f"class {class_name} not found under {CODE}"
    if member:
        assert member in index[class_name], f"{class_name} has no member {member}"


# --------------------------------------------------------------------------- Step 3 + 5 + 7: contexts

@pytest.mark.parametrize("context", CONTEXTS)
def test_each_context_section_has_job_words_rules_needs_and_tells(context: str) -> None:
    body = sections(contexts_md(), 2)[next(h for h in sections(contexts_md(), 2) if h.startswith(context))]
    assert re.search(r"^Job: \S", body, re.MULTILINE)
    assert re.search(r"^Rules this context owns:\n- ", body, re.MULTILINE)
    assert re.search(r"^Needs from other contexts: \S", body, re.MULTILINE)
    assert re.search(r"^Tells other contexts: \S", body, re.MULTILINE)
    header, *rows = tables(body)[0]
    assert header == ["Word", "Meaning here"]
    assert {row[0] for row in rows} == EXPECTED_PLACEMENT[context]


def test_all_18_words_are_placed_in_exactly_one_context() -> None:
    all_sections = sections(contexts_md(), 2)
    placed: list[str] = []
    for context in CONTEXTS:
        heading = next(h for h in all_sections if h.startswith(context))
        placed.extend(row[0] for row in tables(all_sections[heading])[0][1:])
    assert len(placed) == 18 == len(set(placed))
    assert [len(EXPECTED_PLACEMENT[c]) for c in CONTEXTS] == [4, 8, 3, 3]


# --------------------------------------------------------------------------- Step 4

def test_same_word_table_has_room_status_and_cancel_and_the_danger_sentence() -> None:
    body = sections(contexts_md(), 2)["Same word, different meaning"]
    header, *rows = tables(body)[0]
    assert header == ["Word", *CONTEXTS]
    assert {"Room", "Status", "Cancel"} <= {row[0] for row in rows}
    assert all(all(cell for cell in row) for row in rows)
    sentence = body.split("What would go wrong with one shared status:")[1].split("\n\n")[0]
    for must in ("Maya", "R7", "Failed", "R6"):
        assert must in sentence


# --------------------------------------------------------------------------- Step 5

def test_rule_owners_eight_cards_one_owner_each_with_a_reason() -> None:
    body = sections(contexts_md(), 2)["Rule owners"]
    header, *rows = tables(body)[0]
    assert header == ["Card", "Rule", "Owner", "Why this owner"]
    assert [int(row[0]) for row in rows] == list(range(1, 9))
    for card, rule, owner, why in rows:
        assert owner == EXPECTED_OWNERS[int(card)], f"card {card}"
        assert len(why.split()) >= 6, f"card {card}: reason too short"


def test_every_rule_is_listed_under_its_owner_and_nowhere_else() -> None:
    all_sections = sections(contexts_md(), 2)
    rows = tables(all_sections["Rule owners"])[0][1:]
    for card, rule, owner, _ in rows:
        for context in CONTEXTS:
            heading = next(h for h in all_sections if h.startswith(context))
            rules_block = all_sections[heading].split("Rules this context owns:")[1].split("\n\n")[0]
            listed = re.search(rf"\(card {card}\b", rules_block) is not None and rule in rules_block
            assert listed == (context == owner), f"card {card} under {context}"


# --------------------------------------------------------------------------- Step 6: context map

def mermaid_edges(source: str) -> list[tuple[str, str, str, str]]:
    """(from, arrow, label, to) for each edge line such as ``a -->|"label"| b``."""
    pattern = re.compile(r'^\s*(\w+)\s+(-->|-\.->)\|"([^"]+)"\|\s+(\w+)\s*$', re.MULTILINE)
    return pattern.findall(source)


def test_context_map_has_4_boxes_and_3_labelled_arrows_from_reservations() -> None:
    source = MAP_MMD.read_text(encoding="utf-8")
    nodes = set(re.findall(r'^\s*(\w+)\["<b>', source, re.MULTILINE))
    assert nodes == {"rooms", "payments", "reservations", "notifications"}
    edges = mermaid_edges(source)
    assert len(edges) == 3
    assert all(start == "reservations" for start, *_ in edges)
    assert sorted(arrow for _, arrow, _, _ in edges) == ["-->", "-->", "-.->"]
    for _, arrow, label, target in edges:
        assert label.startswith("Announces:" if arrow == "-.->" else "Asks:")
        if arrow == "-.->":
            assert target == "notifications" and "ReservationConfirmed" in label
    assert re.search(r"^\s*class reservations owner$", source, re.MULTILINE)
    assert "fill:#c8e6c9" in source  # green


def test_contexts_md_embeds_the_same_map_as_the_mermaid_source() -> None:
    body = sections(contexts_md(), 2)["Context map"]
    embedded = body.split("```mermaid\n")[1].split("```")[0].strip()
    source = MAP_MMD.read_text(encoding="utf-8").split("---", 2)[2].strip()
    assert embedded == source


def test_drawio_page_context_map_has_the_required_shape() -> None:
    root = ET.parse(MAP_DRAWIO).getroot()
    pages = root.findall("diagram")
    assert [page.get("name") for page in pages] == ["Context map"]
    cells = pages[0].iter("mxCell")
    boxes = {c.get("id"): c for c in cells if c.get("vertex") == "1" and c.get("id", "").startswith("ctx-")}
    assert len(boxes) == 4
    green = [cid for cid, c in boxes.items() if "fillColor=#C8E6C9" in c.get("style", "")]
    assert green == ["ctx-reservations"]
    edges = [c for c in pages[0].iter("mxCell") if c.get("edge") == "1"]
    assert len(edges) == 3
    assert all(e.get("source") == "ctx-reservations" for e in edges)
    dotted = [e for e in edges if "dashed=1" in e.get("style", "")]
    assert len(dotted) == 1 and dotted[0].get("target") == "ctx-notifications"
    assert "#2E7D32" in dotted[0].get("style", "")
    for edge in edges:
        assert edge.get("value", "").startswith("Announces:" if edge in dotted else "Asks:")


# --------------------------------------------------------------------------- Step 7: borders

def test_between_contexts_has_one_subsection_per_arrow_with_fields() -> None:
    body = sections(contexts_md(), 2)["Between contexts"]
    borders = sections(body, 3)
    assert len(borders) == 3
    targets = {heading.split("→")[1].split(":")[0].strip() for heading in borders}
    assert targets == {"Rooms", "Payments", "Notifications"}
    assert all(heading.startswith("Reservations →") for heading in borders)
    for heading, text in borders.items():
        assert "Sent when:" in text, heading
        assert "Never crosses:" in text, heading
        assert re.search(r"^- \w+", text, re.MULTILINE), f"{heading}: no fields listed"
    event = next(text for heading, text in borders.items() if "ReservationConfirmed" in heading)
    for field in ("reservationId: R101", "guestEmail: maya@example.com", "roomNumber: R7",
                  "checkIn: 2026-11-12", "checkOut: 2026-11-14"):
        assert field in event


# --------------------------------------------------------------------------- Step 1: scenarios

def test_six_quality_scenarios_each_with_seven_lines_and_a_numeric_measure() -> None:
    text = SCENARIOS_MD.read_text(encoding="utf-8")
    all_sections = sections(text, 2)
    stakeholders = tables(all_sections["Stakeholders"])[0]
    assert len(stakeholders) == 1 + 5
    scenario_headings = sorted(h for h in all_sections if re.match(r"S[1-6] · ", h))
    assert [h[:2] for h in scenario_headings] == ["S1", "S2", "S3", "S4", "S5", "S6"]
    for heading in scenario_headings:
        header, *rows = tables(all_sections[heading])[0]
        assert header == ["Part", heading[:2]]
        assert [row[0] for row in rows] == SCENARIO_PARTS, heading
        measure = dict((row[0], row[1]) for row in rows)["Measure"]
        assert re.search(r"\d", measure), f"{heading}: Measure has no number"
