# hotel-booking

The course project of *Advanced Software Design & Architecture*: a small fictional hotel (rooms R7
and R8) that takes bookings on its website and at the reception desk. This folder is **one growing
codebase**; each practice evolves it and keeps earlier behaviour (and tests) working.

| Version | Practice | What it adds |
|---|---|---|
| 1 | [P03](../practices/P03-hotel-domain-uml/README.md) | Domain classes and the booking workflow from the P03 UML; in memory; demo + race demo |
| 2 | [P04](../practices/P04-refactor-reservation/README.md) | SOLID refactor, same behaviour: `BookingService` depends only on the `ReservationStore` and `NotificationSender` protocols; `main.py` is the composition root; 8 `unittest` tests. New after the refactor: R6 (a failed confirmation keeps the booking) and `SmsNotificationSender` |
| — | [P05](../practices/P05-domain-context-boundaries/README.md) | Design only: quality scenarios, four bounded contexts, rule owners, context map (docs copied into `docs/` in P06) |
| 3 | [P06](../practices/P06-modular-monolith-review/README.md) | **Modular monolith**, same behaviour: four modules (rooms, reservations, payments, notifications), each a package with a public contract and `internal.py`; Notifications gets its own `Confirmation` message; Payments contract + simulated service; `main.py` is the only app file that names internal code; the borders are checked (`.importlinter` + `tests/test_architecture.py`); ADR-001 |

Planned by the course (not implemented yet): P07 HTTP API + database (a PostgreSQL store that keeps
the `ReservationStore` promise, plugged in through the wiring), P08 cache, P09 concurrency fix for
the race, P10 asynchronous notifications, P17 booking saga with the Payments deposit.

## Requirements

- Python 3.12 or newer (developed and tested on 3.13). Standard library only at runtime.
- Nothing to install for the course's 8 tests (`unittest` is built in) or for the border checks
  (`tests/test_architecture.py` uses only the standard library).
- `pytest` (full suite), `mypy` (type check) and `import-linter` (`lint-imports`, optional) from
  `requirements.txt`.

```bash
cd hotel-booking
python3 -m venv .venv && source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

## Run

```bash
python main.py                      # the normal demo: nine lines proving R1-R4
python main.py --race               # two guests book R7 for the same nights at the same moment
python -m unittest -v               # the course's 8 tests (test_booking_service.py)
lint-imports                        # the 3 module borders in .importlinter (needs import-linter)
python -m tests.test_architecture   # the same 3 borders, standard library only, lint-imports-style output
python -m pytest                    # everything: the 8 unittest tests + the pytest suite in tests/
python -m mypy                      # strict type check, incl. that every class keeps its protocol
```

Expected demo output (identical in versions 1, 2 and 3):

```text
Free rooms 12-14 Nov: R7, R8
Maya books R7 12-14 Nov: Accepted R101
Omar books R7 13-15 Nov: Unavailable
Nora books R7 14-16 Nov: Accepted R102
Omar books R8 15-15 Nov: InvalidDates
Free rooms 12-14 Nov: R8
Maya cancels R101: True
Free rooms 12-14 Nov: R7, R8
Confirmation emails sent: 2
```

Expected race output (a **known defect**, kept on purpose until P09 — a refactoring does not fix bugs):

```text
Maya and Omar both book R7 for 12-14 Nov at the same moment...
Maya: Accepted R101
Omar: Accepted R102
Confirmed reservations for R7 on 12-14 Nov: 2
Double booking! Both requests checked before either one saved.
```

Expected border check:

```text
Reservations uses only the public contracts of other modules KEPT
Rooms does not depend on any other module KEPT
Payments and Notifications do not depend on Reservations KEPT

