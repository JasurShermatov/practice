"""The code must match the class diagrams exactly: same classes, members, interfaces and links.

The diagrams are the Mermaid sources in the practice folder. When a later
practice changes the design, it points CLASS_DIAGRAM at its own diagram.

P04 change (deliberate): CLASS_DIAGRAM moved from the P03 diagram to the P04
one, and the parser now understands ``<<interface>>`` boxes and ``..|>``
("implements") lines. Interfaces are ``typing.Protocol`` classes; "implements"
is checked structurally (same public methods, same parameter names), because a
Protocol is kept by shape, not by inheritance. Two more tests check the
activity sheet's "Classes - after" page (2 interfaces, 5 classes, 2 "uses",
4 "implements").

Names are looked up lazily (``getattr``) so that, while the code is between the
P03 and the P04 design, only the affected tests fail, not the whole module.
"""
from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

import pytest

import hotel_booking

REPO_ROOT = Path(__file__).resolve().parents[2]
UML_DIR = REPO_ROOT / "practices" / "P04-refactor-reservation" / "uml"
CLASS_DIAGRAM = UML_DIR / "class-diagram.mmd"
CLASSES_AFTER = UML_DIR / "classes-after.mmd"

CLASS_HEADER = re.compile(r"^\s*class (\w+) \{\s*$")
MEMBER = re.compile(r"^\s*([+-])(\w+)(\(.*\))?")
STEREOTYPE = re.compile(r"^\s*<<(.+)>>\s*$")
RELATION = re.compile(
    r'^\s*(\w+)\s+(?:"[^"]*"\s+)?(\.\.\|>|\.\.>|-->|<--|\*--|--)\s+(?:"[^"]*"\s+)?(\w+)\s*:'
)
IMPLEMENTS = "..|>"
USES = "..>"


@dataclass
class Box:
    stereotype: str | None = None
    members: dict[str, set[str]] = field(
        default_factory=lambda: {key: set() for key in ("+attr", "-attr", "+op", "-op")}
    )
    values: set[str] = field(default_factory=set)  # enumeration literals


@dataclass
class Diagram:
    boxes: dict[str, Box]
    relations: list[tuple[str, str, str]]  # (left, arrow, right)

    def named(self, stereotype: str | None) -> set[str]:
        return {name for name, box in self.boxes.items() if box.stereotype == stereotype}

    def links(self, arrow: str) -> list[tuple[str, str]]:
        return [(left, right) for left, kind, right in self.relations if kind == arrow]


def parse_diagram(text: str) -> Diagram:
    boxes: dict[str, Box] = {}
    relations: list[tuple[str, str, str]] = []
    current: Box | None = None
    for line in text.splitlines():
        if (header := CLASS_HEADER.match(line)) is not None:
            current = boxes[header.group(1)] = Box()
            continue
        if current is not None:
            if line.strip() == "}":
                current = None
            elif (stereotype := STEREOTYPE.match(line)) is not None:
                current.stereotype = stereotype.group(1)
            elif (member := MEMBER.match(line)) is not None:
                visibility, name, params = member.groups()
                current.members[f"{visibility}{'op' if params else 'attr'}"].add(name)
            elif line.strip():
                current.values.add(line.strip())
            continue
        if (relation := RELATION.match(line)) is not None:
            left, arrow, right = relation.groups()
            relations.append((left, arrow, right))
    return Diagram(boxes, relations)


