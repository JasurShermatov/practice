# P04 — Activity-sheet answers ("Your turn" steps)

Every "Your turn" block of the P04 activity sheet, in order, then the curriculum-plan tasks. Paths
starting with `hotel-booking/` are in the growing codebase; the rest are in this folder. Evidence
links point to [evidence/observed-runs.md](evidence/observed-runs.md) (O0–O8).

## Section 1 · Check that your P03 app still runs

| Item | Answer |
|---|---|
| Run the P03 demo — nine lines | Yes, before any change: identical to P03's expected output ([O0](evidence/observed-runs.md#o0--p03-still-runs-section-1-check-that-your-p03-app-still-runs)) |
| Run the race — "Double booking!" | Yes: `Confirmed reservations for R7 on 12-14 Nov: 2`, `Double booking! …` (O0) |
| Heading `# P04 design notes` at the bottom of `docs/design-notes.md` | Added: [design-notes.md § P04 design notes](../../hotel-booking/docs/design-notes.md#p04-design-notes) |

## Step 1 · Write down the rule for today

In [design-notes.md § Refactoring](../../hotel-booking/docs/design-notes.md#refactoring):

> A refactoring changes how the code is organised — names, files, which class depends on which — while
> everything the app does for a guest (every answer, every saved booking, every message) stays exactly
> the same.
>
> Must stay the same: the tests from Step 2 (all 6 pass after every move); the demo output (the same
> nine lines as in P03); the race demo (still "Double booking!" — refactoring does not fix bugs).

Applying the rule to the sheet's "Refactoring or not?" table: renaming `EmailSender`, moving
`DateRange`, and accepting an interface are refactorings (same output); fixing the race and adding SMS
are not (behaviour changes) — which is why SMS and R6 are a separate Step 7 here, and the race is left
for P09.

## Step 2 · Write the six tests and run them

| Item | Answer |
|---|---|
| Make the code reachable from the tests | Nothing to do in Python: `from hotel_booking import …` already worked |
| Test file the runner finds | [hotel-booking/test_booking_service.py](../../hotel-booking/test_booking_service.py) — `python -m unittest -v` finds it; `python -m pytest` runs it too (added to `testpaths`) |
| The six tests (free room, clash, adjacent stay, invalid dates, cancel, one confirmation per accepted booking) | As run on the P03 code: [step2/test_booking_service.py](step2/test_booking_service.py). Arrange–Act–Assert is marked in the clash test. `new_service()` is the only place that builds the service |
| Run: 6 passing | `Ran 6 tests in 0.000s` · `OK` on the **unchanged** P03 code ([O1](evidence/observed-runs.md#o1--step-2--six-characterization-tests-on-the-unchanged-p03-code)) |
| A test failed? | None did; the app was not changed in Step 2 |

Why no race test here: these are characterization tests of single requests; the race depends on
timing. (This portfolio already pins the race since P03 with a slowed-down, staggered run,
`test_race_double_books_r7_known_defect`; P09 flips it.)

## Step 3 · Write down what our code breaks

In [design-notes.md § What our code breaks](../../hotel-booking/docs/design-notes.md#what-our-code-breaks):

> - BookingService asks for exactly ReservationStore (D: dependency inversion). In P07 we would have
>   to edit BookingService just to use a database.
> - BookingService asks for exactly EmailSender (D, and therefore O: open/closed). The day the hotel
>   wants SMS confirmations we must open the class that holds the booking rules and change its
>   constructor and `reserve()` — a change for a messaging reason in a class whose job is booking.

Two more were written down (no seam to make the email fail — D; `demo.py` both tells the story and
picks the concrete classes — S) and the demo pause was noted but not fixed.

## Step 4 · Draw "Classes - after"

[Diagrams.md § 2](Diagrams.md#2-classes---after-the-activity-sheet-page) —
[uml/classes-after.mmd](uml/classes-after.mmd) / [.svg](uml/classes-after.svg).
Check with the sheet: **2 interfaces** (marked «interface»), **5 classes** (`FakeNotificationSender`
marked «tests only»), **2 "uses"** (dashed, open arrow), **4 "implements"** (dashed, hollow
triangle). The counts are asserted by `test_classes_after_page_has_the_counts_of_the_p04_checklist`.
Made in Mermaid instead of draw.io — see README "Substitutions".

## Step 5 · Refactor in six moves

The checks were run after **every** move ([O2](evidence/observed-runs.md#o2--steps-45--the-checks-after-every-move)).

| Move | What changed | Files | `python -m unittest` |
|---|---|---|---|
| 1 (5.1) | `NotificationSender` protocol; `EmailSender` → `EmailNotificationSender` (rename in every use) | `notifications.py`, uses in `booking.py`, `demo.py`, `__init__.py`, tests | 6 OK |
| 2 (5.2) | `ReservationStore` protocol; the list store → `InMemoryReservationStore` (the name `ReservationStore` is now the promise) | `stores.py`, uses | 6 OK |
| 3 (5.3 + 5.6) | `BookingService(rooms, store: ReservationStore, notifications: NotificationSender, …)`; method bodies unchanged; test helper uses the new names | `booking.py`, `test_booking_service.py` (`new_service` only) | 6 OK |
| 4 (5.4) | Data classes in their own module — already true since P03 (`domain.py`); nothing to move, no old file to delete | — | 6 OK |
| 5 (5.5) | `main.py` becomes the composition root (`build_app`); `demo.py` receives the service | `main.py`, `demo.py`, `tests/test_demo_and_race.py` (arrange only) | 6 OK |
| 6 | Run once more: still 6, no test body changed (diff shows only the import line and `new_service`) | — | 6 OK ([O3](evidence/observed-runs.md#o3--move-6--still-6-passing-and-no-test-body-changed)) |

The Python note "delete the old `hotel_booking.py`" does not apply: there never was a single file in
this portfolio.

## Step 6 · Run the checks and write the proof

In [design-notes.md § Proof](../../hotel-booking/docs/design-notes.md#proof):

> - Tests: `python -m unittest -v` → Ran 6 tests … OK after every move, and the 6 test bodies were not edited.
> - Demo: `python main.py` → the same nine lines as P03 (`diff` against the P03 output: no difference).
> - Race: `python main.py --race` → still double-booked (`Confirmed reservations for R7 on 12-14 Nov: 2`).

Line-by-line comparison of the demo: done with `diff`, no difference
([O4](evidence/observed-runs.md#o4--step-6--prove-that-nothing-changed)).

## Step 7 · Add the fake, rule R6 and SMS

| # | Item | Answer / evidence |
|---|---|---|
| 1 | `FakeNotificationSender` in the test file; helper `new_service(failing_sender=False)`; sixth test checks `["R101", "R102"]`; 6 green | [test_booking_service.py](../../hotel-booking/test_booking_service.py); `Ran 6 tests … OK` (O6, 7.1) |
| 2 | `## R6 · Failed message` in `docs/requirements.md` | [requirements.md § R6](../../hotel-booking/docs/requirements.md#r6--failed-message): "If the confirmation cannot be sent, the booking stays saved and Accepted, and the failure is reported." |
| 3 | R6 test added first — red | `FAILED (errors=1)`: `RuntimeError: The mail server is down.` escaped `reserve` (O6, 7.2a) |
| 4 | Change `BookingResult` and `reserve` — 7 green | `notification_failed: bool = False`; `reserve` calls `_try_to_confirm`, which catches the error, logs a warning and returns False; answer stays `Accepted R101` — `Ran 7 tests … OK` (O6, 7.2b). The test also asserts the warning (`assertLogs`), i.e. that the failure is *reported* |
| 5 | `SmsNotificationSender` + its test — 8 green | `notifications.py` (moved in P06 to [notifications/internal.py](../../hotel-booking/hotel_booking/notifications/internal.py)); `Ran 8 tests … OK` (O6, 7.3) |
| 6 | BookingService not edited for the SMS step | `sha256sum hotel_booking/booking.py` identical before and after the step (O6, 7.3) |

## Step 8 · Check and hand over your project

| File or page | It is finished when | Status |
|---|---|---|
| Tests | 8 tests pass: the 6 from Step 2 plus R6 and SMS | Done — `Ran 8 tests … OK` (O7) |
| App code | Constructor takes the storage and the notification promise; classes in separate modules | Done — `booking.py`, `stores.py`, `notifications.py`, `domain.py` |
| Demo and race | Same nine demo lines as P03; race still double-books | Done — O4, O7 (20/20) |
| `docs/requirements.md` | R6 added | Done |
| `docs/design-notes.md` | Refactoring, What our code breaks, Proof | Done (+ Target design, Feel the benefit) |
| "Classes - after" | 2 interfaces, 5 classes, 2 uses, 4 implements | Done (Mermaid; asserted by a test) |

Run everything one last time: done (O7). **Copy the folder to the partner's laptop and keep it for
P05: to do by the student.** Draft message for the hand-over:

> Here is our hotel-booking folder after P04 (ZIP). Same behaviour as P03 — nine demo lines, the race
> still double-books — but BookingService now only knows the ReservationStore and NotificationSender
> protocols and main.py wires the real classes. Run `python -m unittest -v` (8 tests) and
> `python main.py`. Keep it: P05 starts from it.

## Curriculum-plan task 1 · Inspect a before-example

The teacher-supplied starter ("a self-contained before-example mixing booking policy, SQL access and
email") is not in the downloaded materials, so this is a paper inspection of a minimal example of that
shape, written for this worksheet — **Simulated** (reasoned, not run) — and mapped to our code:

```python
def book(conn, smtp, guest_email, room, check_in, check_out):
    if check_out <= check_in:                                          # (a) policy: valid stay
        return "InvalidDates"
    clash = conn.execute("SELECT 1 FROM reservations WHERE room=? AND status='Confirmed' "
                         "AND check_in < ? AND ? < check_out", (room, check_out, check_in)).fetchone()
    if clash:                                                          # (b) policy + SQL mixed
        return "Unavailable"
    rid = conn.execute("INSERT INTO reservations(...) VALUES (...)", (...)).lastrowid   # (c) SQL
    smtp.sendmail("hotel@example.com", guest_email, f"Booked {rid}")   # (d) one email vendor
    return f"Accepted {rid}"
```

| Line | Responsibility | Reason it would change | Where it lives in version 2 |
|---|---|---|---|
| (a), the shape of (b) | booking policy | the hotel's rules | `DateRange.is_valid`, `DateRange.overlaps`, `BookingService.reserve` |
| SQL in (b), (c) | storage | database / schema | behind `ReservationStore` (`InMemoryReservationStore` now; PostgreSQL adapter in P07) |
| (d) | notification via one vendor | mail provider | behind `NotificationSender` (`EmailNotificationSender`, `SmsNotificationSender`) |

Three reasons to change in one function = three responsibilities (S). Problems seen on paper: the
overlap rule is written in SQL, so the reception desk's code could disagree; a mail error after the
INSERT raises out of `book()` although the booking exists — exactly the case R6 now covers; and nothing
can be tested without a database and a mail server.

## Curriculum-plan task 2 · Introduce a focused interface and name the principle

Two focused interfaces were introduced — `NotificationSender` (one method) and `ReservationStore`
(five methods BookingService actually calls) — serving **D** (the booking rules depend on promises,
`main.py` picks the adapters), which in turn gives **O** (SMS added without editing `BookingService`),
**L** (any sender/store that keeps the promise gives the same records) and **I** (two small promises,
not one big one). Explanation and checks: [Before-after.md § 3](Before-after.md#3-which-solid-principle-each-change-serves).

## Curriculum-plan task 3 · Compare accepted / full / error before and after; checks and a limitation

Comparison table: [Before-after.md § 4](Before-after.md#4-behaviour-before-and-after-accepted--full--error)
(all **Observed**: same answers and same saved records for P03 and P04; the only difference is the new
R6 row). Checks: `test_booking_service.py` (8), `tests/test_substitution.py` (9), demo/race diffs.
Limitation: the race is unchanged (by design) and the second store is only a stand-in for the P07
database — see [Before-after.md § 6](Before-after.md#6-assumptions-and-limitations-what-p04-does-not-do).

## Completed example of the curriculum plan, reproduced

*Starting situation:* reservation code directly calls one email vendor (`EmailSender`).
*Action:* replace the vendor dependency with a port (`NotificationSender`) implemented by adapters.
*Visible result:* the booking rule is unchanged when the provider changes —
`test_changing_the_provider_keeps_answers_and_saved_records[email|sms|fake]` all pass.
*Saved data/evidence:* accepted booking records stay the same — identical record lists for every
provider (test) and identical P03/P04 records (O5).
