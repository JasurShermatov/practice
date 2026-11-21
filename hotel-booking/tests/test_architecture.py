"""Architecture tests: the borders between the four modules (P06 Step 6).

The course checks the borders with import-linter (``lint-imports``). It cannot
be installed in every environment, so this file does the same job with the
standard library only, and both read the *same* rules: the forbidden contracts
in ``.importlinter`` (parsed with ``configparser``).

How it works (the same model import-linter uses):

1. Every ``.py`` file under ``hotel_booking/`` is parsed with ``ast`` - nothing
   is imported, so a broken border cannot hide behind an import error.
2. Each ``import x`` / ``from x import y`` / relative import becomes an edge
   ``importer -> imported`` (with its line number) when ``imported`` is inside
   the package. ``from pkg import name`` points at ``pkg.name`` if that is a
   module, otherwise at ``pkg``. Imports under ``if TYPE_CHECKING:`` count too.
3. A forbidden contract is broken when any module in a source package reaches
   any module in a forbidden package - directly or through other modules
   (import-linter's default ``allow_indirect_imports = False``). The failure
   names the whole chain, file by file, with line numbers.

Run as a script (``python -m tests.test_architecture``) it prints the contracts
like ``lint-imports`` does (KEPT / BROKEN, then "Contracts: 3 kept, 0 broken.").

Two more rules are portfolio extras (not in the course's three contracts):
no module imports *another* module's internal code (this also covers
``demo.py`` and Payments <-> Notifications), and every class lives in one of
the four module folders.
"""
from __future__ import annotations

import ast
import configparser
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = PROJECT / "hotel_booking"
CONTRACTS_FILE = PROJECT / ".importlinter"
MODULES = ("rooms", "reservations", "payments", "notifications")

COURSE_CONTRACTS = {
    "Reservations uses only the public contracts of other modules",
    "Rooms does not depend on any other module",
    "Payments and Notifications do not depend on Reservations",
}


# --------------------------------------------------------------------------- the import graph


@dataclass(frozen=True)
class Import:
    importer: str
    imported: str
    line: int

    def __str__(self) -> str:
        return f"{self.importer} -> {self.imported} (l.{self.line})"


