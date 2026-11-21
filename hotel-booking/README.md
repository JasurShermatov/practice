# hotel-booking

The course project of *Advanced Software Design & Architecture*: a small fictional hotel (rooms R7
and R8) that takes bookings on its website and at the reception desk. This folder is **one growing
codebase**; each practice evolves it and keeps earlier behaviour (and tests) working.

| Version | Practice | What it adds |
|---|---|---|
| 1 | [P03](../practices/P03-hotel-domain-uml/README.md) | Domain classes and the booking workflow from the P03 UML; in memory; demo + race demo |

Planned by the course (not implemented yet): P04 SOLID refactor (interfaces for storage and
notification), P05/P06 business areas and modular monolith, P07 HTTP API + database, P08 cache,
P09 concurrency fix for the race, P10 asynchronous notifications.

## Requirements

- Python 3.12 or newer (developed and tested on 3.13). Standard library only at runtime.
- `pytest` for the tests (`requirements.txt`).

```bash
cd hotel-booking
python3 -m venv .venv && source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

## Run

```bash
python main.py           # the normal demo: nine lines proving R1-R4
python main.py --race    # two guests book R7 for the same nights at the same moment
python -m pytest         # all tests (config in pyproject.toml)
python -m mypy           # optional: strict type check of hotel_booking/ and main.py
```

Expected demo output:

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

Expected race output (a **known defect**, kept on purpose until P09):

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
├── main.py                     command line: demo or --race
├── hotel_booking/
│   ├── domain.py               DateRange, Guest, Room, ReservationStatus, Reservation
│   ├── stores.py               ReservationStore (in-memory list)
│   ├── notifications.py        EmailSender (simulated: counts, sends nothing)
│   ├── booking.py              BookingOutcome, BookingResult, BookingService
│   └── demo.py                 the classroom scenario (R7, R8, Maya, Omar, Nora) and the race
├── tests/
│   ├── test_domain.py          DateRange half-open rule, Reservation status/encapsulation
│   ├── test_booking_service.py R1-R5 and the R3 invariant (one request at a time)
│   ├── test_sequences.py       message order of each sequence diagram, via spies
│   ├── test_demo_and_race.py   exact demo output; race known defect + control case
│   └── test_uml_conformance.py code == class diagram (classes, members, enums, links)
├── docs/
│   ├── requirements.md         R1-R5 with Check and Proof lines, invariant
│   ├── design-notes.md         short answers per step (P03; later practices append)
│   └── l02-notes.md            L02 exit-check answers
├── pyproject.toml              pytest / mypy configuration
└── requirements.txt
```

## Design in one paragraph

`BookingService` runs each request: `reserve` validates the stay (`DateRange.is_valid`), asks
`ReservationStore.has_overlap`, then creates a `Reservation`, saves it, asks `EmailSender` to send
the confirmation and returns a `BookingResult`. The overlap rule is written once, in
`DateRange.overlaps`; a `Reservation` decides whether it `blocks` a request and owns its status
(changed only by `cancel()`). UML and the code are kept identical; `tests/test_uml_conformance.py`
fails if a class, attribute, operation, enum value or link drifts from
`practices/P03-hotel-domain-uml/uml/class-diagram.mmd` (a later practice that changes the design
points `CLASS_DIAGRAM` at its own diagram).

## Known limitations of version 1

- **Race condition (R3 under concurrency):** check (`has_overlap`) and act (`save`) are separate
  steps. Fixed in P09; pinned by `test_race_double_books_r7_known_defect`.
- In-memory only: restarting clears all reservations.
- `BookingService` depends on the concrete `ReservationStore` and `EmailSender` (P04 introduces
  interfaces).
- `reserve` does not check that the room belongs to the hotel's room list, and reservation ids
  (`R101`, `R102`, …) come from the store's row count — fine for one process, not for several.
