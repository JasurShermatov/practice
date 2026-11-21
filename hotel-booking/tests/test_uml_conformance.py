"""The code must match the class diagrams exactly: same classes, members, interfaces, links - and modules.

The diagrams are the Mermaid sources in the practice folders. When a later
practice changes the design, it points CLASS_DIAGRAM at its own diagram.

P04 change: CLASS_DIAGRAM moved to the P04 diagram; ``<<interface>>`` boxes and
``..|>`` ("implements") lines are understood. Interfaces are ``typing.Protocol``
classes; "implements" is checked structurally (same public methods, same
parameter names).

P06 change (deliberate): CLASS_DIAGRAM now points at the P06 diagram
(``practices/P06-modular-monolith-review/diagrams/class-diagram.mmd``), which
draws one Mermaid ``namespace`` per module and marks internal classes
``<<internal>>``. Because the package root no longer re-exports anything,
classes are looked up in the four module contracts (``__all__``) and their
``internal.py``. New checks: every box sits in the namespace of the module whose
code defines it; ``<<internal>>`` boxes are exactly the classes of the
``internal.py`` files; and the diagram itself respects the module borders (a
line between two modules starts in Reservations and ends at a public class).
The two checks of the P04 activity page "Classes - after" are kept.

P07 change (deliberate): CLASS_DIAGRAM now points at the P07 diagram
(``practices/P07-capacity-api-design/diagrams/class-diagram.mmd``), which adds the
two internal SQL classes (``SqlReservationStore``, ``SqlRoomCatalog``) with their
"implements" lines and one link each (16 -> 18 non-"implements" lines). The
sample instances use an in-memory SQLite connection. The HTTP API edge
(``api.py``) is not a module and is not drawn here; its classes are pydantic
shapes checked against docs/openapi.yaml (``test_openapi_contract.py``).

P09 change (deliberate): CLASS_DIAGRAM now points at the P09 diagram
(``practices/P09-protect-the-last-seat/diagrams/class-diagram.mmd``): ``ReservationStore`` gained
``next_reservation_id`` (both stores implement it; ``BookingService.next_id`` is gone), the list
store has its lock, counter and ``blocked`` helper, the SQL store its ``insert`` helper, and the
contract exports ``OverlapRejected``, drawn as an ``<<exception>>`` box with two lines (the store's
save raises it, BookingService answers Unavailable for it): 18 -> 20 non-"implements" lines.
"""
from __future__ import annotations

import importlib
import inspect
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLASS_DIAGRAM = REPO_ROOT / "practices" / "P09-protect-the-last-seat" / "diagrams" / "class-diagram.mmd"
CLASSES_AFTER = REPO_ROOT / "practices" / "P04-refactor-reservation" / "uml" / "classes-after.mmd"

MODULES = ("rooms", "reservations", "payments", "notifications")

NAMESPACE_HEADER = re.compile(r"^\s*namespace (\w+) \{\s*$")
CLASS_HEADER = re.compile(r"^\s*class (\w+) \{\s*$")
MEMBER = re.compile(r"^\s*([+-])(\w+)(\(.*\))?")
STEREOTYPE = re.compile(r"^\s*<<(.+)>>\s*$")
RELATION = re.compile(
    r'^\s*(\w+)\s+(?:"[^"]*"\s+)?(\.\.\|>|\.\.>|-->|<--|\*--|--)\s+(?:"[^"]*"\s+)?(\w+)\s*:'
)
IMPLEMENTS = "..|>"
USES = "..>"
INTERNAL = "internal"


@dataclass
class Box:
    namespace: str | None = None
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
    namespace: str | None = None
    current: Box | None = None
    for line in text.splitlines():
        if (header := NAMESPACE_HEADER.match(line)) is not None:
            namespace = header.group(1)
            continue
        if (header := CLASS_HEADER.match(line)) is not None:
            current = boxes[header.group(1)] = Box(namespace=namespace)
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
        if line.strip() == "}":  # end of a namespace block
            namespace = None
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


# --- where every class lives in the code -------------------------------------------------


def contract(module: str) -> ModuleType:
    return importlib.import_module(f"hotel_booking.{module}")


def internal(module: str) -> ModuleType:
    return importlib.import_module(f"hotel_booking.{module}.internal")


