# P04 — Before and after: the reservation design refactored

**Today's aim (curriculum plan):** improve one responsibility or dependency while preserving
behaviour. **Case:** the fictional hotel from P03 (rooms R7, R8; guests Maya, Omar, Nora).
**Code:** [hotel-booking/](../../hotel-booking/README.md), version 1 (P03) → version 2 (P04).

Words used here: the curriculum plan's *port* is a Python `typing.Protocol` (the activity sheet calls
it a *promise* or *interface*); an *adapter* is a class that keeps it. So
`NotificationSender` = the NotificationPort of the completed example, `EmailNotificationSender` and
`SmsNotificationSender` = its adapters, `ReservationStore` = the storage port ("SQL access" in the
curriculum plan's before-example; a list today, PostgreSQL in P07).

## 1. Before: what the P03 design mixed together

`BookingService` holds the **booking policy** (valid dates, no shared night, save before confirm), but
its constructor asked for two **concrete** helpers:

```python
# version 1 (P03) - hotel_booking/booking.py
from .notifications import EmailSender
from .stores import ReservationStore          # the class that keeps a list

class BookingService:
    def __init__(self, rooms, store: ReservationStore, email: EmailSender, slow_step_seconds=0.0): ...
        ...
        self._store.save(reservation)
        self._email.send_confirmation(reservation)   # an exception here escapes reserve()
```

and `demo.py` both told the classroom story and created those concrete objects. Consequences (all in
[design-notes.md § What our code breaks](../../hotel-booking/docs/design-notes.md#what-our-code-breaks)):

| Change request | What version 1 forces | Principle broken |
|---|---|---|
| "Send SMS confirmations too." | Edit `BookingService`'s constructor and `reserve()` | D, therefore O |
| "Keep bookings in PostgreSQL" (P07) | Edit `BookingService` although the booking rules stay the same | D |
| "Prove a failed email never loses a booking." | Impossible in a test: the only sender is the real `EmailSender` | D (no seam) |
| "Change which classes the app uses" | Edit `demo.py`, which also holds the scenario | S (two reasons to change) |

## 2. After: one job per class, rules depend on promises

```python
# version 2 (P04) - hotel_booking/booking.py
from .notifications import NotificationSender   # Protocol: send_confirmation(reservation)
from .stores import ReservationStore            # Protocol: count, has_overlap, save, find, count_confirmed

class BookingService:
    def __init__(self, rooms, store: ReservationStore, notifications: NotificationSender, slow_step_seconds=0.0): ...

# main.py - the composition root, the only place that picks real classes
def build_app(slow_step_seconds=0.0):
    store = InMemoryReservationStore()
    email = EmailNotificationSender()
    return BookingService(HOTEL_ROOMS, store, email, slow_step_seconds=slow_step_seconds), store, email
```

Pictures: [Classes - before / after and the dependency sketch](Diagrams.md).

| P03 class | After P04 | Kind of change | Why |
|---|---|---|---|
| `EmailSender` | `EmailNotificationSender`, keeps `NotificationSender` | rename + new protocol | The name says what it does; `BookingService` only knows the promise |
| `ReservationStore` (list) | `InMemoryReservationStore`, keeps `ReservationStore` (now the protocol) | rename + new protocol | The name says where rows live; P07 adds a database store next to it |
| `BookingService` | Same three public methods; constructor takes the two protocols | dependency inversion | Depends on promises, not on helpers |
| `demo.py` | Receives the service; no longer creates store or sender | single responsibility | Only `main.py` chooses the real classes |
| `Guest`, `Room`, `DateRange`, `Reservation`, `ReservationStatus` | Unchanged, already in `domain.py` since P03 | — | One job per module |
| (new) `SmsNotificationSender`, `FakeNotificationSender` (tests) | Keep `NotificationSender` | **feature**, after the refactoring | O: added without opening `BookingService` |
| `BookingResult` | `+notification_failed: bool` | **behaviour (R6)**, after the refactoring | A failed message must not lose or hide a booking |

## 3. Which SOLID principle each change serves

| Letter | Where it shows in version 2 | Checked by |
|---|---|---|
| **S** — one reason to change | `DateRange` (date rules), `InMemoryReservationStore` (keeping rows), `EmailNotificationSender` (sending), `BookingService` (the booking steps), `demo.py` (the scenario), `main.py` (wiring) | `test_only_main_creates_concrete_stores_and_senders` |
| **O** — extend by adding code | `SmsNotificationSender` is a new class; `booking.py` has the same SHA-256 before and after it was added | Evidence O6 (sha256), `test_sms_confirmations_need_no_change_to_booking_service` |
| **L** — any implementation can replace another | Email, SMS and the fake sender, and a second (dict) store, give identical answers and identical saved records; a sender that cancels the booking has the right method name but breaks the promise, and the scenario catches it | `tests/test_substitution.py` (9 tests) |
| **I** — small interfaces | `NotificationSender` has one method; storage and messaging are two separate protocols, so the SMS sender never has to pretend to save rows | `test_interfaces_are_protocols_with_the_drawn_operations` |
| **D** — rules depend on abstractions | `booking.py` imports only the two protocols; arrows from the concrete classes point up to them | `test_booking_rules_name_only_the_promises`, `test_booking_service_uses_only_the_interfaces`, mypy strict |

## 4. Behaviour before and after (accepted / full / error)

All rows **Observed** (Linux container, Python 3.13.18): the same scenario script was run against the
P03 code and the P04 code ([evidence O5](evidence/observed-runs.md#o5--beforeafter-behaviour-accepted-full-and-error-cases-and-the-saved-records)),
plus the demo and race diffs ([O4](evidence/observed-runs.md#o4--step-6--prove-that-nothing-changed)).

| Case | Request | Before (P03) | After (P04) | Same? |
|---|---|---|---|---|
| accepted | Maya R7 12–14 | `Accepted R101` | `Accepted R101` | yes |
| full | Omar R7 13–15 (shares the 13th) | `Unavailable`, nothing saved | `Unavailable`, nothing saved | yes |
| accepted (adjacent) | Nora R7 14–16 | `Accepted R102` | `Accepted R102` | yes |
| error | Omar R8 15–15 / 16–14 | `InvalidDates` ×2, nothing saved | `InvalidDates` ×2, nothing saved | yes |
| hotel full | free rooms 12–14 after R7 and R8 are taken | none | none | yes |
| cancel | R101, again, R999 | `True`, `False`, `False` | `True`, `False`, `False` | yes |
| saved records | after the scenario | R101 Maya R7 Cancelled · R102 Nora R7 Confirmed · R103 Omar R8 Confirmed | identical | yes |
| confirmations | count | 3 | 3 | yes |
| demo | `python main.py` | nine lines | `diff`: no difference | yes |
| race | `python main.py --race` | 2 Confirmed for R7 (double booking) | 2 Confirmed, 20 of 20 runs | yes — on purpose |
| **error: sender fails** | Maya R7 12–14, mail server down | `RuntimeError` escapes `reserve()`; R101 *is* saved, but the caller sees a crash instead of an answer (observed in Step 7.2a on the refactored code just before the R6 change — its `reserve` body was still the P03 one) | `Accepted R101`, `notification_failed=True`, R101 saved and Confirmed, warning logged | **no — new rule R6**, added after the refactoring, test first |

The last row is the only difference, and it is deliberate: it was made a separate step (Step 7.2)
with its own red-then-green test, so the refactoring itself can be shown to have changed nothing.

## 5. Decision record: how to express the two promises

**Context.** `BookingService` must stop naming concrete classes, and the course's Python track uses
`typing.Protocol`. The fake sender lives in the test file, and P07 will add a database store.

**Options.**
1. `typing.Protocol` (structural): any class with the right methods fits; no import of a base class.
2. `abc.ABC` with `@abstractmethod`, and every store/sender inherits from it (nominal).
3. No declared interface, plain duck typing with `Any` or no annotation.

**Decision: option 1, `typing.Protocol`.**
- It is what the course's Python reference uses, so the code reads like the lesson.
- Implementations stay independent: the test fake and a future PostgreSQL adapter need not import
  anything from the booking module to qualify; the promise is owned by the side that *uses* it.
- It is still checked: mypy strict verifies at every call site that the object passed in keeps the
  promise (`main.py`, the tests), and `tests/test_uml_conformance.py` checks each "implements" line of
  the diagram (same methods, same parameter names). Option 3 would lose both checks.

**Consequences and limitation.**
- Python does not stop a class from *claiming* the promise at runtime; a missing method shows up in
  mypy or in the conformance test, not at construction time (option 2 would fail at construction).
- No check, static or runtime, can prove *behaviour*: `CancellingSender` in `test_substitution.py` has
  the right signature and passes mypy, yet breaks the promise. Liskov substitution is protected only
  by behaviour tests such as the shared scenario.
- `_try_to_confirm` catches `Exception` broadly on purpose (any channel failure must keep the booking);
  the cost is that a programming error inside a sender is also turned into `notification_failed=True`.
  It is logged with its traceback so it is not silent.

## 6. Assumptions and limitations (what P04 does not do)

Assumptions: the senders are simulated (they count; nothing leaves the machine); one process; the
demo's nine lines and the race output are the accepted description of "behaviour".

- **The race is still there** (check-then-act between `has_overlap` and `save`). A refactoring must
  not fix bugs; P09 fixes it in the database. `test_race_double_books_r7_known_defect` still pins it.
- The demo pause `slow_step_seconds` is still a parameter of `BookingService` (0 normally) — a noted
  design smell, kept so the race can be shown.
- R6 *reports* a failed confirmation but nothing resends it; a retry or outbox is a later topic (P10).
- The second store in the tests (`DictReservationStore`) is a **Simulated** stand-in for the P07
  database adapter: it shows the storage promise is enough for `BookingService`, not that PostgreSQL
  will behave the same (that is **Proposed** for P07, together with the race fix in P09).
- Reservation ids still come from `count()`, fine for one process only.

## 7. Simulated vs executed

Everything in sections 3 and 4 marked as checked by a test or a diff was **executed** here
(evidence index E1–E13). The paper before-example in the [Worksheet](Worksheet.md#curriculum-plan-task-1--inspect-a-before-example)
is **Simulated** (reasoned, not run). Running the same checks on my Mac and the
classroom hand-over are **Proposed** and listed as "to do by the student".
