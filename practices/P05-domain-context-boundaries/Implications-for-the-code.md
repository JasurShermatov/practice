# Implications for the code (input for P06)

P05 changes no code. This page turns the written design ([docs/contexts.md](docs/contexts.md))
into a concrete plan for P06, where each context becomes a Python package with a public contract,
internal code, and import checks that guard the borders. Everything here is **Proposed**: it is
implemented and observed in P06, not here.

Rule of thumb carried over from P05: *each context section becomes a package, each rule owner
says which package the rule's code lives in, and each border becomes a contract.*

## 1. One context → one package

| Context (P05) | Package (P06) | Public contract (what other packages may import) | Internal (only its own package and the wiring may import) |
|---|---|---|---|
| Rooms (Inventory) | `hotel_booking/rooms/` | `Room`, `RoomCatalog` (protocol: `all() -> list[Room]`) in `rooms/catalog.py`, re-exported by `rooms/__init__.py` | `rooms/internal.py`: `InMemoryRoomCatalog` (R7 Standard, R8 Deluxe) |
| Reservations (core) | `hotel_booking/reservations/` | `BookingService`, `BookingResult`, `BookingOutcome`, `Guest`, `DateRange`, `Reservation`, `ReservationStatus`, `ReservationStore` (protocol) | `reservations/internal.py`: `InMemoryReservationStore` |
| Payments | `hotel_booking/payments/` | `PaymentStatus` (`PAID`, `DECLINED`), `PaymentService` (protocol: `take_deposit(reservation_id, amount) -> PaymentStatus`; decision D1 adds `deposit_for(stay_price)`) | `payments/internal.py`: `SimulatedPaymentService` |
| Notifications | `hotel_booking/notifications/` | `Confirmation` (5 fields), `NotificationSender` (protocol: `send_confirmation(confirmation) -> None`) | `notifications/internal.py`: `EmailNotificationSender`, `SmsNotificationSender` |
| — (composition root) | `main.py` (since P04 it builds the store, sender and service; `demo.py` only receives them) | — | The only application code allowed to name internal classes; tests may name them too |

Target layout (matches the course's P06 folder, adapted to this repository's `tests/` folder):

```text
hotel-booking/
├── hotel_booking/
│   ├── __init__.py
│   ├── rooms/          __init__.py, catalog.py, internal.py
│   ├── reservations/   __init__.py, domain.py, booking.py, internal.py
│   ├── payments/       __init__.py, internal.py
│   ├── notifications/  __init__.py, internal.py
│   └── demo.py         the nine-line demo and the race (gets ready-built services)
├── main.py
├── .importlinter       the three border contracts (for lint-imports)
└── tests/              behaviour tests + test_architecture.py (stdlib ast import check)
```

## 2. Where today's classes go

Class names are those of the P04 code (P04 introduces the two protocols and the renamed senders).

| Class today (P04) | File today | Target (P06) | Why there |
|---|---|---|---|
| `Room` | `domain.py` | `rooms/catalog.py` (contract) | Rooms decides what a room is (type, later price, out of service) |
| — (a plain list of rooms passed to BookingService) | `main.py` / `demo.py` (`HOTEL_ROOMS`) | `RoomCatalog` contract + `InMemoryRoomCatalog` | Reservations asks Rooms "which rooms exist?" instead of keeping its own copy |
| `DateRange`, `Guest`, `Reservation`, `ReservationStatus` | `domain.py` | `reservations/domain.py` | Words of Reservations (Stay, Guest, Reservation, Confirmed/Cancelled) |
| `BookingService`, `BookingResult`, `BookingOutcome` | `booking.py` | `reservations/booking.py` | Book, Cancel, Free rooms; owns cards 1–3 |
| `ReservationStore` (protocol) | `stores.py` | `reservations/__init__.py` (or `reservations/store.py`) | The store is Reservations' private data; the protocol is how the wiring plugs a store in |
| `InMemoryReservationStore` | `stores.py` | `reservations/internal.py` | Private rows of Reservations; P07 adds the SQLite/PostgreSQL adapter here |
| `NotificationSender` (protocol) | `notifications.py` | `notifications/__init__.py` | The Notifications contract, now taking a `Confirmation` |
| `EmailNotificationSender`, `SmsNotificationSender` | `notifications.py` | `notifications/internal.py` | How a message is sent is Notifications' business |
| — | — | `payments/` (contract + simulated service) | New in P06; booking calls it only from P17 |

Python detail: `hotel_booking/notifications.py` (a module) and `hotel_booking/notifications/`
(a package) cannot both exist, so P06 must move the module's content and delete the file in the
same step; likewise for anything that imports `hotel_booking.stores` / `hotel_booking.domain`.

## 3. Rule cards → where their code lives

| Card | Rule | Owner | Code today (P04) | Code after P06 | Later |
|---|---|---|---|---|---|
| 1 | No two Confirmed reservations of a room share a night | Reservations | `Reservation.blocks`, `DateRange.overlaps`, `ReservationStore.has_overlap` | Same classes, inside `reservations/` | P09 enforces it in the database (S2) |
| 2 | Check-out after check-in | Reservations | `DateRange.is_valid`, first `if` in `BookingService.reserve` | `reservations/domain.py` | — |
| 3 | Cancelling frees the nights | Reservations | `Reservation.cancel` + `blocks` ignores Cancelled | `reservations/domain.py` | — |
| 4 | Out-of-service rooms are not offered | Rooms | not in code | `rooms/` only (e.g. `RoomCatalog.all()` leaves them out, later `on_sale(stay)`) | The practice that adds out-of-service |
| 5 | Nightly price depends on room type | Rooms | not in code (`Room.type` exists) | `rooms/` only | The practice that adds prices |
| 6 | Deposit = 30% of the stay's price | Payments | not in code | `payments/` only (`deposit_for`) | P17 saga |
| 7 | Only a Paid deposit can be refunded | Payments | not in code | `payments/` only | P17 saga (compensation) |
| 8 | A failed message is Failed and never changes the reservation | Notifications | R6: `BookingService.reserve` catches the sender's error, keeps the booking, sets `notification_failed` | Same, plus Notifications no longer receives a `Reservation` it could change | P10: queue + message status Sent/Failed |