def load(path: Path) -> Diagram:
    if not path.exists():
        pytest.skip(f"diagram not found at {path}")
    return parse_diagram(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def diagram() -> Diagram:
    return load(CLASS_DIAGRAM)


def sample_instances() -> dict[str, object]:
    """One real object per concrete class of the package (interfaces cannot be instantiated)."""
    hb = hotel_booking
    stay = hb.DateRange(date(2026, 11, 12), date(2026, 11, 14))
    guest = hb.Guest("Maya", "maya@example.com")
    room = hb.Room("R7", "Standard")
    store = getattr(hb, "InMemoryReservationStore")()
    email = getattr(hb, "EmailNotificationSender")()
    return {
        "BookingService": hb.BookingService([room], store, email),
        "BookingResult": hb.BookingResult(hb.BookingOutcome.ACCEPTED, "R101"),
        "InMemoryReservationStore": store,
        "EmailNotificationSender": email,
        "SmsNotificationSender": getattr(hb, "SmsNotificationSender")(),
        "Reservation": hb.Reservation("R101", guest, room, stay),
        "Guest": guest,
        "Room": room,
        "DateRange": stay,
    }


CONCRETE_CLASSES = [
    "BookingResult", "BookingService", "DateRange", "EmailNotificationSender", "Guest",
    "InMemoryReservationStore", "Reservation", "Room", "SmsNotificationSender",
]


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


def protocol_operations(cls: type) -> set[str]:
    return {name for name, value in vars(cls).items() if inspect.isfunction(value) and not name.startswith("_")}


def parameter_names(function: Any) -> list[str]:
    return [name for name in inspect.signature(function).parameters if name != "self"]


def assert_keeps_promise(implementation: type, interface: type) -> None:
    """Structural "implements": every method of the Protocol, with the same parameter names."""
    assert getattr(interface, "_is_protocol", False), f"{interface.__name__} is not a typing.Protocol"
    for operation in protocol_operations(interface):
        method = getattr(implementation, operation, None)
        assert callable(method), f"{implementation.__name__} lacks {operation}()"
        assert parameter_names(method) == parameter_names(getattr(interface, operation)), (
            f"{implementation.__name__}.{operation} has a different signature than {interface.__name__}"
        )


# --- the full class diagram of version 2 -------------------------------------------------


def test_diagram_has_exactly_the_public_classes_of_the_package(diagram: Diagram) -> None:
    assert set(diagram.boxes) == set(hotel_booking.__all__)


def test_diagram_marks_the_two_interfaces_and_two_enumerations(diagram: Diagram) -> None:
    assert diagram.named("interface") == {"ReservationStore", "NotificationSender"}
    assert diagram.named("enumeration") == {"ReservationStatus", "BookingOutcome"}
    assert diagram.named(None) == set(CONCRETE_CLASSES)


@pytest.mark.parametrize("name", CONCRETE_CLASSES)
def test_class_members_match_the_diagram(diagram: Diagram, name: str) -> None:
    expected = diagram.boxes[name].members
    actual = code_members(sample_instances()[name])
    for key in ("+attr", "-attr", "+op", "-op"):
        assert actual[key] == expected[key], f"{name} {key}: code {actual[key]} vs diagram {expected[key]}"


@pytest.mark.parametrize("name", ["ReservationStore", "NotificationSender"])
def test_interfaces_are_protocols_with_the_drawn_operations(diagram: Diagram, name: str) -> None:
    interface = getattr(hotel_booking, name)
    box = diagram.boxes[name]
    assert getattr(interface, "_is_protocol", False), f"{name} must be a typing.Protocol"
    assert protocol_operations(interface) == box.members["+op"]
    assert not (box.members["+attr"] | box.members["-attr"] | box.members["-op"])  # a promise has no data


@pytest.mark.parametrize("name", ["ReservationStatus", "BookingOutcome"])
def test_enumeration_values_match_the_diagram(diagram: Diagram, name: str) -> None:
    enum_cls = getattr(hotel_booking, name)
    assert issubclass(enum_cls, Enum)
    assert {member.name for member in enum_cls} == diagram.boxes[name].values


def test_every_implements_line_holds_in_the_code(diagram: Diagram) -> None:
    implements = diagram.links(IMPLEMENTS)
    assert sorted(implements) == [
        ("EmailNotificationSender", "NotificationSender"),
        ("InMemoryReservationStore", "ReservationStore"),
        ("SmsNotificationSender", "NotificationSender"),
    ]
    for implementation, interface in implements:
        assert_keeps_promise(getattr(hotel_booking, implementation), getattr(hotel_booking, interface))


def test_every_other_relationship_is_visible_in_the_source(diagram: Diagram) -> None:
    """Each non-"implements" line must correspond to a reference in the code of one end."""
    others = [(left, right) for left, kind, right in diagram.relations if kind != IMPLEMENTS]
    assert len(others) == 11
    for left, right in others:
        left_src = inspect.getsource(getattr(hotel_booking, left))
        right_src = inspect.getsource(getattr(hotel_booking, right))
        assert right in left_src or left in right_src, f"no code link for {left} -- {right}"


def test_booking_service_uses_only_the_interfaces(diagram: Diagram) -> None:
    """Dependency inversion on the diagram: BookingService's "uses" lines end at interfaces."""
    used = {right for left, right in diagram.links(USES) if left == "BookingService"}
    assert {"ReservationStore", "NotificationSender"} <= used
    assert not used & {"InMemoryReservationStore", "EmailNotificationSender", "SmsNotificationSender"}


# --- the activity sheet's page "Classes - after" ------------------------------------------


def test_classes_after_page_has_the_counts_of_the_p04_checklist() -> None:
    page = load(CLASSES_AFTER)
    assert len(page.named("interface")) == 2
    assert len(page.boxes) - len(page.named("interface")) == 5
    assert len(page.links(USES)) == 2
    assert len(page.links(IMPLEMENTS)) == 4
    assert page.named("tests only") == {"FakeNotificationSender"}


def test_classes_after_page_implements_lines_hold_in_the_code() -> None:
    import test_booking_service  # the course's unittest file at the project root holds the fake

    page = load(CLASSES_AFTER)
    for implementation, interface in page.links(IMPLEMENTS):
        cls = getattr(hotel_booking, implementation, None) or getattr(test_booking_service, implementation)
        assert_keeps_promise(cls, getattr(hotel_booking, interface))
