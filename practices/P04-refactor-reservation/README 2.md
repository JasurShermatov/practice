# P04 — Refactor a reservation design

**Session:** Saturday 24 October 2026, 09:30–10:50 (Asia/Tashkent) · Practice · Group 23-309 SW · Room 232
**Related lecture:** L02 — Object-oriented design, UML and SOLID
**Type of work:** refactoring of the growing [hotel-booking](../../hotel-booking/README.md) codebase
(version 1 → version 2), tests first, then two deliberate behaviour additions.

## Goal

Make the P03 booking app easy to change **without changing what it does**: lock today's behaviour
with tests, find what the design breaks (SOLID), draw the target, move `BookingService` onto two
interfaces in small safe moves, prove nothing changed — then use the new seams to add rule R6 (a failed
confirmation keeps the booking) and an SMS sender without touching `BookingService`.

## Outputs

| Output | File |
|---|---|
| Before/after design explanation: what was mixed, what moved where, SOLID per change, behaviour before vs after (accepted/full/error), decision + assumptions + limitations | [Before-after.md](Before-after.md) |
| Diagrams: Classes - before, **Classes - after** (activity page), full class diagram v2, before/after dependency sketch, R6 sequence | [Diagrams.md](Diagrams.md), sources + SVG in [uml/](uml/) |
| Answers to every "Your turn" step and the curriculum-plan tasks | [Worksheet.md](Worksheet.md) |
| The Step 2 tests exactly as they ran on the P03 code | [step2/test_booking_service.py](step2/test_booking_service.py) |
| The course's 8 `unittest` tests (Step 2 + Step 7) and the fake sender | [hotel-booking/test_booking_service.py](../../hotel-booking/test_booking_service.py) |
| Refactored code (version 2) | [hotel-booking/hotel_booking/](../../hotel-booking/hotel_booking/), [main.py](../../hotel-booking/main.py) |
| design-notes P04 sections: Refactoring, What our code breaks, Target design, Proof, Feel the benefit | [hotel-booking/docs/design-notes.md](../../hotel-booking/docs/design-notes.md#p04-design-notes) |
| R6 in the requirements | [hotel-booking/docs/requirements.md](../../hotel-booking/docs/requirements.md#r6--failed-message) |
| Extra checks: dependency rule (`ast`), substitution/Liskov, UML conformance v2, R6 sequence | [hotel-booking/tests/](../../hotel-booking/tests/) |
| Evidence index and real run outputs (after every move) | [evidence/Index.md](evidence/Index.md), [evidence/observed-runs.md](evidence/observed-runs.md), [evidence/logs/](evidence/logs/) |
| Before/after behaviour script | [evidence/compare_behaviour.py](evidence/compare_behaviour.py) |
| Individual reflection | [reflections/Jasur-Shermatov.md](reflections/Jasur-Shermatov.md) |

## How to run

```bash
cd hotel-booking
python3 -m unittest -v     # the course's command: 8 tests, nothing to install
python3 main.py            # the same nine lines as P03
python3 main.py --race     # still double-books (known defect until P09)
python3 -m pip install -r requirements.txt
python3 -m pytest          # 82 tests (8 unittest + 74 pytest)
python3 -m mypy            # strict type check
python3 -I ../practices/P04-refactor-reservation/evidence/compare_behaviour.py .   # before/after scenario
```

Re-render a diagram: `mmdc -i uml/classes-after.mmd -o uml/classes-after.svg`
(add `-p puppeteer.json` with `{"args": ["--no-sandbox"]}` inside a container).

## What changed in the code (version 1 → 2)

| File | Change | Kind |
|---|---|---|
| `hotel_booking/notifications.py` | `NotificationSender` protocol; `EmailSender` → `EmailNotificationSender`; `SmsNotificationSender` | refactoring; SMS = feature |
| `hotel_booking/stores.py` | `ReservationStore` protocol; the list store → `InMemoryReservationStore` | refactoring |
| `hotel_booking/booking.py` | Constructor takes the two protocols (`notifications` instead of `email`); `BookingResult.notification_failed`; `_try_to_confirm` | refactoring; R6 = behaviour |
| `hotel_booking/demo.py` | Receives the service, store and sender instead of creating them | refactoring |
| `main.py` | Composition root `build_app()` | refactoring |
| `hotel_booking/domain.py` | — | unchanged |
| `test_booking_service.py` (new, project root) | 6 characterization tests (Step 2) + R6 + SMS, `unittest`, `FakeNotificationSender` | tests |
| `tests/*` (P03 suite) | Kept green. Deliberate edits, each with a note in the module docstring: renamed classes in `conftest.py` and the spies of `test_sequences.py`; arrange part of `test_demo_and_race.py` (demo receives the service) + one `--race` test; `test_uml_conformance.py` now points `CLASS_DIAGRAM` at the P04 diagram and understands «interface» and "implements" | tests |
| `tests/test_dependency_rule.py`, `tests/test_substitution.py` (new) | D and L checked on the code | tests |
| `pyproject.toml`, `requirements.txt`, `README.md`, `docs/*` | version 0.4.0; root test file in `testpaths`; mypy also on the new tests; docs | docs/config |

## Substitutions (honest record)

| Course material uses | This portfolio uses | Why | Requirement still covered by |
|---|---|---|---|
| draw.io page "Classes - after" in `docs/diagrams.drawio` | Mermaid [uml/classes-after.mmd](uml/classes-after.mmd) + SVG | Same reason as P03: text diagrams can be diffed and a test can parse them — here the test counts 2 interfaces / 5 classes / 2 uses / 4 implements and checks every "implements" line against the code. draw.io can import it (Arrange → Insert → Advanced → Mermaid). | `test_classes_after_page_*` |
| Move 4: split one big `hotel_booking.py` into modules and delete it | Nothing to move | The P03 portfolio version was already a package (P03 Substitutions). | Evidence E3, [logs/m4.txt](evidence/logs/m4.txt) |
| `main.py` holds the scenario and the wiring | `main.py` = composition root (`build_app`); scenario stays in `hotel_booking/demo.py`, which now *receives* its collaborators | Keeps the scenario importable by tests while still having exactly one place that creates concrete classes (checked by `test_only_main_creates_concrete_stores_and_senders`). | E10 |
| `BookingResult("Accepted", …)` with a string | `BookingResult(BookingOutcome.ACCEPTED, …)` (enum since P03) | Closed set of answers; printing unchanged. | `str(result)` asserted by all 8 tests |
| `Reservation` with public mutable fields (course reference) | Read-only properties, status changed only by `cancel()` (kept from P03) | Encapsulation (L02); not touched by P04. | `tests/test_domain.py` |
| R6 "the failure is reported": a flag | The flag **and** a logged warning with the reservation id | A flag alone is lost if the caller ignores it; the log keeps a trace for resending. | `assertLogs` in the R6 test |
| Only the course's tests | Course's 8 `unittest` tests **plus** the P03 pytest suite and P04 extras | Portfolio rule: every behaviour gets an automated check; pytest runs the unittest file too. | `python -m pytest` (82) |

## Requirements checklist

Sources: Activity sheet (= Student notes = Presentation notes; the three files are identical apart
from the title), Student explanation (current curriculum plan), L02 sections 5 and 7 (the P04
preview), and the task brief.

| # | Requirement (source) | Where it is satisfied | Status |
|---|---|---|---|
| 1 | Check the P03 app still runs: demo and race (Activity §1) | [O0](evidence/observed-runs.md#o0--p03-still-runs-section-1-check-that-your-p03-app-still-runs) | Done — Observed |
| 2 | Heading `# P04 design notes` in design-notes.md (Activity §1.4) | [design-notes.md](../../hotel-booking/docs/design-notes.md#p04-design-notes) | Done |
| 3 | `## Refactoring`: own one-sentence definition + "Must stay the same:" with the three checks (Step 1) | [design-notes.md § Refactoring](../../hotel-booking/docs/design-notes.md#refactoring) | Done |
| 4 | Six characterization tests (free room, clash, adjacent, invalid dates, cancel, one confirmation per accepted booking) in a file the runner finds, passing on the P03 code; Python uses `unittest` (Step 2; L02 §7) | [test_booking_service.py](../../hotel-booking/test_booking_service.py), [step2/](step2/test_booking_service.py); E2 | Done — Observed |
| 5 | `## What our code breaks`: the completed example + a second problem in own words, with class, principle letter and what hurts (Step 3) | [design-notes.md](../../hotel-booking/docs/design-notes.md#what-our-code-breaks) | Done (4 problems + the noted demo pause) |
| 6 | "Classes - after": 2 interfaces, 5 classes («tests only» fake), 2 uses (dashed, open arrow), 4 implements (dashed, hollow triangle) (Step 4) | [Diagrams.md § 2](Diagrams.md#2-classes---after-the-activity-sheet-page); `test_classes_after_page_*` | Done (Mermaid, see Substitutions) |
| 7 | 5.1 notification promise + `EmailNotificationSender` (Step 5) | `notifications.py` | Done |
| 8 | 5.2 storage promise + `InMemoryReservationStore` (Step 5) | `stores.py` | Done |
| 9 | 5.3 `BookingService` constructor asks for the two promises; method bodies unchanged (Step 5) | `booking.py`; `test_booking_rules_name_only_the_promises` | Done |
| 10 | 5.4 data classes in their own module (Step 5) | `domain.py` (since P03) | Done (no-op, see Substitutions) |
| 11 | 5.5 entry point is the only place that picks the real store and sender (Step 5) | `main.py` `build_app`; `test_only_main_creates_concrete_stores_and_senders` | Done |
| 12 | 5.6 tests use the new names; only the helper changes (Step 5) | Diff in [O3](evidence/observed-runs.md#o3--move-6--still-6-passing-and-no-test-body-changed) | Done — Observed |
| 13 | Run the tests after **every** move; green each time (Step 5 "Your turn") | [O2](evidence/observed-runs.md#o2--steps-45--the-checks-after-every-move), E3 | Done — Observed |
| 14 | Step 6: run tests, demo, race; compare demo line by line; `## Proof` with three lines | [design-notes.md § Proof](../../hotel-booking/docs/design-notes.md#proof); E5 | Done — Observed |
| 15 | Race still double-books — refactoring does not fix bugs (Step 6; brief) | `test_race_double_books_r7_known_defect`, `test_main_race_flag_still_double_books`; E5 (20/20) | Done — kept on purpose until P09 |
| 16 | 7.1 `FakeNotificationSender` + helper; sixth test checks R101, R102 (Step 7) | `test_booking_service.py` | Done — Observed |
| 17 | 7.2 `## R6 · Failed message` in requirements.md (Step 7) | [requirements.md § R6](../../hotel-booking/docs/requirements.md#r6--failed-message) | Done |
| 18 | 7.2 R6 test first (red), then change `BookingResult` and `reserve` (7 green) (Step 7) | E7 | Done — Observed |
| 19 | 7.3 `SmsNotificationSender` + test (8 green); `BookingService` not edited (Step 7) | E8 (same SHA-256) | Done — Observed |
| 20 | Step 8 checklist: 8 tests; promises in the constructor; separate modules; same demo and race; R6; three design-note sections; diagram counts | [Worksheet § Step 8](Worksheet.md#step-8--check-and-hand-over-your-project) | Done |
| 21 | Run tests, demo, race one last time (Step 8.2) | [O7](evidence/observed-runs.md#o7--final-state-of-version-2) | Done — Observed |
| 22 | Copy the folder to the partner's laptop; keep it for P05 (Step 8.3–8.4) | Draft message in [Worksheet § Step 8](Worksheet.md#step-8--check-and-hand-over-your-project); E17 | **To do by the student** |
| 23 | Pair work on one laptop, swap typist each step (Activity "How you work today") | — | **To do by the student** (classroom) |
| 24 | Inspect a before-example mixing booking policy, SQL access and email (curriculum plan 1) | [Worksheet § task 1](Worksheet.md#curriculum-plan-task-1--inspect-a-before-example); E14 | Done — Simulated (paper; teacher starter not available) |
| 25 | Introduce a focused interface and explain the SOLID principle it serves (curriculum plan 2) | [Before-after.md § 3](Before-after.md#3-which-solid-principle-each-change-serves) | Done |
| 26 | Compare accepted/full/error behaviour before and after; checks and a limitation (curriculum plan 3) | [Before-after.md § 4, § 6](Before-after.md#4-behaviour-before-and-after-accepted--full--error); E6 | Done — Observed |
| 27 | Produce: before/after dependency sketch and behaviour checks (curriculum plan) | [Diagrams.md § 1, 2, 4](Diagrams.md#4-beforeafter-dependency-sketch); E6, E10, E11 | Done |
| 28 | Completed example: notification port + adapter; booking rule unchanged when the provider changes; accepted records stay the same (curriculum plan) | `test_changing_the_provider_keeps_answers_and_saved_records`; [Worksheet](Worksheet.md#completed-example-of-the-curriculum-plan-reproduced) | Done — Observed |
| 29 | Check: assumptions, a justified decision and its limitation; simulated vs executed distinguished (curriculum plan) | [Before-after.md § 5–7](Before-after.md#5-decision-record-how-to-express-the-two-promises); evidence labels | Done |
| 30 | SOLID: all five letters shown in the hotel app (Step 3) | [Before-after.md § 3](Before-after.md#3-which-solid-principle-each-change-serves) | Done |
| 31 | L02 exit-check answer 3 (OCP + DIP for SMS) now true in code | [l02-notes.md](../../hotel-booking/docs/l02-notes.md) (P04 update) | Done |
| 32 | Evolve the same codebase; keep P03 tests green or update deliberately with a note (brief) | 52 P03 tests still pass; edits listed above and in each module docstring | Done — Observed |
| 33 | UML conformance test points at the P04 class diagram (brief) | `CLASS_DIAGRAM` → [uml/class-diagram.mmd](uml/class-diagram.mmd) | Done — Observed |
| 34 | UML render-checked with `mmdc` (brief) | E13, [logs/mmdc.txt](evidence/logs/mmdc.txt) | Done — Observed |
| 35 | Same results on the student's Mac | E16 | **To do by the student** |

The explanation's "previous-syllabus reference" (threads, locks, lost updates) is marked by the course
as *not the current lesson instructions* and is not part of P04 (the race is P09's topic).

## Self-check before submission

- [x] Every refactoring move was followed by a test run, and the logs are kept
- [x] The six Step 2 test bodies were unchanged by the refactoring (diff in O3); only afterwards, in
      Step 7.1, the sixth test was changed on purpose (count → exact ids), as the activity sheet asks
- [x] The only behaviour differences are R6 and SMS, each added after the refactoring, test first
- [x] `BookingService` names no concrete store or sender — checked by a test, not by eye
- [x] The race is still there and still pinned; nothing claims it is fixed
- [x] Evidence is labelled Proposed / Simulated / Observed; nothing is claimed for the Mac or the classroom