def public_classes() -> dict[str, tuple[str, type]]:
    """Name -> (module, class) for everything a module's contract exports."""
    return {name: (module, getattr(contract(module), name)) for module in MODULES for name in contract(module).__all__}


def internal_classes() -> dict[str, tuple[str, type]]:
    """Name -> (module, class) for every class *defined* in a module's internal.py."""
    found: dict[str, tuple[str, type]] = {}
    for module in MODULES:
        code = internal(module)
        for name, value in vars(code).items():
            if inspect.isclass(value) and value.__module__ == code.__name__:
                found[name] = (module, value)
    return found


def lookup(name: str) -> type:
    return {**public_classes(), **internal_classes()}[name][1]


def sample_instances() -> dict[str, object]:
    """One real object per concrete class of the four modules (interfaces cannot be instantiated)."""
    rooms_internal, reservations_internal = internal("rooms"), internal("reservations")
    payments_internal, notifications_internal = internal("payments"), internal("notifications")
    res, rms, ntf = contract("reservations"), contract("rooms"), contract("notifications")
    stay = res.DateRange(date(2026, 11, 12), date(2026, 11, 14))
    guest = res.Guest("Maya", "maya@example.com")
    room = rms.Room("R7", "Standard")
    store = reservations_internal.InMemoryReservationStore()
    email = notifications_internal.EmailNotificationSender()
    payments = payments_internal.SimulatedPaymentService()
    payments.take_deposit("R101", Decimal("60.00"))
    return {
        "BookingService": res.BookingService([room], store, email),
        "BookingResult": res.BookingResult(res.BookingOutcome.ACCEPTED, "R101"),
        "InMemoryReservationStore": store,
        "InMemoryRoomCatalog": rooms_internal.InMemoryRoomCatalog([room]),
        "SqlReservationStore": reservations_internal.SqlReservationStore(sqlite3.connect(":memory:"), [room]),
        "SqlRoomCatalog": rooms_internal.SqlRoomCatalog(sqlite3.connect(":memory:")),
        "SimulatedPaymentService": payments,
        "EmailNotificationSender": email,
        "SmsNotificationSender": notifications_internal.SmsNotificationSender(),
        "Confirmation": ntf.Confirmation("R101", guest.email, room.number, stay.check_in, stay.check_out),
        "Reservation": res.Reservation("R101", guest, room, stay),
        "Guest": guest,
        "Room": room,
        "DateRange": stay,
    }


CONCRETE_CLASSES = [
    "BookingResult", "BookingService", "Confirmation", "DateRange", "Guest", "Reservation", "Room",
]
INTERNAL_CLASSES = [
    "EmailNotificationSender", "InMemoryReservationStore", "InMemoryRoomCatalog",
    "SimulatedPaymentService", "SmsNotificationSender",
    "SqlReservationStore", "SqlRoomCatalog",  # P07
]
INTERFACES = ["NotificationSender", "PaymentService", "ReservationStore", "RoomCatalog"]
ENUMERATIONS = ["BookingOutcome", "PaymentStatus", "ReservationStatus"]
EXCEPTIONS = ["OverlapRejected"]  # P09


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


# --- the full class diagram of version 3 -------------------------------------------------


def test_diagram_has_exactly_the_classes_of_the_four_modules(diagram: Diagram) -> None:
    assert set(diagram.boxes) == set(public_classes()) | set(internal_classes())


def test_every_box_is_drawn_in_the_module_that_defines_it(diagram: Diagram) -> None:
    where = {name: module for name, (module, _) in {**public_classes(), **internal_classes()}.items()}
    drawn = {name: box.namespace for name, box in diagram.boxes.items()}
    assert drawn == where


def test_internal_boxes_are_exactly_the_classes_of_the_internal_files(diagram: Diagram) -> None:
    assert diagram.named(INTERNAL) == set(internal_classes()) == set(INTERNAL_CLASSES)
    assert not set(internal_classes()) & set(public_classes()), "a contract re-exports an internal class"


def test_diagram_marks_the_interfaces_and_enumerations(diagram: Diagram) -> None:
    assert diagram.named("interface") == set(INTERFACES)
    assert diagram.named("enumeration") == set(ENUMERATIONS)
    assert diagram.named("exception") == set(EXCEPTIONS)
    assert all(issubclass(lookup(name), Exception) for name in EXCEPTIONS)
    assert diagram.named(None) == set(CONCRETE_CLASSES)


