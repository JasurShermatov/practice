"""Dependency inversion, checked on the source code itself (P04; re-pointed in P06).

Read with ``ast`` (no import side effects), so the rule holds for every line,
not only for the paths the other tests happen to run:

1. ``reservations/booking.py`` (the booking rules) never names a concrete store or sender.
2. Only ``main.py`` (the wiring) creates concrete classes of any module.
3. ``reservations/domain.py`` depends on nothing in the app except the Rooms contract.

P06 change (deliberate): the files moved into the modules, so the paths changed;
rule 2 now covers every concrete class of every module (room catalog and
payment service included) and searches the module folders recursively; rule 3
allows exactly one import, ``hotel_booking.rooms`` (``Room`` moved there). The
borders *between* modules are checked in ``test_architecture.py``.

P07 change (deliberate): the two SQL classes (``SqlReservationStore``,
``SqlRoomCatalog``) joined the concrete helpers; rule 2 now also proves that
the HTTP API (``hotel_booking/api.py``) creates none of them - it receives a
unit of work from the wiring.
"""
from __future__ import annotations

import ast
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
PACKAGE = PROJECT / "hotel_booking"
BOOKING = PACKAGE / "reservations" / "booking.py"
DOMAIN = PACKAGE / "reservations" / "domain.py"
CONCRETE_HELPERS = {
    "InMemoryReservationStore", "EmailNotificationSender", "SmsNotificationSender",
    "InMemoryRoomCatalog", "SimulatedPaymentService",
    "SqlReservationStore", "SqlRoomCatalog",  # P07
}
PROMISES = {"ReservationStore", "NotificationSender"}


def names_used(path: Path) -> set[str]:
    """Every identifier and imported name in a module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
    return names


def constructor_calls(path: Path) -> set[str]:
    """Names of the classes a module calls, e.g. ``InMemoryReservationStore()``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def package_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.level > 0 or (node.module or "").startswith("hotel_booking"))
    }


def test_booking_rules_name_only_the_promises() -> None:
    used = names_used(BOOKING)
    assert PROMISES <= used
    assert not used & CONCRETE_HELPERS, f"booking.py names a concrete helper: {used & CONCRETE_HELPERS}"


def test_only_main_creates_concrete_classes_of_the_modules() -> None:
    creators = {
        path.relative_to(PROJECT).as_posix()
        for path in [*PACKAGE.rglob("*.py"), PROJECT / "main.py"]
        if constructor_calls(path) & CONCRETE_HELPERS
    }
    assert creators == {"main.py"}


def test_domain_depends_only_on_the_rooms_contract() -> None:
    assert package_imports(DOMAIN) == {"hotel_booking.rooms"}


def test_the_api_names_no_concrete_helper() -> None:
    """P07: the HTTP edge knows only BookingService and the contracts, never a store or a sender."""
    used = names_used(PACKAGE / "api.py")
    assert "BookingService" in used
    assert not used & CONCRETE_HELPERS, f"api.py names a concrete helper: {used & CONCRETE_HELPERS}"