Contracts: 3 kept, 0 broken.
```

## Layout

```text
hotel-booking/
├── main.py                     wiring: the only app file that names internal code (build_app), demo or --race
├── test_booking_service.py     the course's 8 unittest tests (P04) + FakeNotificationSender (receives a Confirmation)
├── .importlinter               P06: the 3 border contracts (lint-imports; also read by tests/test_architecture.py)
├── hotel_booking/
│   ├── __init__.py             docstring only - re-exports nothing
│   ├── rooms/                  Rooms: __init__.py (contract: Room, RoomCatalog), catalog.py, internal.py (InMemoryRoomCatalog)
│   ├── reservations/           Reservations: __init__.py (contract), domain.py (DateRange, Guest, Reservation, ReservationStatus),
│   │                           booking.py (ReservationStore, BookingOutcome, BookingResult, BookingService), internal.py (InMemoryReservationStore)
│   ├── payments/               Payments: __init__.py (contract: PaymentStatus, PaymentService), internal.py (SimulatedPaymentService)
│   ├── notifications/          Notifications: __init__.py (contract: Confirmation, NotificationSender), internal.py (Email/Sms senders)
│   └── demo.py                 the classroom scenario (R7, R8, Maya, Omar, Nora) and the race; uses contracts only
├── tests/                      pytest suite (P03 on; every deliberate change noted in the module docstring)
│   ├── test_domain.py          DateRange half-open rule, Reservation status/encapsulation
│   ├── test_booking_service.py R1-R5 and the R3 invariant (one request at a time)
│   ├── test_sequences.py       message order of each sequence diagram, via spies (+ R6)
│   ├── test_demo_and_race.py   exact demo output; race known defect + control case
│   ├── test_uml_conformance.py code == P06 class diagram (classes, members, interfaces, links, modules)
│   ├── test_dependency_rule.py P04: booking.py names no concrete helper; only main.py creates them
│   ├── test_substitution.py    P04: any sender/store that keeps the promise gives the same records
│   ├── test_modules.py         P06: Rooms catalog, Payments deposit, the Confirmation translation
│   └── test_architecture.py    P06: the 3 border contracts (ast import graph) + extras + self-tests
├── docs/
│   ├── requirements.md         R1-R6 with Check and Proof lines, invariant
│   ├── design-notes.md         P03, P04 and P06 sections (Before, Modules, Architecture rules, Broken on purpose, After)
│   ├── quality-scenarios.md    P05: stakeholders and S1-S6
│   ├── contexts.md             P05: words, four contexts, rule owners, context map, borders (+ P06 status)
│   ├── adr-001-modular-monolith.md   P06: why one program with four modules
│   ├── diagrams.drawio         pages "Context map" (P05) and "Modules" (P06)
│   ├── l02-notes.md, l03-notes.md    lecture exit-check answers
├── pyproject.toml              pytest / mypy configuration
└── requirements.txt
```

## Design in one paragraph

The app is one program with four modules. **Reservations** owns the booking rule:
`BookingService.reserve` validates the stay (`DateRange.is_valid`), asks its store `has_overlap`,
then creates a `Reservation`, saves it, translates it into Notifications' own `Confirmation`
(reservation id, guest email, room number, check-in, check-out) and hands that to a
`NotificationSender`; a failed send keeps the booking (`notification_failed=True`, R6). It knows
the other modules only through their contracts: `Room` from **Rooms** (the wiring passes
`InMemoryRoomCatalog.all()` in), `NotificationSender`/`Confirmation` from **Notifications**, and —
from P17 — `PaymentService` from **Payments**. Rooms, Payments and Notifications never import
Reservations, so no dependency circle can form. `main.py` is the only application file that names
internal classes. The borders are not a convention: `tests/test_architecture.py` parses every
import with `ast` and fails on any import the three contracts in `.importlinter` forbid (directly or
through other modules). UML and code are kept identical by `tests/test_uml_conformance.py`
against `practices/P06-modular-monolith-review/diagrams/class-diagram.mmd`.

## Known limitations of version 3

- **Race condition (R3/S2 under concurrency):** check (`has_overlap`) and act (`save`) are separate
  steps. Fixed in P09; pinned by `test_race_double_books_r7_known_defect`.
- In-memory only: restarting clears all reservations.
- The demo pause `slow_step_seconds` still sits inside `reserve()` (0 in normal use).
- R6 reports a failed confirmation but nothing resends it yet (P10).
- Python cannot *hide* internal code: `internal.py` is a naming convention, and the border holds
  only because the architecture tests run with every test run (CI from P25).
- `Reservation` still holds the whole `Room` from the Rooms contract (allowed by rule 1); keeping only
  the room number is noted for P07 (P05 decision D2).
- Payments exists but is not called; the 30% deposit rule (P05 card 6, decision D1) arrives with P17.
- `reserve` does not check that the room is in the catalog, and reservation ids (`R101`, …) come from
  the store's row count — fine for one process, not for several.
