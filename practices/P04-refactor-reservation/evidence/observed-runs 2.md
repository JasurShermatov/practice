# Observed runs — P04

**Label:** Observed — every block below is real output, copied from the run (full logs in
[logs/](logs/)). Absolute paths are shortened to `<portfolio>/`.
**Environment:** Linux container (kernel 6.18), Python 3.13.18, pytest 9.1.1, mypy 2.3.1 (strict),
Mermaid CLI 11.16.0 with headless Chromium. **Run date:** 2026-11-21 (portfolio build).
**Working directory:** `hotel-booking/` unless stated. The student's Mac has not been used for these
runs; re-running there is listed in the README checklist.

The moves were done in the order of the activity sheet, and the checks were run **after each move**,
not only at the end. "Before" means the P03 code, copied aside before the first change (the P03 copy is
not part of the portfolio; its outputs are in `logs/b0-*.txt` and `logs/cmp-p03.txt`).

## O0 · P03 still runs (Section 1 "check that your P03 app still runs")

```text
$ python main.py
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

```text
$ python main.py --race
Maya and Omar both book R7 for 12-14 Nov at the same moment...
Maya: Accepted R101
Omar: Accepted R102
Confirmed reservations for R7 on 12-14 Nov: 2
Double booking! Both requests checked before either one saved.
```

`python -m pytest -q` on the P03 code: `52 passed` ([logs/b0-pytest.txt](logs/b0-pytest.txt)).

## O1 · Step 2 — six characterization tests on the unchanged P03 code

The file as it ran here is kept as [../step2/test_booking_service.py](../step2/test_booking_service.py).

```text
$ python -m unittest -v   # Step 2, on the unchanged P03 code
test_cancelling_frees_the_room_again (test_booking_service.BookingServiceTests.test_cancelling_frees_the_room_again) ... ok
test_check_out_must_be_after_check_in (test_booking_service.BookingServiceTests.test_check_out_must_be_after_check_in) ... ok
test_maya_gets_r7_when_it_is_free (test_booking_service.BookingServiceTests.test_maya_gets_r7_when_it_is_free) ... ok
test_nora_can_arrive_on_the_day_maya_leaves (test_booking_service.BookingServiceTests.test_nora_can_arrive_on_the_day_maya_leaves) ... ok
test_omar_is_refused_when_a_night_is_shared (test_booking_service.BookingServiceTests.test_omar_is_refused_when_a_night_is_shared) ... ok
test_one_confirmation_per_accepted_booking (test_booking_service.BookingServiceTests.test_one_confirmation_per_accepted_booking) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.000s

OK
```

The pytest suite collects the new file too: `58 passed` (52 P03 + 6) — [logs/s2-both.txt](logs/s2-both.txt).

## O2 · Steps 4–5 — the checks after every move

At Step 4 the target class diagram was drawn and `tests/test_uml_conformance.py` was pointed at it
(deliberately *before* the code moved), so the design tests are red until the code reaches the
target and turn green at the end of Step 7 (the target includes R6 and the SMS sender). The safety
net of the activity sheet is the 6 unittest tests: they were green after every move.

| Log | `python -m unittest` (the 6 Step 2 tests) | `python -m pytest -q` | failed | failed outside the design test |
|---|---|---|---|---|
| [s4](logs/s4.txt) | Ran 6 tests in 0.000s — OK | 15 failed, 51 passed in 1.14s | 15 (all in `test_uml_conformance.py`) | 0 |
| [m1](logs/m1.txt) | Ran 6 tests in 0.000s — OK | 14 failed, 52 passed in 1.19s | 14 (all in `test_uml_conformance.py`) | 0 |
| [m2](logs/m2.txt) | Ran 6 tests in 0.001s — OK | 12 failed, 54 passed in 1.23s | 12 (all in `test_uml_conformance.py`) | 0 |
| [m3](logs/m3.txt) | Ran 6 tests in 0.000s — OK | 12 failed, 54 passed in 1.21s | 12 (all in `test_uml_conformance.py`) | 0 |
| [m5](logs/m5.txt) | Ran 6 tests in 0.000s — OK | 12 failed, 55 passed in 1.78s | 12 (all in `test_uml_conformance.py`) | 0 |

Move 4 (data classes into their own module) had nothing to move — the P03 portfolio version was
already a package; the module listing and a green run are in [logs/m4.txt](logs/m4.txt).
In move 5 the arrange part of `tests/test_demo_and_race.py` changed on purpose (the demo functions now
receive the service from `main.build_app`); the expected outputs did not change.

## O3 · Move 6 — still 6 passing, and no test body changed

```text
### Move 6: run the tests once more - still 6 passing, no test body changed
$ python -m unittest -v
test_cancelling_frees_the_room_again (test_booking_service.BookingServiceTests.test_cancelling_frees_the_room_again) ... ok
test_check_out_must_be_after_check_in (test_booking_service.BookingServiceTests.test_check_out_must_be_after_check_in) ... ok
test_maya_gets_r7_when_it_is_free (test_booking_service.BookingServiceTests.test_maya_gets_r7_when_it_is_free) ... ok
test_nora_can_arrive_on_the_day_maya_leaves (test_booking_service.BookingServiceTests.test_nora_can_arrive_on_the_day_maya_leaves) ... ok
test_omar_is_refused_when_a_night_is_shared (test_booking_service.BookingServiceTests.test_omar_is_refused_when_a_night_is_shared) ... ok
test_one_confirmation_per_accepted_booking (test_booking_service.BookingServiceTests.test_one_confirmation_per_accepted_booking) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.001s

