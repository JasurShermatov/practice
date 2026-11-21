"""Break the code/contract agreement on purpose, on throw-away copies, and show that the check notices.

    python3 -I practices/P07-capacity-api-design/evidence/break_the_contract.py hotel-booking

For each mutation: copy the project to a temporary folder, change ONE line (in the code or in
docs/openapi.yaml), run tests/test_openapi_contract.py on the copy and print which checks fail.
The project itself is never changed. A check that cannot fail proves nothing; this shows that
tests/test_openapi_contract.py fails in both directions (code ahead of contract, contract ahead of code).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MUTATIONS: list[tuple[str, str, str, str]] = [
    # (what, file, old text, new text)
    ("code answers a status the contract does not list (UnknownRoom 400 -> 404)",
     "hotel_booking/api.py", 'problem(400, "UnknownRoom"', 'problem(404, "UnknownRoom"'),
    ("code serves a route the contract does not have (GET /stats)",
     "hotel_booking/api.py", 'Route("/openapi.yaml", serve_contract, methods=["GET"]),',
     'Route("/openapi.yaml", serve_contract, methods=["GET"]),\n            Route("/stats", serve_contract, methods=["GET"]),'),
    ("contract forgets an answer the code gives (POST /reservations 409 removed)",
     "docs/openapi.yaml", '        "409":\n          description: Unavailable when',
     '        "x-removed-409":\n          description: Unavailable when'),
    ("contract example differs from the real body (detail reworded)",
     "docs/openapi.yaml", 'detail: "There is no room R99."', 'detail: "Room R99 does not exist."'),
    ("contract renames an answer field (notificationFailed -> notificationsFailed)",
     "docs/openapi.yaml", "        notificationFailed:\n          type: boolean",
     "        notificationsFailed:\n          type: boolean"),
    ("code adds an error title the contract's Problem list lacks (InvalidRequest -> BadRequest for limit)",
     "hotel_booking/api.py", 'problem(400, "InvalidRequest", LIMIT_DETAIL)', 'problem(400, "BadRequest", LIMIT_DETAIL)'),
]


def run_contract_tests(project: Path) -> tuple[int, list[str], str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", "tests/test_openapi_contract.py"],
        cwd=project, capture_output=True, text=True)
    failed = [line.removeprefix("FAILED ").split(" - ")[0] for line in result.stdout.splitlines() if line.startswith("FAILED ")]
    return result.returncode, failed, result.stdout.strip().splitlines()[-1]


def first_difference(old: str, new: str) -> tuple[str, str]:
    """The first line that the mutation changes (or adds), for the report."""
    old_lines, new_lines = old.splitlines(), new.splitlines()
    for index, line in enumerate(new_lines):
        if index >= len(old_lines) or line != old_lines[index]:
            return (old_lines[index].strip() if index < len(old_lines) else "(nothing)"), line.strip()
    return old_lines[0].strip(), new_lines[0].strip()


def copy(project: Path) -> Path:
    target = Path(tempfile.mkdtemp(prefix="contract-")) / "hotel-booking"
    shutil.copytree(project, target, ignore=shutil.ignore_patterns("__pycache__", "*.sqlite3", ".mypy_cache"))
    return target


def main(argv: list[str]) -> int:
    project = Path(argv[0]).resolve()
    code, failed, summary = run_contract_tests(copy(project))
    print(f"Unchanged copy: {summary}")
    unexpected = code != 0
    for number, (what, file, old, new) in enumerate(MUTATIONS, start=1):
        mutated = copy(project)
        path = mutated / file
        text = path.read_text(encoding="utf-8")
        assert text.count(old) == 1, f"mutation {number}: the text to change is not unique in {file}"
        path.write_text(text.replace(old, new), encoding="utf-8")
        code, failed, summary = run_contract_tests(mutated)
        before, after = first_difference(old, new)
        print(f"\n{number}. {what}\n   changed {file}: {before!r} -> {after!r}")
        print(f"   result: {summary}")
        for name in failed:
            print(f"   FAILED {name}")
        unexpected |= code == 0
    print("\nEvery mutation was caught." if not unexpected else "\nA mutation was NOT caught - see above.")
    return 1 if unexpected else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
