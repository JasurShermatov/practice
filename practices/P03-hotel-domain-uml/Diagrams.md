# P03 — UML diagrams

All diagrams are written as Mermaid source (`uml/*.mmd`), render-checked with the Mermaid CLI
(`mmdc` 11.16) and exported to SVG next to the source. The activity sheet asks for draw.io pages;
see the README for the substitution and how to import these into draw.io.

The diagrams describe **the code in `hotel-booking/` exactly** (version 1). Where they are more
detailed than the course's completed diagrams, the difference is listed at the end of this file
and is there so that every class, member, multiplicity and message matches the code.

| # | Activity-sheet page | Diagram here | Checked against the code by |
|---|---|---|---|
| 1 | Use cases | [Use case diagram](#1-use-cases) | Each use case maps to one method (table below) |
| 2 | Classes | [Class diagram](#2-classes) | `tests/test_uml_conformance.py` (classes, attributes, operations, enum values, 11 links) |
| 3 | Sequence - book | [Maya books R7](#3-sequence---book-success-path) | `tests/test_sequences.py::test_sequence_book_maya_r7` |
| 3b | (L02 / curriculum plan: no-availability path) | [Omar is refused](#3b-sequence---book-no-availability-path) | `test_sequence_unavailable_omar_r7` |
| 4 | Sequence - cancel | [Maya cancels R101](#4-sequence---cancel) | `test_sequence_cancel_r101` |
| 5 | Activity - book | [The booking decision](#5-activity---book) | `test_sequence_invalid_dates_stops_before_the_store`, `test_r3_*` |
| 6 | Step 8 "message by message" | [The race](#6-the-race-step-8) | `test_sequence_race_both_checks_before_either_save`, `test_race_double_books_r7_known_defect` |
| 7 | (L02 page 16: states) | [Reservation states](#7-reservation-states) | `TestReservation::test_cancel_once_then_again` |

## 1. Use cases

```mermaid
---
title: Who uses the hotel booking app, and for what? (use case diagram)
---
flowchart LR
  guest["«actor»<br/>Guest<br/>(website)"]
  receptionist["«actor»<br/>Receptionist<br/>(phone / walk-in)"]

  subgraph app["Hotel booking app (system boundary)"]
    search(["Search free rooms"])
    book(["Book a room"])
    view(["View a booking"])
    cancel(["Cancel a booking"])
  end

  guest --- search
  guest --- book
  guest --- view
  guest --- cancel
  receptionist --- search
  receptionist --- book
  receptionist --- view
  receptionist --- cancel

  classDef actor fill:#fff,stroke:#333,stroke-width:2px
  class guest,receptionist actor
```

Source: [uml/use-case-diagram.mmd](uml/use-case-diagram.mmd) · rendered: [uml/use-case-diagram.svg](uml/use-case-diagram.svg)

2 actors outside the boundary, 4 use cases inside, 8 plain association lines (no arrowheads:
an association says nothing about order). Checking dates and saving are steps *inside* "Book a
room", not goals of their own, so they are not drawn.

| Use case | Method in the code | Requirement |
|---|---|---|
| Search free rooms | `BookingService.find_free_rooms(stay)` | R1 |
| Book a room | `BookingService.reserve(guest, room, stay)` | R2, R3 |
| Cancel a booking | `BookingService.cancel(reservation_id)` | R4 |
| View a booking | `ReservationStore.find(reservation_id)` | R5 |

Sentences for the Cancel lines: *A guest cancels her own booking on the website.* *A receptionist
cancels a booking for a guest who phones.* When Nora phones the hotel, the **receptionist** is the
actor (she uses the app); Nora is still the guest stored on the reservation.

Use case description "Book a room" (main success scenario): (1) the guest enters 12–14 Nov and
asks for free rooms; (2) the app shows R7, R8; (3) the guest chooses R7 and presses Book; (4) the
app checks nobody has R7 on the nights of the 12th and 13th; (5) the app saves R101 and sends a
confirmation email; (6) the guest sees "Accepted, your reservation id is R101".
Alternative flows: at step 1 dates 15–15 → "InvalidDates", nothing saved; at step 4 a Confirmed
booking shares a night → "Unavailable", nothing saved.

## 2. Classes

```mermaid
---
title: Hotel booking app, version 1 - class diagram (P03)
---
classDiagram
  direction TB

  class BookingService {
    -rooms: list~Room~
    -store: ReservationStore
    -email: EmailSender
    -slow_step_seconds: float
    +find_free_rooms(stay: DateRange) list~Room~
    +reserve(guest: Guest, room: Room, stay: DateRange) BookingResult
    +cancel(reservation_id: str) bool
    -next_id() str
  }

  class BookingResult {
    +outcome: BookingOutcome
    +reservation_id: str or None
  }

  class BookingOutcome {
    <<enumeration>>
    ACCEPTED
    UNAVAILABLE
    INVALID_DATES
  }

  class ReservationStore {
    -rows: list~Reservation~
    +count() int
    +has_overlap(room: Room, stay: DateRange) bool
    +save(reservation: Reservation) None
    +find(reservation_id: str) Reservation or None
    +count_confirmed(room: Room, stay: DateRange) int
  }

  class EmailSender {
    +sent: int
    +send_confirmation(reservation: Reservation) None
  }

  class ReservationStatus {
    <<enumeration>>
    CONFIRMED
    CANCELLED
  }

  class Reservation {
    +id: str
    +guest: Guest
    +room: Room
    +stay: DateRange
    +status: ReservationStatus
    +blocks(room: Room, stay: DateRange) bool
    +cancel() bool
  }

  class Guest {
    +name: str
    +email: str
  }

  class Room {
    +number: str
    +type: str
  }

  class DateRange {
    +check_in: date
    +check_out: date
    +is_valid() bool
    +overlaps(other: DateRange) bool
  }

  BookingService ..> ReservationStore : uses
  BookingService ..> EmailSender : uses
  BookingService ..> Reservation : creates
  BookingService ..> BookingResult : returns
  BookingService --> "1..*" Room : offers
  BookingResult --> "1" BookingOutcome : has
  ReservationStore --> "0..*" Reservation : keeps
  Reservation --> "1" ReservationStatus : has
  Guest "1" <-- "0..*" Reservation : makes
  Reservation "0..*" --> "1" Room : reserves
  Reservation "1" *-- "1" DateRange : owns stay dates
```

Source: [uml/class-diagram.mmd](uml/class-diagram.mmd) · rendered: [uml/class-diagram.svg](uml/class-diagram.svg)

**Notation.** Box = class (name / attributes / operations). `+` public, `-` private (a leading
underscore in Python). `«enumeration»` = fixed list of values. Solid arrow = navigable
association (the class at the tail holds a reference). Filled diamond = composition (the owner is
at the diamond). Dashed arrow = dependency ("uses / creates / returns"). Numbers = multiplicity.
`list~Room~` is Mermaid's way to write `list[Room]`. Reservation's attributes are read-only
properties; its status changes only through `cancel()`.

| Link | Multiplicity | Kind | Why this kind | In the code | Requirement it serves |
|---|---|---|---|---|---|
| Guest — Reservation "makes" | Guest 1, Reservation 0..* | association (navigable Reservation → Guest) | Maya exists without bookings and may have many; each booking is for exactly one guest | `Reservation.guest` | R2 (book *for a guest*), R5 (view shows the guest) |
| Reservation — Room "reserves" | Reservation 0..*, Room 1 | association | R7 exists before and after any booking; many bookings of R7 over time | `Reservation.room` | R2, R3 (clash is per room) |
| Reservation ◆— DateRange "owns stay dates" | 1 — 1 | composition | the dates belong to this reservation alone and mean nothing without it; immutable value | `Reservation.stay` | R3 (nights compared), R5 |
| Reservation — ReservationStatus "has" | 1 | association to an enumeration | exactly one of Confirmed / Cancelled at any time | `Reservation.status` | R3 (only Confirmed blocks), R4 |
| ReservationStore — Reservation "keeps" | 0..* | association | the store holds every saved booking, Cancelled ones included (history) | `ReservationStore._rows` | R1, R3, R4, R5 |
| BookingService — Room "offers" | 1..* | association | the service knows the hotel's rooms to search | `BookingService._rooms` | R1 |
| BookingService ··> ReservationStore "uses" | — | dependency | handed in from outside, not owned; called to check, save, find | `_store.has_overlap/count/save/find` | R1–R5 |
| BookingService ··> EmailSender "uses" | — | dependency | handed in; called after a successful save | `_email.send_confirmation` | R2 (confirmation) |
| BookingService ··> Reservation "creates" | — | dependency | `reserve` instantiates the reservation | `Reservation(self._next_id(), …)` | R2 |
| BookingService ··> BookingResult "returns" | — | dependency | the answer of `reserve` | `return BookingResult(...)` | R2, R3 |
| BookingResult — BookingOutcome "has" | 1 | association to an enumeration | exactly one of Accepted / Unavailable / InvalidDates | `BookingResult.outcome` | R2, R3 |

**Composition versus inheritance.** A Reservation is *not a kind of* Room, so there is no
inheritance (hollow triangle) between them — a reservation *refers to* a room. Room type
("Standard", "Deluxe") is a field, not a `SuiteRoom` subclass, because in version 1 a type has no
data or behaviour of its own. Sending a confirmation is a separate job, so it is a separate class
that BookingService *uses* rather than an `EmailBookingService` subclass. Version 1 has no
inheritance at all, which is a deliberate result of the analysis, not an omission.

## 3. Sequence - book (success path)

```mermaid
---
title: Sequence - book. Maya books R7 for 12-14 Nov (success path)
---
sequenceDiagram
  autonumber
  actor Maya
  participant BS as :BookingService
  participant stay as stay:DateRange
  participant Store as :ReservationStore
  participant Email as :EmailSender

  Note over Store: before: store is empty
  Maya->>BS: reserve(MAYA, R7, 12-14 Nov)
  BS->>stay: is_valid()
  stay-->>BS: True
  BS->>Store: has_overlap(R7, 12-14 Nov)
  Note right of Store: loop over rows:<br/>row.blocks(room, stay)<br/>(no rows yet)
  Store-->>BS: False - no booking shares a night
  Note over BS: slow step: 0 s normally<br/>(0.5 s in the race demo)
  BS->>BS: next_id()
  BS->>Store: count()
  Store-->>BS: 0
  create participant R101 as R101:Reservation
  BS->>R101: «create» Reservation("R101", MAYA, R7, stay)
  BS->>Store: save(R101)
  BS->>Email: send_confirmation(R101)
  BS-->>Maya: BookingResult(ACCEPTED, "R101") - "Accepted R101"
  Note over Store: after: R101, Maya, R7, 12-14 Nov, Confirmed
```

Source: [uml/sequence-book.mmd](uml/sequence-book.mmd) · rendered: [uml/sequence-book.svg](uml/sequence-book.svg)

Order that matters: the check (4) comes before the save (10); the save comes before the email (11),
so no email is ever sent for a booking that was not saved; Maya hears "Accepted" only at the end
(12). The course's 6-message version maps to arrows 1, 4, 5, 10, 11, 12 here; arrows 2–3
(`is_valid`), 6–8 (`next_id` → `count`) and 9 (creation of R101) are shown because the code does
them.

## 3b. Sequence - book, no-availability path

```mermaid
---
title: Sequence - book, no availability. Omar asks for R7 13-15 Nov
---
sequenceDiagram
  autonumber
  actor Omar
  participant BS as :BookingService
  participant stay as stay:DateRange
  participant Store as :ReservationStore
  participant R101 as R101:Reservation

  Note over Store: before: R101 (Maya, R7, 12-14 Nov, Confirmed)
  Omar->>BS: reserve(OMAR, R7, 13-15 Nov)
  BS->>stay: is_valid()
  stay-->>BS: True
  BS->>Store: has_overlap(R7, 13-15 Nov)
  loop for each saved row
    Store->>R101: blocks(R7, 13-15 Nov)
    Note right of R101: Confirmed, same room,<br/>stay.overlaps(13-15):<br/>12 < 15 and 13 < 14
    R101-->>Store: True
  end
  Store-->>BS: True - R101 shares the night of 13 Nov
  BS-->>Omar: BookingResult(UNAVAILABLE) - "Unavailable"
  Note over BS,Store: nothing created, nothing saved, no email.<br/>Store still holds only R101.
```

Source: [uml/sequence-unavailable.mmd](uml/sequence-unavailable.mmd) · rendered: [uml/sequence-unavailable.svg](uml/sequence-unavailable.svg)

The first arrows are the same as the success path; after the store answers `True` the request ends
with "Unavailable": no `count`, no creation, no `save`, no `send_confirmation`. Refusing is a normal
answer and the saved data does not change.

## 4. Sequence - cancel

```mermaid
---
title: Sequence - cancel. Maya cancels R101
---
sequenceDiagram
  autonumber
  actor Maya
  participant BS as :BookingService
  participant Store as :ReservationStore
  participant R101 as R101:Reservation

  Note over R101: before: status = CONFIRMED
  Maya->>BS: cancel("R101")
  BS->>Store: find("R101")
  Store-->>BS: R101
  BS->>R101: cancel()
  Note right of R101: CONFIRMED -> CANCELLED<br/>(nothing is deleted)
  R101-->>BS: True - now Cancelled
  BS-->>Maya: True
  Note over Store,R101: after: R101 stays in the store as Cancelled (history kept)<br/>and no longer blocks R7 for 12-14 Nov
```

Source: [uml/sequence-cancel.mmd](uml/sequence-cancel.mmd) · rendered: [uml/sequence-cancel.svg](uml/sequence-cancel.svg)

The fourth participant is one *object*, reservation R101. Find (2) must come before Cancel (4): a
reservation that has not been found cannot be cancelled. The reservation changes its own status;
nothing is deleted, so the history is kept and R7 is free again for 12–14 Nov.

## 5. Activity - book

```mermaid
---
title: Activity - book. The booking decision inside BookingService.reserve
---
flowchart TD
  start(( )) --> received["Reserve request received<br/>(guest, room, stay)"]
  received --> d1{"Check-out after check-in?<br/>stay.is_valid()"}
  d1 -- No --> invalid["InvalidDates · save nothing"]
  d1 -- Yes --> d2{"A Confirmed booking shares a night?<br/>store.has_overlap(room, stay)"}
  d2 -- Yes --> unavailable["Unavailable · save nothing"]
  d2 -- No --> save["Save the reservation as Confirmed<br/>store.save(reservation)"]
  save --> send["Send the confirmation email<br/>email.send_confirmation(reservation)"]
  send --> accepted["Accepted + reservation id"]
  accepted --> done((( )))
  invalid --> stop1((( )))
  unavailable --> stop2((( )))

  classDef startNode fill:#222,stroke:#222,color:#222
  classDef refusal fill:#fde8e8,stroke:#b42318
  classDef ok fill:#e7f6ec,stroke:#1a7f37
  class start startNode
  class invalid,unavailable refusal
  class accepted ok
```

Source: [uml/activity-book.mmd](uml/activity-book.mmd) · rendered: [uml/activity-book.svg](uml/activity-book.svg)

Filled circle = start; diamond = yes/no decision (one `if` in `reserve`); rectangle = action;
bullseye = end. The two diamonds are the two `if` statements at the top of
`BookingService.reserve`. Traces for Omar R7 13–15, Nora R7 14–16 and Omar R8 15–15 are in
[hotel-booking/docs/design-notes.md](../../hotel-booking/docs/design-notes.md#activity-traces).

## 6. The race (Step 8)

```mermaid
---
title: Step 8 - Maya and Omar book R7 for 12-14 Nov at the same moment (race)
---
sequenceDiagram
  actor Maya
  actor Omar
  participant BS as :BookingService
  participant Store as :ReservationStore

  Note over Maya,Store: run_race(): slow step 0.5 s between check and save, Omar starts 0.1 s after Maya
  Maya->>BS: 1. reserve(MAYA, R7, 12-14 Nov)  [0.0 s]
  BS->>Store: 2. has_overlap(R7, 12-14 Nov)
  Store-->>BS: false (store empty)
  Note over BS: Maya's request waits 0.5 s
  Omar->>BS: 3. reserve(OMAR, R7, 12-14 Nov)  [0.1 s]
  BS->>Store: 4. has_overlap(R7, 12-14 Nov)
  Store-->>BS: false (Maya has not saved yet) - the bug
  Note over BS: Omar's request waits 0.5 s
  BS->>Store: 5. save(R101, Maya)  [0.5 s]
  BS-->>Maya: 6. Accepted R101  (after send_confirmation)
  BS->>Store: 7. save(R102, Omar)  [0.6 s] - never re-checks
  BS-->>Omar: 8. Accepted R102  (after send_confirmation)
  Note over Store: R101 and R102: same room, same nights, both Confirmed - R3 broken
```

Source: [uml/sequence-race.mmd](uml/sequence-race.mmd) · rendered: [uml/sequence-race.svg](uml/sequence-race.svg)

| Time | Maya's request | Omar's request | Reservations in the store |
|---|---|---|---|
| 0.0 s | Checks R7: nobody there | — | none |
| 0.1 s | Waiting (slow step) | Checks R7: nobody there | none |
| 0.5 s | Saves R101 → Accepted | Waiting | R101 |
| 0.6 s | — | Saves R102 → Accepted | R101 and R102, same room, same nights |

Both checks (2 and 4) happen before either save (5 and 7): check-then-act is not atomic. In the
course's drawing both saves come before both replies; here Maya's reply (6) is drawn before Omar's
save (7) because that is the order the code produces (`test_sequence_race_both_checks_before_either_save`
records it).

## 7. Reservation states

```mermaid
---
title: States of a Reservation (ReservationStatus)
---
stateDiagram-v2
  [*] --> Confirmed : reserve() accepted<br/>store.save(reservation)
  Confirmed --> Cancelled : cancel() returns True
  Cancelled --> Cancelled : cancel() returns False (no change)
  note right of Cancelled
    Kept in the store as history.
    blocks() is False: the room is free again.
  end note
```

Source: [uml/state-reservation.mmd](uml/state-reservation.mmd) · rendered: [uml/state-reservation.svg](uml/state-reservation.svg)

| Now | Action | Afterwards | `cancel()` returns |
|---|---|---|---|
| (new) | `reserve` succeeds | Confirmed | — |
| Confirmed | cancel | Cancelled | True |
| Cancelled | cancel again | Cancelled | False |

## Differences from the course's completed diagrams

| Course diagram | Here | Reason |
|---|---|---|
| Class diagram: 8 boxes, 7 links | 10 boxes, 11 links | Added `BookingResult` and its `BookingOutcome` enumeration (the code returns them), `BookingService → Room` (the `rooms` list), and `BookingService ··> Reservation «creates»`, so the diagram is the code. |
| `BookingResult.outcome` is a string | `BookingOutcome` enumeration | A fixed list of three answers is safer to compare than free text; `str(result)` still prints `Accepted R101`. |
| `ReservationStore` without `count()`; `BookingService` without private members | `count()`, `-next_id()`, `-store`, `-email`, `-slow_step_seconds` shown | The code uses them; `slow_step_seconds` exists only to make Step 8 visible. |
| Plain lines for "makes" / "reserves" | Navigable arrows from Reservation | In the code only Reservation holds the reference; Guest and Room do not know their reservations. |
| Sequence - book: 6 messages | 12 messages | Adds `is_valid`, `next_id`/`count` and the creation of R101, which the code performs. |
| Race: saves 5, 6 then replies 7, 8 | save, reply, save, reply | The order the code produces (recorded by a test). |
| draw.io pages | Mermaid + SVG | See README "Substitutions". |
