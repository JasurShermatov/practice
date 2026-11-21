"""Break each module border on purpose - on a throw-away copy - and show which check turns red.

P06 Step 7 does this once by hand for rule 1 (see logs/s7-red.txt and
logs/s7-green.txt). This script repeats it for all three rules, so the result
can be re-run at any time without touching the real project:

    python3 -I practices/P06-modular-monolith-review/evidence/break_the_border.py hotel-booking

For every case it copies hotel-booking/ to a temporary folder, adds ONE bad
import line, then runs (in the copy):

- the course's 8 behaviour tests      python -m unittest test_booking_service
- the lint-imports look-alike         python -m tests.test_architecture
- the architecture tests              python -m pytest -q tests/test_architecture.py

and prints the result of each. The real project is only read.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Case:
    title: str
    file: str
    after: str  # the bad line is inserted after the first line that starts with this text
    bad_line: str


CASES = [
    Case("Rule 1 (activity sheet Step 7): Reservations names Notifications' internal sender",
         "hotel_booking/reservations/booking.py", "from hotel_booking.rooms import Room",
         "from hotel_booking.notifications.internal import EmailNotificationSender  # step 7"),
    Case("Rule 2: Rooms reaches into Reservations",
         "hotel_booking/rooms/catalog.py", "from typing import Protocol",
         "from hotel_booking.reservations import domain  # bad"),
    Case("Rule 3: Notifications depends on Reservations (the circle P06 removed)",
         "hotel_booking/notifications/internal.py", "from hotel_booking.notifications import Confirmation",
         "from hotel_booking.reservations.domain import Reservation  # bad"),
]

COMMANDS = [
    ("8 behaviour tests", [sys.executable, "-m", "unittest", "test_booking_service"]),
    ("lint-imports look-alike", [sys.executable, "-m", "tests.test_architecture"]),
    ("architecture tests", [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                            "tests/test_architecture.py"]),
]


def insert_line(path: Path, after: str, line: str) -> int:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    index = next(i for i, text in enumerate(lines) if text.startswith(after))
    lines.insert(index + 1, line + "\n")
    path.write_text("".join(lines), encoding="utf-8")
    return index + 2  # 1-based line number of the bad line


def summary(name: str, result: subprocess.CompletedProcess[str]) -> list[str]:
    out = (result.stdout + result.stderr).strip().splitlines()
    if name == "8 behaviour tests":
        keep = [line for line in out if line.startswith(("Ran ", "OK", "FAILED", "ImportError"))]
    elif name == "lint-imports look-alike":
        keep = [line for line in out if line.strip() and not line.startswith("Analyzed")]
    else:
        keep = [line for line in out if line.startswith(("FAILED", "E  ")) or " passed" in line or " failed" in line]
    return [f"  [{name}] exit {result.returncode}"] + [f"    {line}" for line in keep]


def main(project: Path) -> int:
    ignore = shutil.ignore_patterns("__pycache__", ".mypy_cache", ".pytest_cache", ".venv")
    for case in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "hotel-booking"
            shutil.copytree(project, copy, ignore=ignore)
            line_no = insert_line(copy / case.file, case.after, case.bad_line)
            print(f"== {case.title}")
            print(f"   {case.file}:{line_no}: {case.bad_line}")
            for name, command in COMMANDS:
                result = subprocess.run(command, cwd=copy, capture_output=True, text=True,
                                        env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"})
                print("\n".join(summary(name, result)))
            print()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
