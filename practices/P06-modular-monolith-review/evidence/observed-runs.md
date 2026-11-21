# Observed runs — P06

**Label:** Observed — every block below is real output copied from the run (full logs in
[logs/](logs/)). Absolute paths are shortened to `<portfolio>/`.
**Environment:** Linux container (kernel 6.18), Python 3.13.18, pytest 9.1.1, mypy (strict), Mermaid
CLI 11.16.0 with headless Chromium. **Run date:** 2026-11-21 (portfolio build). **Working
directory:** `hotel-booking/` unless stated. My Mac was not used; re-running there (and
`lint-imports`) is in the README checklist.

The moves followed the activity sheet's order and the checks ran **after every move**. "Before" is
the P04 code (version 2); a copy of it was kept outside the portfolio for O9.

## O1 · Step 1: the safety net before any move

```text
$ python3 -m unittest -v
...
Ran 8 tests in 0.004s
OK
$ python3 -m pytest -q -p no:cacheprovider
82 passed in 1.69s
$ python3 -m mypy
Success: no issues found in 10 source files
```

Demo: the nine lines ([b1-demo](logs/b1-demo.txt)). Race ([b1-race](logs/b1-race.txt)):

```text
Confirmed reservations for R7 on 12-14 Nov: 2
Double booking! Both requests checked before either one saved.
```

P05 document checks: 26 passed ([b1-p05checks](logs/b1-p05checks.txt)).

## O2 · Step 2: the name clash

Four empty packages, with `hotel_booking/notifications/` next to the old `notifications.py`
([m1-red-name-clash](logs/m1-red-name-clash.txt)):

```text
      1 FAILED (errors=8)
      8 ImportError: cannot import name 'NotificationSender' from 'hotel_booking.notifications' (<portfolio>/hotel-booking/hotel_booking/notifications/__init__.py)
```

The package shadows the module. Without the `notifications/` folder (created later, in move 3.2,
together with deleting `notifications.py`): `Ran 8 tests … OK` ([m1-green](logs/m1-green.txt)).

## O3 · Steps 3–4: after every move

Each log runs `python3 -m unittest test_booking_service -v` and diffs the demo against O1:

| Move | Log | 8 tests | Demo diff |
|---|---|---|---|
| 3.1 Rooms | [m2-rooms](logs/m2-rooms.txt) | OK | no difference |
| 3.2 + 3.3 Notifications + Confirmation | [m3-notifications](logs/m3-notifications.txt) | OK | no difference |
| 4.1 Reservations | [m4-reservations](logs/m4-reservations.txt) | OK | no difference |
| 4.2 Payments | [m5-payments](logs/m5-payments.txt) | OK | no difference |

Classes per file after move 4.2 (end of [m5-payments](logs/m5-payments.txt)): the package root
`__init__.py` and `demo.py` define 0 classes; all 19 classes are in the four module folders.

## O4 · Step 5: who names internal code

```text
$ grep -rn "import.*internal\|internal import" hotel_booking --include=*.py
hotel_booking/__init__.py:11:modules may import. Its ``internal.py`` holds the classes that keep that

$ grep -rn "internal import" main.py tests test_booking_service.py   # who does name internal code
main.py
test_booking_service.py
tests/conftest.py
tests/test_architecture.py
tests/test_modules.py
tests/test_sequences.py
tests/test_substitution.py
```

The one hit inside the package is a docstring. (`tests/test_architecture.py` matches because its
self-tests contain bad import lines as strings.) Log: [s5-internal-search](logs/s5-internal-search.txt).

## O5 · Step 6: the three contracts

```text
$ python3 -m tests.test_architecture
Analyzed 13 files, 14 dependencies.
Reservations uses only the public contracts of other modules KEPT
Rooms does not depend on any other module KEPT
Payments and Notifications do not depend on Reservations KEPT

Contracts: 3 kept, 0 broken.
(exit code 0)
```

([f-contracts](logs/f-contracts.txt).) `lint-imports` could not be run: `ModuleNotFoundError: No
module named 'importlinter'` and `pip download import-linter` → `No matching distribution found`
([f-importlinter-unavailable](logs/f-importlinter-unavailable.txt)).

## O6 · Step 7: broken on purpose

Prediction (written first): only rule 1 fails, naming `hotel_booking.reservations.booking` and
`hotel_booking.notifications.internal`; the 8 tests stay green. Result ([s7-red](logs/s7-red.txt)):

```text
$ python3 -m unittest test_booking_service    # behaviour: still green
Ran 8 tests in 0.004s
OK
$ python3 main.py | tail -1                     # the app still runs
Confirmation emails sent: 2

$ python3 -m tests.test_architecture           # lint-imports look-alike
Analyzed 13 files, 15 dependencies.
Reservations uses only the public contracts of other modules BROKEN
Rooms does not depend on any other module KEPT
Payments and Notifications do not depend on Reservations KEPT

Reservations uses only the public contracts of other modules BROKEN

hotel_booking.reservations.booking is not allowed to import hotel_booking.notifications.internal:
-   hotel_booking.reservations.booking -> hotel_booking.notifications.internal (l.29)

Contracts: 2 kept, 1 broken.
(exit code 1)

$ python3 -m pytest -q -p no:cacheprovider tests/test_architecture.py
FAILED tests/test_architecture.py::test_contract_is_kept[reservations-uses-contracts-only]
FAILED tests/test_architecture.py::test_no_module_imports_another_modules_internal_code
2 failed, 11 passed in 0.12s
```