OK
$ diff -u step2/test_booking_service.py (as run on P03) test_booking_service.py (after move 5)
--- ../practices/P04-refactor-reservation/step2/test_booking_service.py
+++ test_booking_service.py
@@ -10,7 +10,7 @@
 import unittest
 from datetime import date
 
-from hotel_booking import BookingService, DateRange, EmailSender, Guest, ReservationStore, Room
+from hotel_booking import BookingService, DateRange, EmailNotificationSender, Guest, InMemoryReservationStore, Room
 
 R7 = Room("R7", "Standard")
 R8 = Room("R8", "Deluxe")
@@ -24,10 +24,10 @@
     return DateRange(date(2026, 11, check_in), date(2026, 11, check_out))
 
 
-def new_service() -> tuple[BookingService, ReservationStore, EmailSender]:
+def new_service() -> tuple[BookingService, InMemoryReservationStore, EmailNotificationSender]:
     """The only place that builds the service: a refactoring changes this function, not the tests."""
-    store = ReservationStore()
-    email = EmailSender()
+    store = InMemoryReservationStore()
+    email = EmailNotificationSender()
     return BookingService([R7, R8], store, email), store, email
 
 
(exit 1)
```

The diff touches only the import line and `new_service()` — the helper that builds the service, exactly
what activity 5.6 allows.

## O4 · Step 6 — prove that nothing changed

```text
### Step 6 - prove that nothing changed
$ python -m unittest -v
----------------------------------------------------------------------
Ran 6 tests in 0.001s

OK
$ python main.py
Free rooms 12-14 Nov: R7, R8
Maya books R7 12-14 Nov: Accepted R101
Omar books R7 13-15 Nov: Unavailable
Nora books R7 14-16 Nov: Accepted R102
Omar books R8 15-15 Nov: InvalidDates
Free rooms 12-14 Nov: R8
Maya cancels R101: True
Free rooms 12-14 Nov: R7, R8
Confirmation emails sent: 2
$ python main.py --race
Maya and Omar both book R7 for 12-14 Nov at the same moment...
Maya: Accepted R101
Omar: Accepted R102
Confirmed reservations for R7 on 12-14 Nov: 2
Double booking! Both requests checked before either one saved.

