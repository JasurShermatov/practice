# P06 worksheet — answers to every "Your turn"

Activity sheet: *P06 · Turn the four contexts into modules with checked borders* (the Student
explanation, Student notes and Presentation notes are the same text). Python track. Every result
below is **Observed** unless marked otherwise; logs are in [evidence/logs/](evidence/logs/), the
index in [evidence/Index.md](evidence/Index.md).

## Your turn · open your project

1. Opened `hotel-booking/` (end of P04, version 2).
2. `docs/contexts.md` next to the code: P05 had left it in its practice folder (P04 was editing the
   project at the time), so the first action of P06 was the copy P05's README asks for —
   `quality-scenarios.md`, `contexts.md`, `l03-notes.md` → `hotel-booking/docs/`. Only the diagram
   links had to change (they pointed at `../diagrams/` of the P05 folder); a "P06 status" section
   was appended to the project copy of `contexts.md`. A check
   ([checks/test_p06_docs.py](checks/test_p06_docs.py) `test_copied_p05_docs_keep_their_content`)
   confirms every P05 heading survived the copy, and every link resolves.
3. `docs/design-notes.md` got the heading `# P06 design notes`.

## Step 1 · Lock the behaviour — run the safety net

| Check | Command | Result before any move | Log |
|---|---|---|---|
| Tests | `python -m unittest -v` | Ran 8 tests — OK (full suite `pytest`: 82 passed; `mypy`: no issues) | [b1-unittest](evidence/logs/b1-unittest.txt), [b1-pytest](evidence/logs/b1-pytest.txt) |
| Demo | `python main.py` | The nine lines, `Confirmation emails sent: 2` | [b1-demo](evidence/logs/b1-demo.txt) |
| Race | `python main.py --race` | `Confirmed reservations for R7 on 12-14 Nov: 2` — Double booking! | [b1-race](evidence/logs/b1-race.txt) |

Written to `design-notes.md` → `## Before` (three lines). A copy of the whole project at this point
was kept aside (outside the portfolio) for the before/after comparison in Step 8.

## Step 2 · Create the four module folders

- Created `hotel_booking/rooms/`, `reservations/`, `payments/` with an empty `__init__.py` each.
- **Finding (Observed):** creating `hotel_booking/notifications/` *while `notifications.py` still
  existed* broke all 8 tests: `ImportError: cannot import name 'NotificationSender' from
  'hotel_booking.notifications' (…/notifications/__init__.py)` — a package beats a module of the same
  name. P05's plan had predicted this ([Implications § 2](../P05-domain-context-boundaries/Implications-for-the-code.md#2-where-todays-classes-go)).
  So the `notifications/` folder was created in move 3.2, in the same step that deleted
  `notifications.py`. Log: [m1-red-name-clash](evidence/logs/m1-red-name-clash.txt) → [m1-green](evidence/logs/m1-green.txt) (8 OK).
- The table "The four modules" is in `design-notes.md` → `## Modules`, with this project's names.

## Step 3 · Move Rooms, then Notifications

