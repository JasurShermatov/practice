"""Automated checks for the P06 documents and diagrams ("Your P06 checklist", activity sheet Step 8).

The code itself is checked by hotel-booking's own tests. These checks cover what
those tests cannot see:

- the draw.io page "Modules": 5 boxes (Reservations green, the internal sender
  purple and dashed), 3 "Uses" + 1 "Implements" dashed arrows, 1 red "Forbidden"
  arrow from Reservations to the internal sender; the page "Context map" is still there;
- the Mermaid twin of that page has the same shape;
- the as-built module diagram shows exactly the imports the code really has
  (computed with the same ast import graph as tests/test_architecture.py, plus main.py);
- design-notes.md has the five P06 sections, ADR-001 has its five sections;
- the project folder matches the course's "finished P06 folder";
- every relative link in the P06 docs and the project docs points at a file that exists.

Run from the portfolio root:
    python -m pytest -p no:cacheprovider practices/P06-modular-monolith-review/checks -v
"""
from __future__ import annotations

import ast
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

PRACTICE = Path(__file__).resolve().parents[1]
PORTFOLIO = PRACTICE.parents[1]
PROJECT = PORTFOLIO / "hotel-booking"
DOCS = PROJECT / "docs"
DIAGRAMS = PRACTICE / "diagrams"

sys.path.insert(0, str(PROJECT))
from tests.test_architecture import build_import_graph  # noqa: E402  (same graph as the architecture test)


# --------------------------------------------------------------------------- draw.io


def drawio_page(name: str) -> ET.Element:
    root = ET.parse(DOCS / "diagrams.drawio").getroot()
    pages = {page.get("name"): page for page in root.iter("diagram")}
    assert name in pages, f"page {name!r} missing; pages: {list(pages)}"
    return pages[name]


def test_drawio_file_has_the_context_map_and_the_modules_page() -> None:
    root = ET.parse(DOCS / "diagrams.drawio").getroot()
    assert [page.get("name") for page in root.iter("diagram")] == ["Context map", "Modules"]


def test_modules_page_has_the_required_shape() -> None:
    page = drawio_page("Modules")
    cells = list(page.iter("mxCell"))
    boxes = {c.get("id"): c for c in cells if c.get("vertex") == "1" and "text;" not in (c.get("style") or "")}
    edges = [c for c in cells if c.get("edge") == "1"]
    assert len(boxes) == 5
    green = [i for i, c in boxes.items() if "fillColor=#C8E6C9" in c.get("style", "")]
    purple = [i for i, c in boxes.items() if "fillColor=#F3E5F5" in c.get("style", "") and "dashed=1" in c.get("style", "")]
    assert green == ["mod-reservations"] and "Reservations" in boxes["mod-reservations"].get("value", "")
    assert purple == ["i-email"] and "EmailNotificationSender" in boxes["i-email"].get("value", "")
    assert len(edges) == 5
    assert all("dashed=1" in e.get("style", "") and "endArrow=open" in e.get("style", "") for e in edges)
    labels = sorted(e.get("value", "").split(" ")[0] for e in edges)
    assert labels == ["Forbidden", "Implements", "Uses", "Uses", "Uses"]
    for edge in edges:
        if edge.get("value", "").startswith("Uses"):
            assert edge.get("source") == "mod-reservations"
    forbidden = next(e for e in edges if e.get("value") == "Forbidden")
    assert (forbidden.get("source"), forbidden.get("target")) == ("mod-reservations", "i-email")
    assert "strokeColor=#C62828" in forbidden.get("style", "")
    implements = next(e for e in edges if e.get("value") == "Implements")
    assert (implements.get("source"), implements.get("target")) == ("i-email", "c-notifications")


# --------------------------------------------------------------------------- Mermaid


EDGE = re.compile(r"^\s*(\w+)\s*(-\.->|-->)\s*(?:\|\"?([^|\"]+)\"?\|)?\s*(\w+)\s*$")


def mermaid_edges(path: Path) -> list[tuple[str, str, str]]:
    edges = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if (match := EDGE.match(line)) is not None:
            left, _, label, right = match.groups()
            edges.append((left, (label or "").strip(), right))
    return edges


def test_mermaid_modules_page_matches_the_drawio_page() -> None:
    edges = mermaid_edges(DIAGRAMS / "modules.mmd")
    assert sorted((l, lab.split(" ")[0], r) for l, lab, r in edges) == sorted([
        ("res", "Uses", "rooms"), ("res", "Uses", "pay"), ("res", "Uses", "ntf"),
        ("email", "Implements", "ntf"), ("res", "Forbidden", "email"),
    ])
    text = (DIAGRAMS / "modules.mmd").read_text(encoding="utf-8")
    assert "linkStyle 4 stroke:#c62828" in text  # the 5th edge (Forbidden) is red
    assert "class res owner" in text and "class email internal" in text