$ diff <P03 demo output> <P04 demo output>
(no difference, exit 0)
$ diff <P03 race output> <P04 race output>
(no difference, exit 0)
```

## O5 · Before/after behaviour: accepted, full and error cases, and the saved records

[compare_behaviour.py](compare_behaviour.py) runs one scenario (accepted, full, adjacent, two error
cases, a full hotel, three cancels) and prints every answer and every saved record. Run against the
P03 copy, against the code after Step 6, and against the final version 2:

```text
$ python -I evidence/compare_behaviour.py <P03 copy>          > cmp-p03.txt
$ python -I evidence/compare_behaviour.py hotel-booking       > cmp-p04-step6.txt   (after Step 6)
$ python -I evidence/compare_behaviour.py hotel-booking       > cmp-p04-final.txt   (after Step 7)
$ diff cmp-p03.txt cmp-p04-step6.txt   -> no difference
$ diff cmp-p03.txt cmp-p04-final.txt   -> no difference
```

```text
accepted Maya R7 12-14                -> Accepted R101
full     Omar R7 13-15                -> Unavailable
accepted Nora R7 14-16 (adjacent)     -> Accepted R102
error    Omar R8 15-15 (zero nights)  -> InvalidDates
error    Omar R8 16-14 (reversed)     -> InvalidDates
accepted Omar R8 12-14                -> Accepted R103
search   free 12-14                   -> (none - full)
full     Nora R8 13-14                -> Unavailable
cancel   cancel R101                  -> True
cancel   cancel R101 again            -> False
cancel   cancel R999 (unknown)        -> False
search   free 12-14                   -> R7
confirmations sent: 3
saved records: 3
  R101 Maya R7 2026-11-12..2026-11-14 Cancelled
  R102 Nora R7 2026-11-14..2026-11-16 Confirmed
  R103 Omar R8 2026-11-12..2026-11-14 Confirmed
```

## O6 · Step 7 — fake sender, R6 test first, SMS without touching BookingService

7.1 — fake sender, sixth test checks `["R101", "R102"]`: `Ran 6 tests … OK` ([logs/s71.txt](logs/s71.txt)).

7.2a — the R6 test added **before** changing `reserve` (expected red):

```text
### Step 7.2a - R6 test added BEFORE changing reserve (expected: red)
$ python -m unittest -v
test_a_failed_confirmation_keeps_the_booking (test_booking_service.BookingServiceTests.test_a_failed_confirmation_keeps_the_booking)
R6: the sender fails after the save; the booking stays saved and Accepted, the failure is reported. ... ERROR
test_cancelling_frees_the_room_again (test_booking_service.BookingServiceTests.test_cancelling_frees_the_room_again) ... ok
test_check_out_must_be_after_check_in (test_booking_service.BookingServiceTests.test_check_out_must_be_after_check_in) ... ok
test_maya_gets_r7_when_it_is_free (test_booking_service.BookingServiceTests.test_maya_gets_r7_when_it_is_free) ... ok
test_nora_can_arrive_on_the_day_maya_leaves (test_booking_service.BookingServiceTests.test_nora_can_arrive_on_the_day_maya_leaves) ... ok
test_omar_is_refused_when_a_night_is_shared (test_booking_service.BookingServiceTests.test_omar_is_refused_when_a_night_is_shared) ... ok
test_one_confirmation_per_accepted_booking (test_booking_service.BookingServiceTests.test_one_confirmation_per_accepted_booking) ... ok

======================================================================
ERROR: test_a_failed_confirmation_keeps_the_booking (test_booking_service.BookingServiceTests.test_a_failed_confirmation_keeps_the_booking)
R6: the sender fails after the save; the booking stays saved and Accepted, the failure is reported.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<portfolio>/hotel-booking/test_booking_service.py", line 89, in test_a_failed_confirmation_keeps_the_booking
    result = service.reserve(MAYA, R7, nov(12, 14))
  File "<portfolio>/hotel-booking/hotel_booking/booking.py", line 87, in reserve
    self._notifications.send_confirmation(reservation)  # only after the save
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^
  File "<portfolio>/hotel-booking/test_booking_service.py", line 38, in send_confirmation
    raise RuntimeError("The mail server is down.")
RuntimeError: The mail server is down.

----------------------------------------------------------------------
Ran 7 tests in 0.002s

