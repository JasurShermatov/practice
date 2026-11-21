"""Undo the P09 repair in small pieces, on throw-away copies, and check that a test notices every time.

    python3 -I practices/P09-protect-the-last-seat/evidence/break_the_fix.py hotel-booking

The regression tests are only worth something if they fail when the protection is taken away. Each
mutation below copies the project into a temporary folder, changes one thing, runs the whole test
suite there and expects at least one failure. The real project is never touched.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

INTERNAL = "hotel_booking/reservations/internal.py"
BOOKING = "hotel_booking/reservations/booking.py"

MUTATIONS: list[tuple[str, str, str, str]] = [
    ("list store saves without its check (version 5's save)", INTERNAL,
     "            if self._blocked(reservation.room, reservation.stay):\n"
     "                raise OverlapRejected(REFUSED.format(room=reservation.room.number))\n", ""),
    ("SQLite without the no-overlap insert trigger", "db/sqlite/init.sql",
     "BEFORE INSERT ON reservations\nWHEN NEW.status = 'Confirmed' AND EXISTS",
     "BEFORE INSERT ON reservations\nWHEN 0 AND EXISTS"),
    ("reserve no longer turns OverlapRejected into Unavailable", BOOKING,
     "        except OverlapRejected:", "        except LookupError:"),
    ("every integrity error is called a full room", INTERNAL,
     "    if isinstance(error, sqlite3.IntegrityError):\n        return (",
     "    if isinstance(error, sqlite3.IntegrityError):\n        return True or ("),
    ("ids from counting rows again", INTERNAL,
     "        number = self._scalar(NEXT_ID_SQLITE if self._sqlite else NEXT_ID_POSTGRES)",
     "        number = 101 + self.count()"),
    ("PostgreSQL INSERT without the savepoint", INTERNAL,
     "            self._rows(SAVEPOINT)\n", ""),
    ("no retry after a PostgreSQL deadlock", INTERNAL,
     "and attempt < INSERT_ATTEMPTS:", "and attempt < 1:"),
    ("the exclusion constraint left out of db/postgres/init.sql", "db/postgres/init.sql",
     "CONSTRAINT reservations_no_overlap EXCLUDE", "CONSTRAINT reservations_maybe_overlap EXCLUDE"),
    ("the list store's id counter outside its lock", INTERNAL,
     "        with self._lock:\n            self._last_number += 1\n            return f\"R{self._last_number}\"",
     "        number = self._last_number + 1\n        __import__('time').sleep(0.001)\n"
     "        self._last_number = number\n        return f\"R{number}\""),
]


def run(project: Path) -> None:
    print(f"Unchanged copy: {suite(project, None)}")
    caught = 0
    for number, (name, relative, old, new) in enumerate(MUTATIONS, start=1):
        result = suite(project, (relative, old, new))
        failed = "failed" in result
        caught += failed
        print(f"Mutation {number}: {name}\n    -> {result}  {'CAUGHT' if failed else 'NOT CAUGHT'}")
    print(f"\n{caught} of {len(MUTATIONS)} mutations caught by the test suite.")


def suite(project: Path, mutation: tuple[str, str, str] | None) -> str:
    with tempfile.TemporaryDirectory(prefix="p09-mutant-") as folder:
        copy = Path(folder) / "hotel-booking"
        shutil.copytree(project, copy, ignore=shutil.ignore_patterns("__pycache__", ".mypy_cache", "*.sqlite3"))
        practices = Path(folder) / "practices"  # the UML test reads the P09 class diagram next to the project
        shutil.copytree(project.parent / "practices", practices, ignore=shutil.ignore_patterns("__pycache__"))
        if mutation is not None:
            relative, old, new = mutation
            target = copy / relative
            text = target.read_text(encoding="utf-8")
            assert text.count(old) == 1, f"mutation anchor not found once in {relative}: {old!r}"
            target.write_text(text.replace(old, new), encoding="utf-8")
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x", "--no-header", "-rN"],
                              cwd=copy, capture_output=True, text=True, timeout=900)
        lines = [line for line in done.stdout.splitlines() if " passed" in line or " failed" in line or "error" in line]
        failing = [line for line in done.stdout.splitlines() if line.startswith("_") and line.endswith("_")]
        where = f" (first: {failing[0].strip('_ ')})" if failing else ""
        return (lines[-1].strip() if lines else done.stdout.strip()[-200:]) + where


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve())
