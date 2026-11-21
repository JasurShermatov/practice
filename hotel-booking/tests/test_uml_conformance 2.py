"""The code must match the class diagram exactly: same classes, attributes and operations.

The diagram is the Mermaid source in the practice folder. When a later
practice changes the design, it updates CLASS_DIAGRAM to its own diagram.
"""
from __future__ import annotations

import inspect
import re
from datetime import date
from enum import Enum
from pathlib import Path

import pytest

import hotel_booking
from hotel_booking import (
    BookingOutcome,
    BookingResult,
    BookingService,
    DateRange,
    EmailSender,
    Guest,
    Reservation,
    ReservationStore,
    Room,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CLASS_DIAGRAM = REPO_ROOT / "practices" / "P03-hotel-domain-uml" / "uml" / "class-diagram.mmd"

CLASS_HEADER = re.compile(r"^\s*class (\w+) \{\s*$")
MEMBER = re.compile(r"^\s*([+-])(\w+)(\(.*\))?")
RELATION = re.compile(r'^\s*(\w+)\s+(?:"[^"]*"\s+)?(\.\.>|-->|<--|\*--|--)\s+(?:"[^"]*"\s+)?(\w+)\s*:')


def parse_diagram(text: str) -> tuple[dict[str, dict[str, set[str]]], list[tuple[str, str]]]:
    classes: dict[str, dict[str, set[str]]] = {}
    relations: list[tuple[str, str]] = []
    current: str | None = None
    for line in text.splitlines():
        if (header := CLASS_HEADER.match(line)) is not None:
            current = header.group(1)
            classes[current] = {key: set() for key in ("+attr", "-attr", "+op", "-op", "enum")}
            continue
        if current is not None:
            if line.strip() == "}":
                current = None
            elif (member := MEMBER.match(line)) is not None:
                visibility, name, params = member.groups()
                kind = "op" if params else "attr"
                classes[current][f"{visibility}{kind}"].add(name)
            elif line.strip() and not line.strip().startswith("<<"):
                classes[current]["enum"].add(line.strip())
            continue
        if (relation := RELATION.match(line)) is not None:
            relations.append((relation.group(1), relation.group(3)))
    return classes, relations


@pytest.fixture(scope="module")
def diagram() -> tuple[dict[str, dict[str, set[str]]], list[tuple[str, str]]]:
    if not CLASS_DIAGRAM.exists():
        pytest.skip(f"class diagram not found at {CLASS_DIAGRAM}")
    return parse_diagram(CLASS_DIAGRAM.read_text(encoding="utf-8"))


def sample_instances() -> dict[str, object]:
    stay = DateRange(date(2026, 11, 12), date(2026, 11, 14))
    guest = Guest("Maya", "maya@example.com")
    room = Room("R7", "Standard")
    store = ReservationStore()
    return {
        "BookingService": BookingService([room], store, EmailSender()),
        "BookingResult": BookingResult(BookingOutcome.ACCEPTED, "R101"),
        "ReservationStore": store,
        "EmailSender": EmailSender(),
        "Reservation": Reservation("R101", guest, room, stay),
        "Guest": guest,
        "Room": room,
        "DateRange": stay,
    }


def code_members(obj: object) -> dict[str, set[str]]:
    cls = type(obj)
    properties = {name for name, value in vars(cls).items() if isinstance(value, property)}
    fields = set(vars(obj))
    functions = {name for name, value in vars(cls).items() if inspect.isfunction(value)}
    return {
        "+attr": {f for f in fields if not f.startswith("_")} | properties,
        "-attr": {f[1:] for f in fields if f.startswith("_") and f[1:] not in properties},
        "+op": {f for f in functions if not f.startswith("_")},
        "-op": {f[1:] for f in functions if f.startswith("_") and not f.startswith("__")},
    }


def test_diagram_has_exactly_the_public_classes_of_the_package(diagram) -> None:  # type: ignore[no-untyped-def]
    classes, _ = diagram
    assert set(classes) == set(hotel_booking.__all__)


@pytest.mark.parametrize("name", sorted(sample_instances()))
def test_class_members_match_the_diagram(diagram, name: str) -> None:  # type: ignore[no-untyped-def]
    classes, _ = diagram
    expected = classes[name]
    actual = code_members(sample_instances()[name])
    for key in ("+attr", "-attr", "+op", "-op"):
        assert actual[key] == expected[key], f"{name} {key}: code {actual[key]} vs diagram {expected[key]}"


@pytest.mark.parametrize("name", ["ReservationStatus", "BookingOutcome"])
def test_enumeration_values_match_the_diagram(diagram, name: str) -> None:  # type: ignore[no-untyped-def]
    classes, _ = diagram
    enum_cls = getattr(hotel_booking, name)
    assert issubclass(enum_cls, Enum)
    assert {member.name for member in enum_cls} == classes[name]["enum"]


def test_every_relationship_is_visible_in_the_source(diagram) -> None:  # type: ignore[no-untyped-def]
    """Each line on the diagram must correspond to a reference in the code of one end."""
    classes, relations = diagram
    assert len(relations) == 11
    for left, right in relations:
        assert left in classes and right in classes
        left_src = inspect.getsource(getattr(hotel_booking, left))
        right_src = inspect.getsource(getattr(hotel_booking, right))
        assert right in left_src or left in right_src, f"no code link for {left} -- {right}"
