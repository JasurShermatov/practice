# P03 — The hotel booking domain

## The brief (fictional classroom case)

A small hotel has rooms such as **R7** (Standard) and **R8** (Deluxe). Guests book on the website;
a receptionist books for guests who phone or walk in. Today bookings sit in one spreadsheet, and
on a Monday morning Maya (website, R7 12–14 Nov) and Omar (phone, R7 13–15 Nov) can both be
promised the same room. The app must make that impossible: **one room, one night, at most one
guest.** Guests search dated availability, request a reservation and receive its status; payment
is out of scope (the course plan calls it "simulated" — version 1 has no payment step at all).

| Job | Example |
|---|---|
| Search free rooms | Which rooms are free 12–14 Nov? → R7, R8 |
| Book a room | Maya books R7 12–14 Nov → Accepted, id R101 |
| Refuse a clash | Omar asks for R7 13–15 Nov → Unavailable |
| Cancel a booking | Maya cancels R101 → R7 is free again for those nights |
| View a booking | Reception looks up R101 → Maya, R7, 12–14 Nov, Confirmed |

## Glossary

| Term | Meaning in this project |
|---|---|
| Stay / DateRange | Half-open range of nights `[check_in, check_out)`. 12–14 Nov = nights of the 12th and 13th. |
| Night | The unit that can clash. Two stays clash only if they share a night. |
| Reservation | One booking of one room for one stay by one guest; identified by its id (R101). |
| Confirmed | A saved reservation that blocks its room for its nights. |
| Cancelled | A reservation kept as history that no longer blocks anything. |
| Unavailable | The answer when a Confirmed reservation of the same room shares a night; nothing is saved. |
| InvalidDates | The answer when check-out is not after check-in; nothing is saved. |

## Invariant

> For every room *r* and every night *n*, at most one reservation with status **Confirmed** has
> room *r* and a stay that contains *n*.

Equivalently: no two Confirmed reservations of the same room overlap. `ReservationStore.count_confirmed(room, stay)`
measures it (must be ≤ 1 for any single night). It holds for sequential requests (tested by
`test_r3_invariant_at_most_one_confirmed_per_room_night`) and is **observed to break** under
concurrent requests (`python main.py --race` → 2). Secondary invariants: a stay has at least one
night (`is_valid`); status only moves Confirmed → Cancelled; ids are never reused.

## Responsibilities

The course plan asks for responsibilities of Room, DateRange, Reservation and Notification. In
version 1 "Notification" is the `EmailSender` class.

| Class | Kind | Knows | Does | Does **not** do |
|---|---|---|---|---|
| `Room` | data (reference) | number, type | — | know its reservations; a type is a label, not a subclass |
| `Guest` | data (reference) | name, email | — | know its reservations |
| `DateRange` | data (**value**: equal by content, immutable) | check-in, check-out | `is_valid()`, `overlaps(other)` — the *only* home of the night rule | know rooms or statuses |
| `Reservation` | data (**entity**: identified by id, status changes) | id, guest, room, own stay, status | `blocks(room, stay)`, `cancel()` | let anyone else set its status |
| `ReservationStatus` | enumeration | Confirmed, Cancelled | — | — |
| `ReservationStore` | worker | all reservations ever saved | `has_overlap`, `save`, `find`, `count`, `count_confirmed` | decide the date rule (it asks each reservation) |
| `EmailSender` (Notification) | worker | how many confirmations were sent | `send_confirmation(reservation)` after a save | decide whether a booking is accepted; in P03 it is simulated and cannot fail |
| `BookingService` | worker (application service) | the hotel's rooms; its store and sender (handed in) | `find_free_rooms`, `reserve`, `cancel` — the order of steps | contain business rules that belong to the data classes |
| `BookingResult` / `BookingOutcome` | data | outcome (+ id when Accepted) | prints `Accepted R101` | — |

## Assumptions

1. One hotel, rooms fixed at start (R7, R8). Rooms are not added or removed at run time.
2. A reservation is for exactly one room and one guest; a guest may hold several reservations.
3. Dates are calendar dates in the hotel's local time; no check-in/check-out hours.
4. No prices, payments, logins or housekeeping in version 1; the "cleaning day" rule is only a
   thought experiment for why the overlap rule needs one home.
5. Email is simulated (counted, never sent) and cannot fail in version 1.
6. One process, one in-memory store; restart clears everything.
7. All names, emails and dates are fictional demo data (`@example.com`).

## Justified decision and its limitation

**Decision:** put the overlap rule in `DateRange.overlaps`, the "does this booking block that
request" rule in `Reservation.blocks`, and only the *order of steps* in `BookingService.reserve`
(validate → check → save → notify → answer).

- *Why:* each rule has exactly one home (Information Expert), so the website and the reception
  desk cannot drift apart, and a rule change (e.g. a cleaning day) is a one-method edit. The order
  "save before email" means no guest is told about a booking that was not saved.
- *Evidence:* **Observed** — 52 pytest tests pass, including the per-requirement tests and the
  spy tests that record the message order of each sequence diagram
  ([evidence/observed-runs.md](evidence/observed-runs.md)).
- *Limitation:* the check (`has_overlap`) and the act (`save`) are two separate calls. Under
  concurrency the invariant breaks — **Observed** with `python main.py --race` (2 Confirmed
  reservations for R7 12–14 Nov). A code lock would only protect one process; the course fixes this
  in the database in P09. Also: `BookingService` is tied to concrete `ReservationStore` and
  `EmailSender` classes (P04), and the email step happens inside the request, so a real provider's
  failure handling is still undesigned (L02 states that an email failure must not erase an
  accepted reservation — to be designed in P04/P10).
- *Design consequence:* the race is pinned by a characterisation test so that P09's fix is a
  visible, intentional test change rather than an accident.