Whole suite: `3 failed, 115 passed` (the third is P04's `test_booking_rules_name_only_the_promises`).
After removing the line ([s7-green](logs/s7-green.txt)):

```text
sha256 of hotel_booking/reservations/booking.py before the break: c3afa837b0d503ac8f0a0bae9e25a2f465d46130999ce213d150b6feb77541b3
sha256 after removing the line:                                 c3afa837b0d503ac8f0a0bae9e25a2f465d46130999ce213d150b6feb77541b3
Contracts: 3 kept, 0 broken.
118 passed in 1.74s
```

## O7 · All three rules broken on a copy

`python3 -I practices/P06-modular-monolith-review/evidence/break_the_border.py hotel-booking`
([s7-all-rules](logs/s7-all-rules.txt)) — each case adds one line to a throw-away copy:

| Case | Bad line | 8 tests | Contracts | Architecture tests |
|---|---|---|---|---|
| Rule 1 | `reservations/booking.py:29` imports `notifications.internal` | OK | 2 kept, 1 broken (rule 1) | 2 failed, 11 passed |
| Rule 2 | `rooms/catalog.py:6` imports `reservations.domain` | OK | 2 kept, 1 broken (rule 2) | 1 failed, 12 passed |
| Rule 3 | `notifications/internal.py:10` imports `reservations.domain.Reservation` | OK | 2 kept, 1 broken (rule 3) | 1 failed, 12 passed |

In every case the behaviour tests stay green: only the architecture checks see the structural
problem.

## O8 · Step 8: after

```text
$ python3 -m unittest -v
Ran 8 tests in 0.004s
OK
$ diff <(python3 main.py) <(tail -n +2 b1-demo.txt)
(no difference)
$ python3 main.py --race
Maya and Omar both book R7 for 12-14 Nov at the same moment...
Maya: Accepted R101
Omar: Accepted R102
Confirmed reservations for R7 on 12-14 Nov: 2
Double booking! Both requests checked before either one saved.
$ for i in $(seq 20); do python3 main.py --race | grep "Confirmed reservations"; done | sort | uniq -c
     20 Confirmed reservations for R7 on 12-14 Nov: 2
$ python3 -m pytest -v -p no:cacheprovider
============================= 118 passed in 2.01s ==============================
$ python3 -m mypy
Success: no issues found in 19 source files
```

Test count by file ([f-pytest](logs/f-pytest.txt)): `test_booking_service.py` 8 (the course's),
`tests/test_uml_conformance.py` 29, `test_domain.py` 17, `test_booking_service.py` (pytest) 14,
`test_architecture.py` 13, `test_modules.py` 13, `test_substitution.py` 10, `test_sequences.py` 6,
`test_demo_and_race.py` 5, `test_dependency_rule.py` 3 — 118. Before P06: 82 (UML 20, substitution 9);
new: `test_architecture.py` 13, `test_modules.py` 13, UML +9 (more classes, module checks),
substitution +1 (the P04 counter-example split into a contained sender and a bad store).

## O9 · Before and after scenario (version 2 vs version 3)

[compare_behaviour.py](compare_behaviour.py) prints accepted / full / error answers, cancellations,
searches, the confirmations sent and every saved record. Run on the P04 copy and on the project
([cmp-v2-v3](logs/cmp-v2-v3.txt)):

```text
# shape found: version 2 (flat package)      ... and ...      # shape found: version 3 (four modules)
accepted Maya R7 12-14                -> Accepted R101
full     Omar R7 13-15                -> Unavailable
...
confirmations sent: 3
saved records: 3
  R101 Maya R7 2026-11-12..2026-11-14 Cancelled
  R102 Nora R7 2026-11-14..2026-11-16 Confirmed
  R103 Omar R8 2026-11-12..2026-11-14 Confirmed

$ diff <v2 output> <v3 output>
(no difference)
```

## O10 · S5: SMS instead of email on the P06 structure

On a copy, the wiring's import was changed to `SmsNotificationSender`
([s5-sms-swap](logs/s5-sms-swap.txt)):

```text
diff -r -x __pycache__ -x .mypy_cache before/main.py after/main.py
18c18
< from hotel_booking.notifications.internal import EmailNotificationSender
---
> from hotel_booking.notifications.internal import SmsNotificationSender as EmailNotificationSender  # S5: SMS instead of email
files changed: 1
...
OK
Contracts: 3 kept, 0 broken.
```

(The alias keeps the experiment to one line; a real change would also rename the variable — still
only `main.py`.) The demo text still says "emails" because it is the demo's wording.

## O11 · Diagrams and document checks

`mmdc` with `-p puppeteer-config.linux-build.json` (Chromium at `/opt/pw-browsers/chromium-1243/…`,
`--no-sandbox`): `modules.mmd`, `module-dependencies.mmd`, `class-diagram.mmd` → exit 0 each
([mmdc](logs/mmdc.txt)).

```text
$ python3 -m pytest -v -p no:cacheprovider practices/P06-modular-monolith-review/checks
...
============================== 23 passed in 0.80s ==============================
$ python3 -m pytest -q -p no:cacheprovider practices/P05-domain-context-boundaries/checks
26 passed in 0.17s
```

The 23 P06 checks cover the draw.io pages (Context map + Modules shape), the Mermaid Modules page,
the as-built diagram against the real imports, SVGs present, the five design-notes sections, the
ADR sections, the finished folder layout, the copied P05 docs and every relative link
([f-p06checks](logs/f-p06checks.txt)). The P05 checks still pass because they look up every code
name of the Words table recursively in `hotel_booking/` ([f-p05checks](logs/f-p05checks.txt)).