def module_name(path: Path, package_dir: Path) -> str:
    parts = list(path.relative_to(package_dir.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def is_package(path: Path) -> bool:
    return path.name == "__init__.py"


def resolve_relative(importer: str, importer_is_package: bool, level: int, module: str | None) -> str:
    """``from ..x import y`` inside ``importer`` -> absolute base name."""
    base = importer.split(".")
    if not importer_is_package:
        base = base[:-1]  # a plain module's relative imports start at its package
    if level > 1:
        base = base[: len(base) - (level - 1)]
    return ".".join([*base, module] if module else base)


def build_import_graph(package_dir: Path) -> tuple[set[str], list[Import]]:
    """All module names of the package and every import between them."""
    files = {module_name(path, package_dir): path for path in sorted(package_dir.rglob("*.py"))}
    known = set(files)
    root = package_dir.name

    def target(name: str) -> str | None:
        """The innermost known module that ``name`` refers to, or None if outside the package."""
        while name:
            if name in known:
                return name
            name = name.rpartition(".")[0]
        return None

    edges: list[Import] = []
    for importer, path in files.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == root or alias.name.startswith(root + "."):
                        if (found := target(alias.name)) is not None:
                            edges.append(Import(importer, found, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = resolve_relative(importer, is_package(path), node.level, node.module)
                else:
                    base = node.module or ""
                if not (base == root or base.startswith(root + ".")):
                    continue
                for alias in node.names:
                    candidate = f"{base}.{alias.name}"
                    found = candidate if candidate in known else target(base)
                    if found is not None and found != importer:
                        edges.append(Import(importer, found, node.lineno))
    return known, edges


def within(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def broken_chains(
    known: set[str], edges: list[Import], sources: list[str], forbidden: list[str]
) -> list[list[Import]]:
    """Shortest import chain from each source module to each forbidden module it reaches.

    Like import-linter, a chain starts at the *last* module inside the source
    packages: the search never walks through another source module (that one
    gets its own search), so each bad import is reported once, at its file.
    """
    by_importer: dict[str, list[Import]] = {}
    for edge in edges:
        by_importer.setdefault(edge.importer, []).append(edge)

    def in_sources(module: str) -> bool:
        return any(within(module, s) for s in sources)

    chains: list[list[Import]] = []
    for start in sorted(m for m in known if in_sources(m)):
        came_from: dict[str, Import | None] = {start: None}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for edge in by_importer.get(current, []):
                if edge.imported in came_from or in_sources(edge.imported):
                    continue
                came_from[edge.imported] = edge
                if any(within(edge.imported, f) for f in forbidden):
                    chain: list[Import] = []
                    step: Import | None = edge
                    while step is not None:
                        chain.append(step)
                        step = came_from[step.importer]
                    chains.append(chain[::-1])
                else:
                    queue.append(edge.imported)
    return chains


# --------------------------------------------------------------------------- the contracts file


@dataclass(frozen=True)
class ForbiddenContract:
    key: str
    name: str
    sources: list[str]
    forbidden: list[str]


def read_contracts(path: Path) -> list[ForbiddenContract]:
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    contracts = []
    for section in parser.sections():
        if not section.startswith("importlinter:contract:"):
            continue
        body = parser[section]
        assert body["type"] == "forbidden", f"{section}: only 'forbidden' contracts are understood here"
        contracts.append(ForbiddenContract(
            key=section.removeprefix("importlinter:contract:"),
            name=body["name"],
            sources=body["source_modules"].split(),
            forbidden=body["forbidden_modules"].split(),
        ))
    return contracts


def report(contract: ForbiddenContract, chains: list[list[Import]]) -> str:
    """A message in the shape of lint-imports' output, so the two read the same."""
    lines = [f"{contract.name} BROKEN", ""]
    for chain in chains:
        first, last = chain[0], chain[-1]
        lines.append(f"{first.importer} is not allowed to import {last.imported}:")
        lines.extend(f"-   {step}" for step in chain)
        lines.append("")
    return "\n".join(lines)


CONTRACTS = read_contracts(CONTRACTS_FILE)


@pytest.fixture(scope="module")
def graph() -> tuple[set[str], list[Import]]:
    return build_import_graph(PACKAGE_DIR)


# --------------------------------------------------------------------------- the three course rules


def test_contracts_file_holds_the_three_course_rules() -> None:
    parser = configparser.ConfigParser()
    parser.read(CONTRACTS_FILE, encoding="utf-8")
    assert parser["importlinter"]["root_package"] == "hotel_booking"
    assert {contract.name for contract in CONTRACTS} == COURSE_CONTRACTS


@pytest.mark.parametrize("contract", CONTRACTS, ids=[contract.key for contract in CONTRACTS])
def test_contract_is_kept(contract: ForbiddenContract, graph: tuple[set[str], list[Import]]) -> None:
    known, edges = graph
    for package in [*contract.sources, *contract.forbidden]:
        assert package in known, f"{contract.name}: {package} does not exist (typo in .importlinter?)"
    chains = broken_chains(known, edges, contract.sources, contract.forbidden)
    assert not chains, report(contract, chains)


def test_the_checker_sees_the_allowed_dependencies(graph: tuple[set[str], list[Import]]) -> None:
    """Guards against a checker that passes because it sees nothing: the arrows of the design exist."""
    _, edges = graph
    pairs = {(edge.importer, edge.imported) for edge in edges}
    assert ("hotel_booking.reservations.booking", "hotel_booking.notifications") in pairs
    assert ("hotel_booking.reservations.booking", "hotel_booking.rooms") in pairs
    assert ("hotel_booking.notifications.internal", "hotel_booking.notifications") in pairs


# --------------------------------------------------------------------------- portfolio extras


def test_no_module_imports_another_modules_internal_code(graph: tuple[set[str], list[Import]]) -> None:
    """Only a module itself (and, outside the package, main.py and the tests) may import its internal.py."""
    _, edges = graph
    offending = []
    for edge in edges:
        for owner in MODULES:
            if within(edge.imported, f"hotel_booking.{owner}.internal") and not within(
                edge.importer, f"hotel_booking.{owner}"
            ):
                offending.append(str(edge))
    assert not offending, "imports of another module's internal code:\n" + "\n".join(offending)


def test_package_root_exports_nothing() -> None:
    tree = ast.parse((PACKAGE_DIR / "__init__.py").read_text(encoding="utf-8"))
    assert not [node for node in tree.body if isinstance(node, ast.Import | ast.ImportFrom)]


def test_every_class_lives_in_one_of_the_four_modules() -> None:
    outside = []
    for path in PACKAGE_DIR.rglob("*.py"):
        top = path.relative_to(PACKAGE_DIR).parts[0]
        classes = [node.name for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                   if isinstance(node, ast.ClassDef)]
        if classes and top not in MODULES:
            outside.append(f"{path.relative_to(PROJECT)}: {classes}")
    assert not outside, outside


# --------------------------------------------------------------------------- the checker checks itself


def write_package(root: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = root / "hotel_booking" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root / "hotel_booking"


MINI_APP = {
    "__init__.py": "",
    "rooms/__init__.py": "",
    "rooms/internal.py": "",
    "payments/__init__.py": "",
    "payments/internal.py": "",
    "notifications/__init__.py": "",
    "notifications/internal.py": "from hotel_booking.notifications import X\n",
    "reservations/__init__.py": "",
    "reservations/booking.py": "from hotel_booking.notifications import Confirmation\n",
}


@pytest.mark.parametrize(
    ("bad_file", "bad_line", "broken"),
    [
        ("reservations/booking.py", "from hotel_booking.notifications.internal import EmailNotificationSender\n",
         "Reservations uses only the public contracts of other modules"),
        ("reservations/booking.py", "from ..notifications import internal\n",
         "Reservations uses only the public contracts of other modules"),
        ("rooms/internal.py", "import hotel_booking.reservations\n",
         "Rooms does not depend on any other module"),
        ("notifications/__init__.py", "from hotel_booking.reservations.booking import BookingService\n",
         "Payments and Notifications do not depend on Reservations"),
    ],
    ids=["rule1-direct", "rule1-relative", "rule2", "rule3"],
)
def test_checker_catches_each_kind_of_bad_import(
    tmp_path: Path, bad_file: str, bad_line: str, broken: str
) -> None:
    package_dir = write_package(tmp_path, {**MINI_APP, bad_file: MINI_APP[bad_file] + bad_line})
    known, edges = build_import_graph(package_dir)
    failing = {c.name for c in CONTRACTS if broken_chains(known, edges, c.sources, c.forbidden)}
    assert failing == {broken}


def test_checker_catches_an_indirect_bad_import(tmp_path: Path) -> None:
    """reservations -> helper -> notifications.internal: broken although booking.py looks clean."""
    package_dir = write_package(tmp_path, {
        **MINI_APP,
        "reservations/booking.py": "from hotel_booking import shortcut\n",
        "shortcut.py": "from hotel_booking.notifications.internal import EmailNotificationSender\n",
    })
    known, edges = build_import_graph(package_dir)
    rule1 = next(c for c in CONTRACTS if c.key == "reservations-uses-contracts-only")
    chains = broken_chains(known, edges, rule1.sources, rule1.forbidden)
    assert [[str(step) for step in chain] for chain in chains] == [[
        "hotel_booking.reservations.booking -> hotel_booking.shortcut (l.1)",
        "hotel_booking.shortcut -> hotel_booking.notifications.internal (l.1)",
    ]]


# --------------------------------------------------------------------------- lint-imports look-alike


def main() -> int:
    """``python -m tests.test_architecture``: the three contracts, printed the way lint-imports prints them."""
    known, edges = build_import_graph(PACKAGE_DIR)
    print(f"Analyzed {len(known)} files, {len({(e.importer, e.imported) for e in edges})} dependencies.")
    broken = []
    for contract in CONTRACTS:
        chains = broken_chains(known, edges, contract.sources, contract.forbidden)
        print(f"{contract.name} {'BROKEN' if chains else 'KEPT'}")
        if chains:
            broken.append(report(contract, chains))
    print()
    for message in broken:
        print(message)
    print(f"Contracts: {len(CONTRACTS) - len(broken)} kept, {len(broken)} broken.")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