NODE_OF_MODULE = {"rooms": "rooms", "reservations": "res", "payments": "pay", "notifications": "ntf"}


def node(module: str) -> str:
    """hotel_booking.<m>[.x] -> <m>_c, hotel_booking.<m>.internal -> <m>_i, hotel_booking.demo -> demo."""
    parts = module.split(".")
    if parts[1] == "demo":
        return "demo"
    suffix = "_i" if len(parts) > 2 and parts[2] == "internal" else "_c"
    return NODE_OF_MODULE[parts[1]] + suffix


def real_module_edges() -> set[tuple[str, str]]:
    known, edges = build_import_graph(PROJECT / "hotel_booking")
    found = {(node(e.importer), node(e.imported)) for e in edges if e.importer != "hotel_booking"}
    tree = ast.parse((PROJECT / "main.py").read_text(encoding="utf-8"))
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom) and (statement.module or "").startswith("hotel_booking."):
            found.add(("main", node(statement.module or "")))
    return {(a, b) for a, b in found if a != b}


def test_as_built_diagram_shows_exactly_the_real_imports() -> None:
    drawn = {(left, right) for left, _, right in mermaid_edges(DIAGRAMS / "module-dependencies.mmd")}
    assert drawn == real_module_edges()


def test_svgs_exist_for_every_mermaid_source() -> None:
    for source in DIAGRAMS.glob("*.mmd"):
        svg = source.with_suffix(".svg")
        assert svg.exists() and svg.stat().st_size > 1000, f"{svg.name} missing - run mmdc"


# --------------------------------------------------------------------------- documents


def headings(path: Path, level: int) -> list[str]:
    return re.findall(rf"^{'#' * level} (.+)$", path.read_text(encoding="utf-8"), re.MULTILINE)


def test_design_notes_have_the_five_p06_sections() -> None:
    text = (DOCS / "design-notes.md").read_text(encoding="utf-8")
    p06 = text[text.index("# P06 design notes"):]
    found = re.findall(r"^## (.+)$", p06, re.MULTILINE)
    for section in ["Before", "Modules", "Architecture rules", "Broken on purpose", "After"]:
        assert section in found, f"design-notes.md P06: missing ## {section}"
    assert found.index("Before") < found.index("After")


def test_adr_001_has_status_and_the_five_sections() -> None:
    adr = DOCS / "adr-001-modular-monolith.md"
    text = adr.read_text(encoding="utf-8")
    assert text.startswith("# ADR-001")
    assert re.search(r"^Status: Accepted", text, re.MULTILINE)
    assert headings(adr, 2) == ["Context", "Decision", "Alternatives considered", "Consequences", "Revisit when"]


def test_project_folder_matches_the_finished_p06_folder() -> None:
    expected = [
        "docs/adr-001-modular-monolith.md", "docs/contexts.md", "docs/design-notes.md", "docs/diagrams.drawio",
        "docs/quality-scenarios.md", "docs/requirements.md",
        "hotel_booking/__init__.py",
        "hotel_booking/notifications/__init__.py", "hotel_booking/notifications/internal.py",
        "hotel_booking/payments/__init__.py", "hotel_booking/payments/internal.py",
        "hotel_booking/reservations/__init__.py", "hotel_booking/reservations/booking.py",
        "hotel_booking/reservations/domain.py", "hotel_booking/reservations/internal.py",
        "hotel_booking/rooms/__init__.py", "hotel_booking/rooms/catalog.py", "hotel_booking/rooms/internal.py",
        "main.py", "pyproject.toml", "test_booking_service.py", ".importlinter",
    ]
    missing = [path for path in expected if not (PROJECT / path).exists()]
    assert not missing, missing
    gone = [p for p in ["booking.py", "domain.py", "stores.py", "notifications.py"] if (PROJECT / "hotel_booking" / p).exists()]
    assert not gone, f"P04 files left in their old place: {gone}"


def test_copied_p05_docs_keep_their_content() -> None:
    """The three P05 files were copied, not rewritten: every P05 heading is still there."""
    p05 = PORTFOLIO / "practices" / "P05-domain-context-boundaries" / "docs"
    for name in ["quality-scenarios.md", "contexts.md", "l03-notes.md"]:
        for level in (1, 2, 3):
            assert set(headings(p05 / name, level)) <= set(headings(DOCS / name, level)), name


LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def markdown_files() -> list[Path]:
    return sorted([*PRACTICE.rglob("*.md"), *DOCS.glob("*.md"), PROJECT / "README.md"])


@pytest.mark.parametrize("path", markdown_files(), ids=lambda p: str(p.relative_to(PORTFOLIO)))
def test_every_relative_link_resolves(path: Path) -> None:
    broken = []
    for target in LINK.findall(path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if not (path.parent / target).exists():
            broken.append(target)
    assert not broken, f"{path.relative_to(PORTFOLIO)}: broken links {broken}"