Tests (the course's 8) and the demo `diff` after each numbered move:

| Move | What changed | 8 tests | Demo | Log |
|---|---|---|---|---|
| 3.0 | `hotel_booking/__init__.py` → docstring only (no re-exports); imports switched to the module files | — | — | (part of 3.1) |
| 3.1 | `rooms/catalog.py` (`Room`, `RoomCatalog`), `rooms/internal.py` (`InMemoryRoomCatalog`), `rooms/__init__.py`; `Room` deleted from `domain.py`; imports in Reservation, store, BookingService, main, tests fixed | OK | same | [m2-rooms](evidence/logs/m2-rooms.txt) |
| 3.2 + 3.3 | `notifications.py` deleted; `notifications/__init__.py` (`Confirmation`, `NotificationSender`), `notifications/internal.py` (email + SMS senders); `BookingService` sends a `Confirmation`; the fake sender receives a `Confirmation` and records `confirmation.reservation_id` | OK | same | [m3-notifications](evidence/logs/m3-notifications.txt) |

While the moves were in progress the pytest suite in `tests/` still imported from the old package
root, so after each move only the course's 8 tests were run (as the activity sheet does); the
pytest suite was adapted in Step 5 and has been green since.

## Step 4 · Move Reservations, then add Payments

| Move | What changed | 8 tests | Demo | Log |
|---|---|---|---|---|
| 4.1 | `reservations/domain.py` (moved `domain.py`), `reservations/booking.py` (`ReservationStore`, `BookingOutcome`, `BookingResult`, `BookingService`), `reservations/internal.py` (`InMemoryReservationStore`), `reservations/__init__.py`; old `domain.py`, `booking.py`, `stores.py` deleted; the R6 test's logger name became `hotel_booking.reservations.booking` | OK | same | [m4-reservations](evidence/logs/m4-reservations.txt) |
| 4.2 | `payments/__init__.py` (`PaymentStatus`, `PaymentService`), `payments/internal.py` (`SimulatedPaymentService`). Nothing calls it (P17). | OK | same | [m5-payments](evidence/logs/m5-payments.txt) |
| 4.5 | "No class left in its old place": the only files outside the module folders are `hotel_booking/__init__.py` (0 classes) and `demo.py` (0 classes) | — | — | end of [m5-payments](evidence/logs/m5-payments.txt); now a test: `test_every_class_lives_in_one_of_the_four_modules` |

### Where every P04 class is now

| P04 class (file) | Module | File now | Public or internal |
|---|---|---|---|
| `Room` (`domain.py`) | Rooms | `rooms/catalog.py` | Public |
| new: `RoomCatalog`, `InMemoryRoomCatalog` | Rooms | `rooms/catalog.py`, `rooms/internal.py` | Public, internal |
| `DateRange`, `Guest`, `Reservation`, `ReservationStatus` (`domain.py`) | Reservations | `reservations/domain.py` | Public |
| `BookingService`, `BookingResult`, `BookingOutcome` (`booking.py`) | Reservations | `reservations/booking.py` | Public |
| `ReservationStore` (`stores.py`) | Reservations | `reservations/booking.py` | Public (the promise the wiring plugs a store into) |
| `InMemoryReservationStore` (`stores.py`) | Reservations | `reservations/internal.py` | Internal |
| new: `PaymentStatus`, `PaymentService`, `SimulatedPaymentService` | Payments | `payments/__init__.py`, `payments/internal.py` | Public, public, internal |
| new: `Confirmation`; `NotificationSender` (`notifications.py`) | Notifications | `notifications/__init__.py` | Public |
| `EmailNotificationSender`, `SmsNotificationSender` (`notifications.py`) | Notifications | `notifications/internal.py` | Internal |

## Step 5 · Finish the wiring

1. `main.py` compared with the completed example: same choices, written as `build_app()` (kept from
   P04 so the tests can build the app the same way).
2. The catalog is created in the wiring — `InMemoryRoomCatalog(HOTEL_ROOMS)` — and
   `catalog.all()` is passed into `BookingService` instead of the room tuple.
3. Search of the module folders for `internal` imports: **no match** (the only hit is a docstring
   in `hotel_booking/__init__.py`). Files that do import internal code: `main.py` and the tests only
   ([s5-internal-search](evidence/logs/s5-internal-search.txt); `tests/test_architecture.py` matches
   because its self-tests contain bad import lines as strings). One extra fix was needed here:
   `demo.py` had a type hint naming `EmailNotificationSender`; `run_demo` now receives
   `lambda: email.sent`, so `demo.py` names contracts only.
4. Demo: the same nine lines (`diff` against Step 1: no difference) — [f-demo](evidence/logs/f-demo.txt).

The pytest suite was adapted at this point (imports, the spies' and fakes' `Confirmation`
argument, the UML test re-pointed at the P06 diagram, the P04 Liskov counter-example replaced —
every change is described in the docstring of the test module it touches and listed in the
[README](README.md#what-changed-in-the-code-version-2--3)).

## Step 6 · Add the three checks

1. Install line `python -m pip install import-linter`: **not possible here** — PyPI is unreachable
   ([f-importlinter-unavailable](evidence/logs/f-importlinter-unavailable.txt)). To do on the
   student's Mac. Substitute (see README "Substitutions"): `tests/test_architecture.py`, standard
   library only.
2. The contracts are in [`hotel-booking/.importlinter`](../../hotel-booking/.importlinter) (INI
   format, the file `lint-imports` reads by default). `tests/test_architecture.py` parses that
   same file, so there is one source of truth.
3. Result: 8 tests OK, then **"Contracts: 3 kept, 0 broken."**
   ([f-unittest](evidence/logs/f-unittest.txt), [f-contracts](evidence/logs/f-contracts.txt)).
4. `design-notes.md` → `## Architecture rules`: the three rules in plain words.

## Step 7 · Break it, read it, undo it

1. Added the line to `hotel_booking/reservations/booking.py` (line 29):
   `from hotel_booking.notifications.internal import EmailNotificationSender  # step 7: undo after the check fails`
2. **Prediction (written before running):** only rule 1 fails; the message names
   `hotel_booking.reservations.booking` and `hotel_booking.notifications.internal`; the 8 booking
   tests stay green because the app still works.
3. **Red result** ([s7-red](evidence/logs/s7-red.txt)) — prediction correct:

   ```text
   Reservations uses only the public contracts of other modules BROKEN
   Rooms does not depend on any other module KEPT
   Payments and Notifications do not depend on Reservations KEPT

   hotel_booking.reservations.booking is not allowed to import hotel_booking.notifications.internal:
   -   hotel_booking.reservations.booking -> hotel_booking.notifications.internal (l.29)

   Contracts: 2 kept, 1 broken.
   ```

   The 8 tests: OK; `python main.py` still ran. In the full pytest run 3 tests failed: the rule-1
   contract, the extra "no module imports another module's internal code" check, and P04's
   `test_booking_rules_name_only_the_promises` (booking.py now names a concrete sender) — three
   independent checks saw the same shortcut.
4. Removed the line: all green again, and `booking.py` has the same SHA-256 as before the break
   ([s7-green](evidence/logs/s7-green.txt)).
5. `design-notes.md` → `## Broken on purpose`: one line, rule 1, and what the message named.

Extra: [evidence/break_the_border.py](evidence/break_the_border.py) repeats the experiment for all
three rules on a throw-away copy ([s7-all-rules](evidence/logs/s7-all-rules.txt)). Rule 2 (Rooms
imports Reservations) and rule 3 (Notifications imports `Reservation` — the circle P06 removed)
each turn exactly their own contract red while the 8 behaviour tests stay green.

## Step 8 · Prove, decide and draw

1. Ran everything ([f-unittest](evidence/logs/f-unittest.txt), [f-contracts](evidence/logs/f-contracts.txt),
   [f-demo](evidence/logs/f-demo.txt), [f-race](evidence/logs/f-race.txt), [f-race20](evidence/logs/f-race20.txt)):
   8 tests + 3 contracts kept; the nine demo lines unchanged; the race still double-books (20 of 20
   runs). Full suite 118 passed, mypy strict clean ([f-pytest](evidence/logs/f-pytest.txt),
   [f-mypy](evidence/logs/f-mypy.txt)). The scenario script gives byte-identical accepted / full /
   error answers and saved records for version 2 and version 3 ([cmp-v2-v3](evidence/logs/cmp-v2-v3.txt)).
2. `design-notes.md` → `## After`: three lines, the same as `## Before`.
3. [`docs/adr-001-modular-monolith.md`](../../hotel-booking/docs/adr-001-modular-monolith.md): ADR-001
   written in my own words (same decision as the course's; more alternatives and consequences).
4. Page "Modules" in [`docs/diagrams.drawio`](../../hotel-booking/docs/diagrams.drawio) (second page,
   after "Context map"): five boxes (Reservations green, the internal sender purple and dashed),
   three "Uses", one "Implements", the red "Forbidden" arrow — checked by
   `test_modules_page_has_the_required_shape`. Mermaid twin: [diagrams/modules.mmd](diagrams/modules.mmd)
   → [.svg](diagrams/modules.svg).

### Your P06 checklist

| File or page | It is finished when | Status |
|---|---|---|
| Code | Every class lives in one of the four modules; main is the only app file that names internal code | Done — `test_every_class_lives_in_one_of_the_four_modules`, `test_no_module_imports_another_modules_internal_code`, `test_only_main_creates_concrete_classes_of_the_modules` |
| Checks | 8 tests and 3 import-linter contracts | Done — 8 OK; 3 contracts kept by the stdlib checker. `lint-imports` itself: **to run on the Mac** |
| Demo and race | Same nine lines; the race still double-books | Done — `diff` empty; 20/20 double bookings |
| docs/design-notes.md | P06 sections Before, Modules, Architecture rules, Broken on purpose, After | Done — `test_design_notes_have_the_five_p06_sections` |
| docs/adr-001-modular-monolith.md | ADR-001 is there | Done — `test_adr_001_has_status_and_the_five_sections` |
| diagrams.drawio · Modules | 5 boxes, 4 dashed arrows and the red forbidden one | Done (XML checked; not opened in the draw.io app here) |
