# P04 — Diagrams (before and after the refactoring)

All diagrams are Mermaid sources in [uml/](uml/), render-checked with the Mermaid CLI (`mmdc` 11.16,
headless Chromium) and exported to SVG next to the source. The activity sheet asks for a draw.io page
"Classes - after"; see the README "Substitutions" for why Mermaid and how to import it into draw.io.
Python names are used (`ReservationStore`, `NotificationSender`); the C# tab of the course calls the
same interfaces `IReservationStore` and `INotificationSender`.

| # | Diagram | Activity sheet / plan | Checked against the code by |
|---|---|---|---|
| 1 | [Classes - before](#1-classes---before-p03) | Step 4 "Before: the P03 design" | P03 snapshot (evidence O0); `tests/test_uml_conformance.py` of P03 |
| 2 | [Classes - after](#2-classes---after-the-activity-sheet-page) | Step 4 "Your turn" (2 interfaces, 5 classes, 2 uses, 4 implements) | `test_classes_after_page_has_the_counts_of_the_p04_checklist`, `test_classes_after_page_implements_lines_hold_in_the_code` |
| 3 | [Class diagram, version 2 (full)](#3-class-diagram-version-2-full) | Keeps code == UML (P03 rule) | `tests/test_uml_conformance.py` (20 tests) |
| 4 | [Before/after dependency sketch](#4-beforeafter-dependency-sketch) | Curriculum plan: "Produce: before/after dependency sketch" | `tests/test_dependency_rule.py` (3 tests) |
| 5 | [Sequence - R6 failed confirmation](#5-sequence---r6-the-email-fails-after-the-booking-is-saved) | Step 7.2 diagram | `tests/test_sequences.py::test_sequence_r6_failed_confirmation` |

## 1. Classes - before (P03)

```mermaid
---
title: Classes - before (P03). BookingService is tied to two concrete classes
---
classDiagram
  direction TB

  class BookingService {
    -rooms: list~Room~
    -store: ReservationStore
    -email: EmailSender
    +find_free_rooms(stay: DateRange) list~Room~
    +reserve(guest: Guest, room: Room, stay: DateRange) BookingResult
    +cancel(reservation_id: str) bool
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

  BookingService ..> ReservationStore : uses this exact class
  BookingService ..> EmailSender : uses this exact class
```

Source: [uml/class-before.mmd](uml/class-before.mmd) · rendered: [uml/class-before.svg](uml/class-before.svg)

Both dashed "uses" arrows end at **concrete** classes. To keep bookings in PostgreSQL (P07), send SMS,
or make the email fail in a test, `BookingService` itself would have to be edited — although its
booking rules do not change. (Guest, Room, DateRange, Reservation are left out, as in the course
diagram; the full P03 diagram is
[P03 uml/class-diagram.mmd](../P03-hotel-domain-uml/uml/class-diagram.mmd).)

## 2. Classes - after (the activity-sheet page)

```mermaid
---
title: Classes - after (P04). BookingService depends only on two interfaces
---
classDiagram
  direction TB

  class BookingService {
    -rooms: list~Room~
    -store: ReservationStore
    -notifications: NotificationSender
    +find_free_rooms(stay: DateRange) list~Room~
    +reserve(guest: Guest, room: Room, stay: DateRange) BookingResult
    +cancel(reservation_id: str) bool
  }

  class ReservationStore {
    <<interface>>
    +count() int
    +has_overlap(room: Room, stay: DateRange) bool
    +save(reservation: Reservation) None
    +find(reservation_id: str) Reservation or None
    +count_confirmed(room: Room, stay: DateRange) int
  }

  class NotificationSender {
    <<interface>>
    +send_confirmation(reservation: Reservation) None
  }

  class InMemoryReservationStore {
    -rows: list~Reservation~
  }

  class EmailNotificationSender {
    +sent: int
  }

  class SmsNotificationSender {
    +sent: int
  }

  class FakeNotificationSender {
    <<tests only>>
    +fail: bool
    +sent: list~str~
  }

  BookingService ..> ReservationStore : uses
  BookingService ..> NotificationSender : uses
  InMemoryReservationStore ..|> ReservationStore : implements
  EmailNotificationSender ..|> NotificationSender : implements
  SmsNotificationSender ..|> NotificationSender : implements
  FakeNotificationSender ..|> NotificationSender : implements
```

Source: [uml/classes-after.mmd](uml/classes-after.mmd) · rendered: [uml/classes-after.svg](uml/classes-after.svg)

Checklist of the activity sheet: **2 interfaces** (`ReservationStore`, `NotificationSender`),
**5 classes** (`BookingService`, `InMemoryReservationStore`, `EmailNotificationSender`,
`SmsNotificationSender`, `FakeNotificationSender` «tests only»), **2 "uses"** arrows (dashed, open
head) and **4 "implements"** lines (dashed, hollow triangle). The counts are asserted by a test that
parses this file, and each "implements" line is checked against the code (same methods, same
parameter names), including the fake that lives in `test_booking_service.py`.

Reading it: `BookingService` (top) never names a bottom-row class, so any of them can be plugged in —
email or SMS in the app, the fake in the tests, later a PostgreSQL store. Who plugs them in is
`main.py` (`build_app`), the composition root.

## 3. Class diagram, version 2 (full)

```mermaid
---
title: Hotel booking app, version 2 - class diagram (P04)
---
classDiagram
  direction TB

  class BookingService {
    -rooms: list~Room~
    -store: ReservationStore
    -notifications: NotificationSender
    -slow_step_seconds: float
    +find_free_rooms(stay: DateRange) list~Room~
    +reserve(guest: Guest, room: Room, stay: DateRange) BookingResult
    +cancel(reservation_id: str) bool
    -next_id() str
    -try_to_confirm(reservation: Reservation) bool
  }

  class BookingResult {
    +outcome: BookingOutcome
    +reservation_id: str or None
    +notification_failed: bool
  }

  class BookingOutcome {
    <<enumeration>>
    ACCEPTED
    UNAVAILABLE
    INVALID_DATES
  }

  class ReservationStore {
    <<interface>>
    +count() int
    +has_overlap(room: Room, stay: DateRange) bool
    +save(reservation: Reservation) None
    +find(reservation_id: str) Reservation or None
    +count_confirmed(room: Room, stay: DateRange) int
  }

  class InMemoryReservationStore {
    -rows: list~Reservation~
    +count() int
    +has_overlap(room: Room, stay: DateRange) bool
    +save(reservation: Reservation) None
    +find(reservation_id: str) Reservation or None
    +count_confirmed(room: Room, stay: DateRange) int
  }

  class NotificationSender {
    <<interface>>
    +send_confirmation(reservation: Reservation) None
  }

  class EmailNotificationSender {
    +sent: int
    +send_confirmation(reservation: Reservation) None
  }

  class SmsNotificationSender {
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
  BookingService ..> NotificationSender : uses
  BookingService ..> Reservation : creates
  BookingService ..> BookingResult : returns
  BookingService --> "1..*" Room : offers
  BookingResult --> "1" BookingOutcome : has
  InMemoryReservationStore ..|> ReservationStore : implements
  EmailNotificationSender ..|> NotificationSender : implements
  SmsNotificationSender ..|> NotificationSender : implements
  InMemoryReservationStore --> "0..*" Reservation : keeps
  Reservation --> "1" ReservationStatus : has
  Guest "1" <-- "0..*" Reservation : makes
  Reservation "0..*" --> "1" Room : reserves
  Reservation "1" *-- "1" DateRange : owns stay dates
```

Source: [uml/class-diagram.mmd](uml/class-diagram.mmd) · rendered: [uml/class-diagram.svg](uml/class-diagram.svg)

Differences from the P03 class diagram, one line each:

| Change | Kind | Why |
|---|---|---|
| `ReservationStore` became an «interface» (5 operations, no data) | refactoring | D: BookingService depends on the promise |
| `InMemoryReservationStore` (new name for the P03 list store) implements `ReservationStore` | refactoring (rename) | The name says where the rows live; P07 adds a database store next to it |
| `NotificationSender` «interface» (1 operation) | refactoring | D + I: one small promise, "tell the guest" |
| `EmailNotificationSender` (new name for `EmailSender`) implements `NotificationSender` | refactoring (rename) | The name says what it does |
| `BookingService -email` → `-notifications: NotificationSender`; "uses" arrows now end at interfaces | refactoring | D |
| `BookingResult +notification_failed: bool`, `BookingService -try_to_confirm()` | **behaviour (R6)** | Added after the refactoring, test first |
| `SmsNotificationSender` implements `NotificationSender` | **feature** | O: added without editing `BookingService` |
| Domain classes, enums, multiplicities, composition | unchanged | Nothing about the booking rules changed |

14 relationship lines: 11 as in P03 (the store's "keeps" line moved to `InMemoryReservationStore`) plus
3 "implements". Interfaces are `typing.Protocol` classes; "implements" is structural in Python (no
inheritance in the code), which is why the conformance test compares method names and parameter names
instead of looking for a base class.

## 4. Before/after dependency sketch

```mermaid
---
title: Before/after dependency sketch - who names which concrete class
---
flowchart LR
  subgraph before["Before (P03)"]
    direction TB
    b_demo["demo.py<br/>creates ReservationStore + EmailSender"]
    b_service["BookingService<br/>(booking rules)"]
    b_store["ReservationStore<br/>(list in memory)"]
    b_email["EmailSender<br/>(simulated email)"]
    b_demo -- "creates + passes in" --> b_service
    b_service -- "imports, type = concrete class" --> b_store
    b_service -- "imports, type = concrete class" --> b_email
  end

  subgraph after["After (P04)"]
    direction TB
    a_main["main.py = composition root<br/>the only place that picks the real classes"]
    a_service["BookingService<br/>(booking rules, unchanged)"]
    a_store_port[["«interface» ReservationStore"]]
    a_sender_port[["«interface» NotificationSender"]]
    a_mem["InMemoryReservationStore"]
    a_email["EmailNotificationSender"]
    a_sms["SmsNotificationSender"]
    a_fake["FakeNotificationSender<br/>(tests only)"]
    a_main -- "creates + passes in" --> a_service
    a_main -. creates .-> a_mem
    a_main -. creates .-> a_email
    a_service -- uses --> a_store_port
    a_service -- uses --> a_sender_port
    a_mem -. implements .-> a_store_port
    a_email -. implements .-> a_sender_port
    a_sms -. implements .-> a_sender_port
    a_fake -. implements .-> a_sender_port
  end

  before ~~~ after
```

Source: [uml/dependency-before-after.mmd](uml/dependency-before-after.mmd) · rendered: [uml/dependency-before-after.svg](uml/dependency-before-after.svg)

Before, `BookingService` imported and was typed with the concrete classes, and `demo.py` created them.
After, the booking rules depend only on the two promises; the arrows from the concrete classes point
**up** to the promises (dependency inversion), and `main.py` is the one place that creates real
objects. `tests/test_dependency_rule.py` reads the source with `ast` and fails if `booking.py` names a
concrete store or sender, or if any module other than `main.py` creates one.

## 5. Sequence - R6: the email fails after the booking is saved

```mermaid
---
title: R6 - the email fails after the booking is saved (test_a_failed_confirmation_keeps_the_booking)
---
sequenceDiagram
  autonumber
  actor Maya
  participant BS as :BookingService
  participant Store as store:ReservationStore<br/>(InMemoryReservationStore)
  participant Sender as notifications:NotificationSender<br/>(FakeNotificationSender, fail=True)

  Maya->>BS: reserve(MAYA, R7, 12-14 Nov)
  BS->>Store: has_overlap(R7, 12-14 Nov)
  Store-->>BS: False
  BS->>Store: count()   [inside next_id()]
  Store-->>BS: 0
  BS->>Store: save(R101)
  Note over Store: from here on Maya has R101 (Confirmed),<br/>whatever happens next
  BS->>Sender: send_confirmation(R101)
  Sender--xBS: RuntimeError("The mail server is down.")
  Note over BS: caught in try_to_confirm():<br/>logged, booking not undone
  BS-->>Maya: BookingResult(ACCEPTED, "R101", notification_failed=True) - "Accepted R101"
```

Source: [uml/sequence-r6-failed-confirmation.mmd](uml/sequence-r6-failed-confirmation.mmd) · rendered: [uml/sequence-r6-failed-confirmation.svg](uml/sequence-r6-failed-confirmation.svg)

`save(R101)` (6) comes before `send_confirmation(R101)` (7), so the failure (8, a dashed reply with a
cross = an exception) cannot lose the booking. `BookingService` catches it in `_try_to_confirm`,
logs a warning and still answers `Accepted R101` with `notification_failed=True` (9). The course's
version of this diagram has 7 arrows; this one also shows `count()` (4–5), the id lookup inside
`next_id()`, because the spy test records it. The message order is recorded from the running code
by `test_sequence_r6_failed_confirmation`.

## P03 diagrams after the refactoring

The P03 sequence diagrams (book, no availability, cancel, race) still describe version 2: the
participants are now typed by the promises (`store: ReservationStore`, `notifications:
NotificationSender`), but every message and its order are the same — `tests/test_sequences.py` passes
unchanged apart from the renamed spy base classes. The only addition inside `reserve` is the private
self-call `_try_to_confirm`, which wraps the same `send_confirmation` message.
