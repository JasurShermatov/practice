"""Dependency inversion, checked on the source code itself (P04).

Read with ``ast`` (no import side effects), so the rule holds for every line,
not only for the paths the other tests happen to run:

1. ``booking.py`` (the booking rules) never names a concrete store or sender.
2. Only ``main.py`` (the composition root) creates concrete stores and senders.
3. ``domain.py`` depends on nothing else in the package.
"""
from __future__ import annotations

import ast
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
PACKAGE = PROJECT / "hotel_booking"
CONCRETE_HELPERS = {"InMemoryReservationStore", "EmailNotificationSender", "SmsNotificationSender"}
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
    used = names_used(PACKAGE / "booking.py")
    assert PROMISES <= used
    assert not used & CONCRETE_HELPERS, f"booking.py names a concrete helper: {used & CONCRETE_HELPERS}"


def test_only_main_creates_concrete_stores_and_senders() -> None:
    creators = {
        path.relative_to(PROJECT).as_posix()
        for path in [*PACKAGE.glob("*.py"), PROJECT / "main.py"]
        if constructor_calls(path) & CONCRETE_HELPERS
    }
    assert creators == {"main.py"}


def test_domain_depends_on_nothing_else_in_the_package() -> None:
    assert package_imports(PACKAGE / "domain.py") == set()