Consequence for code review from P06 on: a change to a rule is accepted only in its owner's
package. For example a deposit percentage in `reservations/` is a review finding even if tests
pass.

## 4. Borders → contracts

| Border (P05) | Kind | Python contract (P06) | Fields that cross | Never crosses |
|---|---|---|---|---|
| Reservations → Rooms: which rooms exist? | Question | `RoomCatalog.all() -> list[Room]` | number, type (later nightly price) | reservations, guests, statuses; Rooms' storage |
| Reservations → Payments: take a deposit | Question (from P17) | `PaymentService.take_deposit(reservation_id: str, amount) -> PaymentStatus` | reservation id, amount → Paid/Declined | card/provider details; reservation rows |
| Reservations → Notifications: ReservationConfirmed | Event (a call in P06, a queue message in P10/P15) | `NotificationSender.send_confirmation(Confirmation)` | reservation_id, guest_email, room_number, check_in, check_out | `Reservation` object, reservation list; nothing comes back |

Translation happens on the Reservations side: after `save`, `BookingService` builds
`Confirmation(reservation.id, reservation.guest.email, reservation.room.number,
reservation.stay.check_in, reservation.stay.check_out)`. Notifications then never imports
anything from Reservations, so there is no import cycle.

Recommendation for money (P06/P17): use `decimal.Decimal`, not `float`, for `amount` and prices
(30% of 200.10 must not become 60.029999…). The course contract shows `float`; the name and
shape stay the same.

## 5. Import rules that guard the borders

The three "Never crosses" lines become three import rules (the same three the course lists for
P06):

| # | Rule | Forbidden imports |
|---|---|---|
| A | Reservations uses only the public contracts of other modules | `hotel_booking.reservations` → `hotel_booking.rooms.internal`, `hotel_booking.payments.internal`, `hotel_booking.notifications.internal` |
| B | Rooms does not depend on any other module | `hotel_booking.rooms` → `hotel_booking.reservations`, `hotel_booking.payments`, `hotel_booking.notifications` |
| C | Payments and Notifications do not depend on Reservations | `hotel_booking.payments`, `hotel_booking.notifications` → `hotel_booking.reservations` |

Proposed `.importlinter` (used with `lint-imports` once import-linter can be installed):

```ini
[importlinter]
root_package = hotel_booking

[importlinter:contract:reservations-uses-contracts-only]
name = Reservations uses only the public contracts of other modules
type = forbidden
source_modules = hotel_booking.reservations
forbidden_modules =
    hotel_booking.rooms.internal
    hotel_booking.payments.internal
    hotel_booking.notifications.internal

[importlinter:contract:rooms-independent]
name = Rooms does not depend on any other module
type = forbidden
source_modules = hotel_booking.rooms
forbidden_modules =
    hotel_booking.reservations
    hotel_booking.payments
    hotel_booking.notifications

[importlinter:contract:no-dependency-on-reservations]
name = Payments and Notifications do not depend on Reservations
type = forbidden
source_modules =
    hotel_booking.payments
    hotel_booking.notifications
forbidden_modules =
    hotel_booking.reservations
```

Substitution for this portfolio (import-linter cannot be installed here): P06 adds
`tests/test_architecture.py`, a stdlib test that parses every file under `hotel_booking/` with
`ast`, resolves `import` / `from … import …` (including relative imports) to full module names,
and fails with the file, line and forbidden module for each broken rule. Step 7 of P06 ("break it
on purpose") is then: add `from hotel_booking.notifications.internal import
EmailNotificationSender` to `reservations/booking.py`, watch rule A fail, undo.

## 6. What must not change in P06

- The behaviour tests from P04 stay green (only imports and the fake sender's argument type adapt).
- `python main.py` prints the same nine demo lines.
- `python main.py --race` still double-books R7 (known defect until P09; S2 not met).
- `tests/test_uml_conformance.py` compares the code with the P03 class diagram; P06 must point it
  at its own updated diagram (or retire it in favour of the architecture test) — moving classes
  between packages is a deliberate design change, not drift.

## 7. Change-impact check (Simulated)

The four hotel requests from the start of P05, traced through the context map instead of the code.
This is a thought experiment (**Simulated**); P06 and later practices observe it.

| What the hotel wants | Before P05 (one BookingService) | With the four contexts | Files expected to change after P06 |
|---|---|---|---|
| "Take a 30% deposit when a guest books." | BookingService | Payments owns card 6; Reservations only asks (P17) | `payments/` (rule + contract), `reservations/booking.py` (one call in the saga), wiring |
| "R8 is out of service for repairs next week." | BookingService, or every place that lists rooms | Rooms owns card 4; the room list Reservations receives already leaves R8 out | `rooms/` only |
| "Deluxe rooms cost more per night." | BookingService | Rooms owns card 5 | `rooms/` only |
| "Send an SMS as well as the email." | Only a new sender class (P04 solved it) | Notifications | `notifications/internal.py` + wiring (S5: ≤ 2 files, BookingService unchanged) |

Three of the four requests no longer touch BookingService at all; the deposit touches it only to
add one question to Payments, while the money rule itself stays in Payments.
