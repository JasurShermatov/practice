# Architecture review — hotel-booking version 3 as a modular monolith

**What was reviewed:** `hotel-booking/` at the end of P06 (four modules, wiring in `main.py`,
borders in `.importlinter`) against the P05 design (`docs/contexts.md`, the plan in
[P05 Implications-for-the-code.md](../P05-domain-context-boundaries/Implications-for-the-code.md)),
the L03 module-dependency rules and ADR-001.
**How:** every answer points at a check that was run (**Observed**), a thought experiment
(**Simulated**) or a plan (**Proposed**). The import graph used below is the one
`tests/test_architecture.py` builds with `ast` from the real source files.

## Summary

| Question | Verdict |
|---|---|
| R1 · One module per context, each with a contract and internal code? | **Yes** — Observed |
| R2 · Do all dependencies point one way, with no circle? | **Yes** — Observed (as-built graph) |
| R3 · Contract or reach-in: does any module use another's internal code or data? | **No reach-in** — Observed |
| R4 · Are the three gaps of "Why that is not enough yet" closed? | **Yes** — Observed |
| R5 · Does every rule card live in its owner's module? | **Yes for the 4 cards in code; 4 cards not in code yet** — Observed / Proposed |
| R6 · Does each border carry exactly P05's fields? | **Yes** — Observed |
| R7 · Who stops a forbidden arrow, and what can still slip through? | Three contracts + extras stop direct and indirect imports; dynamic imports and data reached through returned objects are not caught — Observed / Simulated |
| R8 · Does ADR-001 pass L03's four ADR questions? | **Yes** |
| R9 · What did P06 change for the quality scenarios S1–S6? | S5 re-observed, S3 strengthened, S2 unchanged (known defect) |
| R10 · Is change now local (P05's change-impact check)? | SMS: Observed (1 file); the other three: Simulated on the real structure |

Eight findings follow at the end (one known high-severity defect, no new blocking issue).

## R1 · One module per context

| Context (P05) | Package | Public contract (`__all__`) | Internal (`internal.py`) | Imports from other modules |
|---|---|---|---|---|
| Rooms | `hotel_booking/rooms` | `Room`, `RoomCatalog` | `InMemoryRoomCatalog` | none |
| Reservations | `hotel_booking/reservations` | `BookingService`, `BookingResult`, `BookingOutcome`, `DateRange`, `Guest`, `Reservation`, `ReservationStatus`, `ReservationStore` | `InMemoryReservationStore` | Rooms contract, Notifications contract |
| Payments | `hotel_booking/payments` | `PaymentStatus`, `PaymentService` | `SimulatedPaymentService` | none |
| Notifications | `hotel_booking/notifications` | `Confirmation`, `NotificationSender` | `EmailNotificationSender`, `SmsNotificationSender` | none |

Evidence: `test_diagram_has_exactly_the_classes_of_the_four_modules`,
`test_every_box_is_drawn_in_the_module_that_defines_it`,
`test_internal_boxes_are_exactly_the_classes_of_the_internal_files` (no contract re-exports an
internal class), `test_every_class_lives_in_one_of_the_four_modules`,
`test_package_root_exports_nothing`. Class diagram by module:
[diagrams/class-diagram.mmd](diagrams/class-diagram.mmd) → [.svg](diagrams/class-diagram.svg).

## R2 · Dependencies point one way

As built ([diagrams/module-dependencies.mmd](diagrams/module-dependencies.mmd) → [.svg](diagrams/module-dependencies.svg);
`test_as_built_diagram_shows_exactly_the_real_imports` fails if the drawing and the code differ):

- Between modules there are exactly **two** arrows, both from Reservations: → Rooms contract,
  → Notifications contract. (The Payments arrow of the context map is "from P17": no code calls
  Payments yet, so no import exists — the diagram shows that honestly.)
- Inside each module, `internal` → contract only.
- `main.py` imports the three internal classes it creates plus the Reservations contract and the
  demo; `demo.py` imports the Reservations and Rooms contracts.
- No circle: Rooms, Payments and Notifications import nothing from any other module (rules 2, 3).

Compared with the P05 target ([module-dependencies.mmd of P05](../P05-domain-context-boundaries/diagrams/module-dependencies.mmd)):
same shape, minus the not-yet-used Payments arrow.

## R3 · Contract or reach-in?

L03's table, applied to this code:

| Code inside Reservations | Allowed? | In our code |
|---|---|---|
| `rooms` list from `RoomCatalog.all()` | Yes: the Rooms contract | The wiring calls `catalog.all()` and passes the list in; `BookingService` only knows `Room` |
| `notifications.send_confirmation(Confirmation(...))` | Yes: the Notifications contract | `BookingService._try_to_confirm` |
| `EmailNotificationSender()` | No: internal to Notifications | Not present — and Step 7 proved the check fails if it appears |
| Reading Notifications' list of sent messages | No: private data | Not present; only `main.py` reads `email.sent` (the wiring owns the object) |

And the other direction (L03 "Reaching into another module"): Notifications cannot read
Reservations' rows — it has no import of Reservations (rule 3) and receives a frozen
`Confirmation` of plain values. Observed: `test_reservations_sends_the_five_border_fields`,
`test_confirmation_is_exactly_the_p05_fields_and_frozen`, `test_a_sender_can_no_longer_change_the_booking`.

## R4 · The three gaps from the start of P06

| What the design says | What P04 code allowed | P06 code | Evidence |
|---|---|---|---|
| Reservations uses only the Notifications contract | BookingService could create `EmailNotificationSender` | Forbidden by rule 1; the import makes the build red | [s7-red](evidence/logs/s7-red.txt) |
| Notifications never depends on Reservations | The sender took the whole `Reservation` (a circle) | The sender takes `Confirmation`; Notifications imports nothing from Reservations | rule 3 kept; [s7-all-rules](evidence/logs/s7-all-rules.txt) shows it turning red if broken |
| Payments is its own business area | No Payments code at all | `payments/` with contract + simulated service, border tested | `test_simulated_payment_*`, rule 3 |

## R5 · Rule cards in their owner's module

| Card | Rule | Owner (P05) | Code after P06 | Verdict |
|---|---|---|---|---|
| 1 | No two Confirmed reservations of a room share a night | Reservations | `Reservation.blocks`, `DateRange.overlaps`, `ReservationStore.has_overlap` in `reservations/` | In owner ✔ (race still open, P09) |
| 2 | Check-out after check-in | Reservations | `DateRange.is_valid`, first `if` of `reserve` | In owner ✔ |
| 3 | Cancelling frees the nights | Reservations | `Reservation.cancel` + `blocks` ignores Cancelled | In owner ✔ |
| 4 | Out-of-service rooms are not offered | Rooms | not in code; the seam exists: the room list comes from `RoomCatalog.all()` (`test_booking_service_offers_exactly_the_catalogs_rooms`) | Proposed (see finding F4) |
| 5 | Nightly price by room type | Rooms | not in code | Proposed |
| 6 | Deposit = 30% | Payments | not in code; `Decimal` contract ready (`test_deposit_arithmetic_is_exact_with_decimal`) | Proposed (P17, decision D1) |
| 7 | Only a Paid deposit can be refunded | Payments | not in code | Proposed (P17) |
| 8 | A failed message never changes the reservation | Notifications | R6 in `BookingService` + Notifications receives only a frozen copy | In code ✔ — now enforced by construction |

No rule's code sits outside its owner's package (search of the module folders; every class is in
its context's module — R1).

## R6 · What crosses each border

| Border | P05 fields | P06 code | Never crosses (P05) | Holds? |
|---|---|---|---|---|
| Reservations → Rooms | number, type | `RoomCatalog.all() -> list[Room]`, `Room(number, type)` | reservations, guests, statuses; Rooms' storage | ✔ Rooms imports nothing (rule 2) |
| Reservations → Payments (P17) | reservation id, amount → Paid/Declined | `PaymentService.take_deposit(reservation_id: str, amount: Decimal) -> PaymentStatus` | card details; reservation rows | ✔ (contract only; no caller yet) |
| Reservations → Notifications | reservation_id, guest_email, room_number, check_in, check_out | `Confirmation` — exactly these five fields, in this order | `Reservation`, reservation list; nothing comes back | ✔ `test_confirmation_is_exactly_the_p05_fields_and_frozen`; `send_confirmation` returns `None` |

## R7 · Who stops the forbidden arrow — and what can still slip through

What runs: `tests/test_architecture.py` on every `python -m pytest` (and `lint-imports` with the
same `.importlinter` where import-linter is installed). Observed to catch:

- direct imports, absolute and relative (`from ..notifications import internal`), `import x.y`
  and `from x import submodule` (self-tests `rule1-direct`, `rule1-relative`, `rule2`, `rule3`);
- **indirect** imports — Reservations → helper → `notifications.internal`
  (`test_checker_catches_an_indirect_bad_import`), like import-linter's default;
- imports under `if TYPE_CHECKING:` (they are still import statements in the tree).

What it does **not** catch (Simulated — reasoned, not exploited):

| Gap | Example | Mitigation |
|---|---|---|
| Dynamic imports | `importlib.import_module("hotel_booking.notifications.internal")` | Neither `ast` nor import-linter sees string imports. Code review; a later check could flag `importlib`/`__import__` in module folders. |
| Data reached through a returned object | Code holding a `Reservation` (from `store.find`) can call `cancel()` | Only Reservations and the wiring hold reservations today; P07 could return read-only views. |
| Private attributes | `store._rows` | Python convention only; mypy strict and review. |
| Rules nobody wrote | e.g. Payments → Rooms is not forbidden by the three course rules | The extra test "no module imports another module's internal code" covers internals; a contract-level Payments → Rooms import would pass. Proposed: an independence contract when P17 adds Payments code. |

## R8 · ADR-001 against L03's "How to check an ADR"

| Question | ADR-001 ([hotel-booking/docs/adr-001-modular-monolith.md](../../hotel-booking/docs/adr-001-modular-monolith.md)) |
|---|---|
| Does it say what was decided, in one sentence? | Yes — "One deployable program with four modules, one per context", borders checked by the build |
| Does it give a reason from a scenario? | Yes — S2 stays checkable in one place; S3 does not depend on a remote system; no measured need for separate release or scaling |
| Does it name a cost? | Yes — released together, one shared process, borders hold only while the checks run, protocols checked by shape |
| Does it say when to revisit? | Yes — a measured need for own release or scaling (L07/P13) |

## R9 · Quality scenarios after P06

| Scenario | Effect of P06 | Status |
|---|---|---|
| S1 Performance | none (same in-process calls) | Proposed (P08/P23) |
| S2 Data integrity | none — the race is unchanged, as a refactoring must leave it; the fix now has one obvious home (Reservations) | **Known to fail** (20/20 double bookings, [f-race20](evidence/logs/f-race20.txt)); P09 |
| S3 Availability | strengthened: a sender can no longer change the booking even by mistake | Observed (R6 tests + `test_a_sender_can_no_longer_change_the_booking`) |
| S4 Security | none | Proposed (P21) |
| S5 Modifiability | re-observed on the new structure: SMS instead of email = 1 line in 1 file (`main.py`), 0 lines in any module, contracts still kept | Observed ([s5-sms-swap](evidence/logs/s5-sms-swap.txt)) |
| S6 Sustainability | none | Proposed |

## R10 · Change impact on the real structure

P05 traced four hotel requests through the context map (Simulated). With the modules in place:

| Request | Files that would change | Label |
|---|---|---|
| "Send an SMS as well / instead" | `main.py` only (sender exists in `notifications/internal.py`) | **Observed** for "instead" ([s5-sms-swap](evidence/logs/s5-sms-swap.txt)); "as well" adds one composite sender in `notifications/internal.py` — Simulated |
| "R8 is out of service next week" | `rooms/` (catalog answers per stay) + the wiring; see F4 for the one Reservations change it currently implies | Simulated |
| "Deluxe rooms cost more" | `rooms/catalog.py` (price on `Room` or a price question) | Simulated |
| "Take a 30% deposit" | `payments/` (rule + `deposit_for`), one call in `reservations/booking.py` (saga), wiring | Simulated (P17) |

## Findings

| # | Severity | Finding | Recommendation / owner practice |
|---|---|---|---|
| F1 | High (known) | S2 race: check-then-save is not atomic; 20/20 runs double-book R7 | Fix inside Reservations (P09); `test_race_double_books_r7_known_defect` must flip |
| F2 | Medium | Python cannot hide `internal.py`; the borders exist only because the checks run. Dynamic imports are invisible to both checkers | Run the checks in CI (P25); flag `importlib` in module folders if it ever appears |
| F3 | Medium | `Reservation` stores the whole `Room` from the Rooms contract; when Rooms adds price or service status to `Room`, Reservations will carry and compare those fields (equality in `blocks`) | Store `room_number` only when the database table arrives (P07, P05 decision D2) |
| F4 | Low | `BookingService` receives the room *list* once, at wiring time, not the `RoomCatalog`; a room going out of service at run time would not be seen | When card 4 arrives, inject `RoomCatalog` and ask it per search (one constructor change, tests' helper only) |
| F5 | Low | Payments' contract is untested by a real caller; P05's D1 (`deposit_for`) was not added | Add with the saga in P17; the border check is already in place |
| F6 | Low | The three course contracts do not forbid contract-level imports between Payments, Notifications and Rooms | Add an independence contract when Payments gets real code (P17) |
| F7 | Info | `demo.py` sits in the package root, outside the four modules | Accepted: it is scenario code with no classes; it is checked like a module (contracts only) |
| F8 | Info | The package root no longer re-exports; code written for version 2 (e.g. P04's `compare_behaviour.py`) cannot import from `hotel_booking` any more | Intended (the root must not hand out internals); P06 ships a version-aware comparison script |

## Differences from the P05 plan

| P05 plan | P06 result | Why |
|---|---|---|
| `ReservationStore` in `reservations/__init__.py` or `store.py` | In `reservations/booking.py`, exported by `__init__.py` | The course's finished P06 folder has exactly `__init__`, `booking`, `domain`, `internal` |
| `PaymentService` gains `deposit_for(stay_price)` (D1) | Not added | The course's P06 contract has `take_deposit` only, and nothing would call it before P17 (no unused API) |
| `.importlinter` | As planned (3 contracts); the course reference puts them in `pyproject.toml` | Brief asks for `.importlinter`; one file only, so `lint-imports` and the test read the same rules |
| `test_uml_conformance.py` re-pointed or retired | Re-pointed at the P06 diagram and extended with module checks | The diagram now also documents *where* each class lives |
| Step 7 as described | As described, plus rules 2 and 3 on a throw-away copy | A check never seen failing proves nothing — for each rule |