FAILED (errors=1)
(exit code 1)
```

7.2b — `BookingResult.notification_failed` + `_try_to_confirm` in `reserve`: `Ran 7 tests … OK`
([logs/s72-green.txt](logs/s72-green.txt)).

7.3 — `SmsNotificationSender` and its test; `booking.py` not edited:

```text
### Step 7.3 - SmsNotificationSender + its test; BookingService not edited
$ python -m unittest -v
test_a_failed_confirmation_keeps_the_booking (test_booking_service.BookingServiceTests.test_a_failed_confirmation_keeps_the_booking)
R6: the sender fails after the save; the booking stays saved and Accepted, the failure is reported. ... ok
test_cancelling_frees_the_room_again (test_booking_service.BookingServiceTests.test_cancelling_frees_the_room_again) ... ok
test_check_out_must_be_after_check_in (test_booking_service.BookingServiceTests.test_check_out_must_be_after_check_in) ... ok
test_maya_gets_r7_when_it_is_free (test_booking_service.BookingServiceTests.test_maya_gets_r7_when_it_is_free) ... ok
test_nora_can_arrive_on_the_day_maya_leaves (test_booking_service.BookingServiceTests.test_nora_can_arrive_on_the_day_maya_leaves) ... ok
test_omar_is_refused_when_a_night_is_shared (test_booking_service.BookingServiceTests.test_omar_is_refused_when_a_night_is_shared) ... ok
test_one_confirmation_per_accepted_booking (test_booking_service.BookingServiceTests.test_one_confirmation_per_accepted_booking) ... ok
test_sms_confirmations_need_no_change_to_booking_service (test_booking_service.BookingServiceTests.test_sms_confirmations_need_no_change_to_booking_service) ... ok

----------------------------------------------------------------------
Ran 8 tests in 0.002s

OK
$ sha256sum hotel_booking/booking.py   # before the SMS step
88a75bebc59c4fadd9415245cdc0bad9b17acd7317cc99686ff036194e717ab3  hotel_booking/booking.py
$ sha256sum hotel_booking/booking.py   # after the SMS step
88a75bebc59c4fadd9415245cdc0bad9b17acd7317cc99686ff036194e717ab3  hotel_booking/booking.py
```

## O7 · Final state of version 2

`python -m unittest -v` (the course's command, [logs/final-unittest.txt](logs/final-unittest.txt)):

```text
----------------------------------------------------------------------
Ran 8 tests in 0.002s

OK
```

`python -m pytest -v` ([logs/final-pytest.txt](logs/final-pytest.txt)) — 82 tests: 8 in
`test_booking_service.py`, 14 `tests/test_booking_service.py`, 5 `test_demo_and_race.py`, 3
`test_dependency_rule.py`, 17 `test_domain.py`, 6 `test_sequences.py`, 9 `test_substitution.py`, 20
`test_uml_conformance.py`:

```text
============================== 82 passed in 1.70s ==============================
```

`python -m mypy` (strict; package, `main.py`, the unittest file and the two new P04 test modules):

```text
$ python -m mypy
Success: no issues found in 10 source files
```

Race repeated 20 times (`for i in $(seq 1 20); do python main.py --race | grep Confirmed; done | sort | uniq -c`):

```text
     20 Confirmed reservations for R7 on 12-14 Nov: 2
```

## O8 · Diagram render check

```text
$ for f in uml/*.mmd; do mmdc -p puppeteer.json -i $f -o ${f%.mmd}.svg; done
OK   uml/class-before.mmd -> uml/class-before.svg (25407 bytes)
OK   uml/class-diagram.mmd -> uml/class-diagram.svg (80483 bytes)
OK   uml/classes-after.mmd -> uml/classes-after.svg (41769 bytes)
OK   uml/dependency-before-after.mmd -> uml/dependency-before-after.svg (30118 bytes)
OK   uml/sequence-r6-failed-confirmation.mmd -> uml/sequence-r6-failed-confirmation.svg (32015 bytes)
$ mmdc -p puppeteer.json -i Diagrams.md -o <scratch>/Diagrams.out.md
Found 5 mermaid charts in Markdown input
 ✅ ./Diagrams.out-1.svg
 ✅ ./Diagrams.out-2.svg
 ✅ ./Diagrams.out-3.svg
 ✅ ./Diagrams.out-4.svg
 ✅ ./Diagrams.out-5.svg
 ✅ <scratch>/mdcheck/Diagrams.out.md
exit 0
  Diagrams.out-1.svg
  Diagrams.out-2.svg
  Diagrams.out-3.svg
  Diagrams.out-4.svg
  Diagrams.out-5.svg
  Diagrams.out.md
puppeteer.json = {"executablePath": "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome", "args": ["--no-sandbox"]}
```
