"""Break the cache on purpose, on throw-away copies, and show which tests notice (P08 Step 6, item 3).

    python3 -I practices/P08-cache-scale-experiment/evidence/break_the_cache.py hotel-booking

The activity sheet asks: remove the invalidate line from POST, run the tests, watch the second new
cache test fail, put it back. This does exactly that - and the same for every other promise of
the cache - on a copy of the project, so the project itself is never changed. For each mutation
it runs ``python -m unittest`` (the course's 14 tests) and the P08 pytest files, and prints which
tests fail. A test that cannot fail proves nothing.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

P08_TESTS = ["tests/test_cache.py", "tests/test_api_cache.py", "tests/test_openapi_contract.py",
             "tests/test_cache_wiring.py", "tests/test_architecture.py"]

MUTATIONS: list[tuple[str, str, str, str]] = [
    # (what, file, old text, new text)
    ("Step 6 item 3: the invalidate line (and its if) is removed from POST",
     "hotel_booking/api.py",
     "        if result.outcome is BookingOutcome.ACCEPTED:\n"
     "            await invalidate_cache(cache, stats)  # after the unit of work: the booking is committed\n", ""),
    ("the invalidate line is removed from DELETE",
     "hotel_booking/api.py",
     "        await invalidate_cache(cache, stats)  # after the unit of work: the cancel is committed\n", ""),
    ("the version is raised BEFORE the booking is saved",
     "hotel_booking/api.py",
     "        result = await in_unit_of_work(unit_of_work, lambda service: service.reserve(guest, room, stay))\n"
     "        if result.outcome is BookingOutcome.ACCEPTED:\n"
     "            await invalidate_cache(cache, stats)  # after the unit of work: the booking is committed\n",
     "        await invalidate_cache(cache, stats)\n"
     "        result = await in_unit_of_work(unit_of_work, lambda service: service.reserve(guest, room, stay))\n"),
    ("booking reads the cache (it asks the cached search whether the room is free)",
     "hotel_booking/api.py",
     "        guest, stay = Guest(body.guest_name, body.guest_email), DateRange(check_in, check_out)\n",
     "        guest, stay = Guest(body.guest_name, body.guest_email), DateRange(check_in, check_out)\n"
     "        free, _ = await search_free_rooms(stay, rooms_by_number, unit_of_work, cache, stats)\n"),
    ("the TTL becomes 300 seconds",
     "hotel_booking/api_cache.py", "TTL_SECONDS = 30\n", "TTL_SECONDS = 300\n"),
    ("the key forgets the version",
     "hotel_booking/api_cache.py",
     'return f"{KEY_PREFIX}:v{self.version()}:{check_in.isoformat()}:{check_out.isoformat()}"',
     'return f"{KEY_PREFIX}:v0:{check_in.isoformat()}:{check_out.isoformat()}"'),
    ("a hit is not counted",
     "hotel_booking/api.py", '        stats.add("cacheHits")\n', ""),
    ("the contract forgets GET /stats",
     "docs/openapi.yaml", "  /stats:\n    get:\n", "  /x-stats-removed:\n    get:\n"),
    ("the cache imports a module (Rooms)",
     "hotel_booking/api_cache.py", "from typing import Protocol\n",
     "from typing import Protocol\n\nfrom hotel_booking.rooms import Room  # noqa: F401\n"),
]


def copy(project: Path) -> Path:
    target = Path(tempfile.mkdtemp(prefix="break-cache-")) / "hotel-booking"
    shutil.copytree(project, target, ignore=shutil.ignore_patterns("__pycache__", "*.sqlite3", ".mypy_cache"))
    return target


def run(project: Path) -> tuple[bool, list[str], str, str]:
    unit = subprocess.run([sys.executable, "-m", "unittest"], cwd=project, capture_output=True, text=True)
    unit_failed = [line.split()[1] for line in unit.stderr.splitlines() if line.startswith(("FAIL:", "ERROR:"))]
    unit_summary = [line for line in unit.stderr.splitlines() if line.startswith(("Ran ", "OK", "FAILED"))]
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", *P08_TESTS],
                           cwd=project, capture_output=True, text=True)
    failed = [line.removeprefix("FAILED ").split(" - ")[0] for line in tests.stdout.splitlines()
              if line.startswith("FAILED ")]
    green = unit.returncode == 0 and tests.returncode == 0
    return green, [f"unittest {name}" for name in unit_failed] + failed, " / ".join(unit_summary), \
        tests.stdout.strip().splitlines()[-1]


def main(argv: list[str]) -> int:
    project = Path(argv[0]).resolve()
    green, _, unit, tests = run(copy(project))
    print(f"Unchanged copy: unittest {unit}; P08 pytest files: {tests}")
    missed = not green
    for number, (what, file, old, new) in enumerate(MUTATIONS, start=1):
        mutated = copy(project)
        path = mutated / file
        text = path.read_text(encoding="utf-8")
        assert text.count(old) == 1, f"mutation {number}: the text to change is not unique in {file}"
        path.write_text(text.replace(old, new), encoding="utf-8")
        green, failed, unit, tests = run(mutated)
        print(f"\n{number}. {what}\n   changed {file}\n   unittest: {unit}\n   pytest:   {tests}")
        for name in failed:
            print(f"   FAILED {name}")
        missed |= green
    print("\nEvery mutation was caught; the project itself was not changed." if not missed
          else "\nA mutation was NOT caught - see above.")
    return 1 if missed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
