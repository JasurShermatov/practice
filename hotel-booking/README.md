# hotel-booking

The course project of *Advanced Software Design & Architecture*: a small fictional hotel (rooms R7
and R8) that takes bookings on its website and at the reception desk. This folder is **one growing
codebase**; each practice evolves it and keeps earlier behaviour (and tests) working.

| Version | Practice | What it adds |
|---|---|---|
| 1 | [P03](../practices/P03-hotel-domain-uml/README.md) | Domain classes and the booking workflow from the P03 UML; in memory; demo + race demo |
| 2 | [P04](../practices/P04-refactor-reservation/README.md) | SOLID refactor, same behaviour: `BookingService` depends only on the `ReservationStore` and `NotificationSender` protocols; `main.py` is the composition root; 8 `unittest` tests. New after the refactor: R6 (a failed confirmation keeps the booking) and `SmsNotificationSender` |

Planned by the course (not implemented yet): P05/P06 business areas and modular monolith, P07 HTTP
API + database (a PostgreSQL store that keeps the `ReservationStore` promise), P08 cache, P09
concurrency fix for the race, P10 asynchronous notifications.

## Requirements

- Python 3.12 or newer (developed and tested on 3.13). Standard library only at runtime.
- Nothing to install for the course's P04 tests (`unittest` is built in).
- `pytest` (full suite) and `mypy` (type check) from `requirements.txt`.

```bash
cd hotel-booking
python3 -m venv .venv && source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

## Run

```bash
python main.py           # the normal demo: nine lines proving R1-R4
python main.py --race    # two guests book R7 for the same nights at the same moment
python -m unittest -v    # the course's 8 P04 tests (test_booking_service.py)
python -m pytest         # everything: the 8 unittest tests + the pytest suite in tests/ (82 tests)
python -m mypy           # strict type check, incl. that every store/sender keeps its protocol
```

Expected demo output (identical in versions 1 and 2):

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

## Layout

```text
hotel-booking/
├── main.py                     composition root: builds the app (build_app), runs demo or --race
├── test_booking_service.py     P04: the course's 8 unittest tests + FakeNotificationSender
├── hotel_booking/
│   ├── domain.py               DateRange, Guest, Room, ReservationStatus, Reservation (unchanged since P03)
│   ├── stores.py               ReservationStore (protocol), InMemoryReservationStore
│   ├── notifications.py        NotificationSender (protocol), EmailNotificationSender, SmsNotificationSender
│   ├── booking.py              BookingOutcome, BookingResult, BookingService (knows only the protocols)
│   └── demo.py                 the classroom scenario (R7, R8, Maya, Omar, Nora) and the race
├── tests/                      pytest suite (P03, kept green; P04 additions marked)
│   ├── test_domain.py          DateRange half-open rule, Reservation status/encapsulation
│   ├── test_booking_service.py R1-R5 and the R3 invariant (one request at a time)
│   ├── test_sequences.py       message order of each sequence diagram, via spies (+ R6 in P04)
│   ├── test_demo_and_race.py   exact demo output; race known defect + control case
│   ├── test_uml_conformance.py code == P04 class diagram (classes, interfaces, implements, links)
│   ├── test_dependency_rule.py P04: booking.py names no concrete helper; only main.py creates them
│   └── test_substitution.py    P04: any sender/store that keeps the promise gives the same records
├── docs/
│   ├── requirements.md         R1-R6 with Check and Proof lines, invariant
│   ├── design-notes.md         P03 sections, then "P04 design notes" (Refactoring, What our code breaks, Proof, ...)
│   └── l02-notes.md            L02 exit-check answers
├── pyproject.toml              pytest / mypy configuration
└── requirements.txt
```

## Design in one paragraph

`BookingService` holds the booking rules and runs each request: `reserve` validates the stay
(`DateRange.is_valid`), asks the store `has_overlap`, then creates a `Reservation`, saves it, asks
the sender to confirm it and returns a `BookingResult`. Since P04 it knows its helpers only as two
promises — `ReservationStore` and `NotificationSender` (`typing.Protocol`) — and `main.py` decides
which real classes keep them (today `InMemoryReservationStore` and `EmailNotificationSender`).
If the confirmation fails, the saved booking stays `Accepted` and the result says
`notification_failed=True` (R6). The overlap rule is written once, in `DateRange.overlaps`; a
`Reservation` decides whether it `blocks` a request and owns its status (changed only by
`cancel()`). UML and code are kept identical: `tests/test_uml_conformance.py` fails if a class,
member, interface, "implements" line, enum value or link drifts from
`practices/P04-refactor-reservation/uml/class-diagram.mmd` (a later practice that changes the design
points `CLASS_DIAGRAM` at its own diagram).

## Known limitations of version 2

- **Race condition (R3 under concurrency):** check (`has_overlap`) and act (`save`) are separate
  steps. Fixed in P09; pinned by `test_race_double_books_r7_known_defect`.
- In-memory only: restarting clears all reservations.
- The demo pause `slow_step_seconds` still sits inside `reserve()` (0 in normal use); kept so the race
  can be shown, removed when the database arrives.
- R6 reports a failed confirmation but nothing resends it yet (a retry/outbox is P10's topic).
- The protocols are checked structurally by mypy and by `test_uml_conformance.py`; Python does not
  stop a class with the right method names but the wrong behaviour (`test_substitution.py` shows one).
- `reserve` does not check that the room belongs to the hotel's room list, and reservation ids
  (`R101`, `R102`, …) come from the store's row count — fine for one process, not for several.