@pytest.mark.parametrize("name", CONCRETE_CLASSES + INTERNAL_CLASSES)
def test_class_members_match_the_diagram(diagram: Diagram, name: str) -> None:
    expected = diagram.boxes[name].members
    actual = code_members(sample_instances()[name])
    for key in ("+attr", "-attr", "+op", "-op"):
        assert actual[key] == expected[key], f"{name} {key}: code {actual[key]} vs diagram {expected[key]}"


@pytest.mark.parametrize("name", INTERFACES)
def test_interfaces_are_protocols_with_the_drawn_operations(diagram: Diagram, name: str) -> None:
    interface = lookup(name)
    box = diagram.boxes[name]
    assert getattr(interface, "_is_protocol", False), f"{name} must be a typing.Protocol"
    assert protocol_operations(interface) == box.members["+op"]
    assert not (box.members["+attr"] | box.members["-attr"] | box.members["-op"])  # a promise has no data


@pytest.mark.parametrize("name", ENUMERATIONS)
def test_enumeration_values_match_the_diagram(diagram: Diagram, name: str) -> None:
    enum_cls = lookup(name)
    assert issubclass(enum_cls, Enum)
    assert {member.name for member in enum_cls} == diagram.boxes[name].values


def test_every_implements_line_holds_in_the_code(diagram: Diagram) -> None:
    implements = diagram.links(IMPLEMENTS)
    assert sorted(implements) == [
        ("EmailNotificationSender", "NotificationSender"),
        ("InMemoryReservationStore", "ReservationStore"),
        ("InMemoryRoomCatalog", "RoomCatalog"),
        ("SimulatedPaymentService", "PaymentService"),
        ("SmsNotificationSender", "NotificationSender"),
        ("SqlReservationStore", "ReservationStore"),
        ("SqlRoomCatalog", "RoomCatalog"),
    ]
    for implementation, interface in implements:
        assert diagram.boxes[implementation].namespace == diagram.boxes[interface].namespace
        assert_keeps_promise(lookup(implementation), lookup(interface))


def test_every_other_relationship_is_visible_in_the_source(diagram: Diagram) -> None:
    """Each non-"implements" line must correspond to a reference in the code of one end."""
    others = [(left, right) for left, kind, right in diagram.relations if kind != IMPLEMENTS]
    assert len(others) == 20  # P06: 16; P07: + 2 (SQL store/catalog); P09: + 2 (OverlapRejected)
    for left, right in others:
        left_src = inspect.getsource(lookup(left))
        right_src = inspect.getsource(lookup(right))
        assert right in left_src or left in right_src, f"no code link for {left} -- {right}"


def test_booking_service_uses_only_the_interfaces(diagram: Diagram) -> None:
    """Dependency inversion on the diagram: BookingService's "uses" lines end at interfaces."""
    used = {right for left, right in diagram.links(USES) if left == "BookingService"}
    assert {"ReservationStore", "NotificationSender"} <= used
    assert not used & set(INTERNAL_CLASSES)


def test_the_diagram_respects_the_module_borders(diagram: Diagram) -> None:
    """Rules 1-3 on paper: a line between two modules starts in Reservations and ends at a public class."""
    crossing = [
        (left, right) for left, _, right in diagram.relations
        if diagram.boxes[left].namespace != diagram.boxes[right].namespace
    ]
    assert crossing, "the modules must be connected somewhere"
    for left, right in crossing:
        # Mermaid lets either end be written first; the dependent end is the one in Reservations.
        ends = {diagram.boxes[left].namespace, diagram.boxes[right].namespace}
        assert "reservations" in ends, f"{left} -- {right}: only Reservations may depend on other modules"
        other = right if diagram.boxes[left].namespace == "reservations" else left
        assert diagram.boxes[other].stereotype != INTERNAL, f"{left} -- {right} reaches internal code"


# --- the P04 activity sheet's page "Classes - after" (kept) ------------------------------


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
    known = {**public_classes(), **internal_classes()}
    for implementation, interface in page.links(IMPLEMENTS):
        cls = known[implementation][1] if implementation in known else getattr(test_booking_service, implementation)
        assert_keeps_promise(cls, known[interface][1])
