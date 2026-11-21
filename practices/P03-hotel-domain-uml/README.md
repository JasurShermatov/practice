# P03 — Hotel booking domain and UML workshop

**Session:** Tuesday 20 October 2026, 18:00–19:20 (Asia/Tashkent) · Practice · Group 23-309 SW · Room 222
**Related lecture:** L02 — Object-oriented design, UML and SOLID
**Type of work:** design (requirements, five UML views) and the first version of the course
project's code. This is the **first practice of the growing hotel-booking project**.

## Goal

Model a small fictional hotel's booking workflow — search dated availability, book a room, refuse
a clash, cancel, view — as requirements and UML (use case, class, sequence, activity), turn the
class diagram into running code, and watch the design's first real bug: two simultaneous requests
double-book the same room.

## Outputs

| Output | File |
|---|---|
| Domain explanation: brief, glossary, **invariant**, responsibilities, assumptions, justified decision + limitation | [Domain.md](Domain.md) |
| All UML, embedded and explained, with relationship → requirement mapping | [Diagrams.md](Diagrams.md) |
| Mermaid sources + rendered SVGs | [uml/](uml/) — `use-case-diagram`, `class-diagram`, `sequence-book`, `sequence-unavailable`, `sequence-cancel`, `activity-book`, `sequence-race`, `state-reservation` |
| Answers to every "Your turn" step and the curriculum-plan tasks | [Worksheet.md](Worksheet.md) |
| Requirements R1–R5 (Check + Proof lines) | [hotel-booking/docs/requirements.md](../../hotel-booking/docs/requirements.md) |
| Design notes (Why design, Where the methods live, Activity traces, Prediction, The race) | [hotel-booking/docs/design-notes.md](../../hotel-booking/docs/design-notes.md) |
| L02 exit-check answers (start of the folder) | [hotel-booking/docs/l02-notes.md](../../hotel-booking/docs/l02-notes.md) |
| Code: version 1 of the app + tests | [hotel-booking/](../../hotel-booking/README.md) |
| Evidence index and real run outputs | [evidence/Index.md](evidence/Index.md), [evidence/observed-runs.md](evidence/observed-runs.md) |
| Individual reflection | [reflections/Jasur-Shermatov.md](reflections/Jasur-Shermatov.md) |

Requirements and design notes live inside `hotel-booking/docs/` because the activity sheet puts
them in the project folder and P04 extends the same files (R6, new design-note sections).

## How to run

```bash
cd hotel-booking
python3 -m pip install -r requirements.txt   # pytest only
python3 main.py            # nine demo lines
python3 main.py --race     # the double booking (known defect until P09)
python3 -m pytest          # 52 tests
```

Re-render a diagram: `mmdc -i uml/class-diagram.mmd -o uml/class-diagram.svg`
(add `-p puppeteer.json` with `{"args": ["--no-sandbox"]}` inside a container).

## Substitutions (honest record)

| Course material uses | This portfolio uses | Why | Requirement still covered by |
|---|---|---|---|
| draw.io file `docs/diagrams.drawio` with 5 pages | Mermaid sources `uml/*.mmd` + SVG, gathered in Diagrams.md | Text diagrams can be diffed, reviewed and render-checked automatically, and a test can compare the class diagram with the code. draw.io can import them (Arrange → Insert → Advanced → Mermaid) if the teacher wants the `.drawio` file. | Same five pages (Use cases, Classes, Sequence - book, Sequence - cancel, Activity - book), plus three extra views |
| One file `hotel_booking.py` | Package `hotel_booking/` (5 small modules) + `main.py` | Small cohesive modules are a portfolio convention; one module per class group keeps later practices' changes local. Classes, methods and behaviour are those of the class diagram; nothing from P04 (interfaces, renaming) is implemented. | `test_uml_conformance.py`, identical demo output |
| No tests in P03 (tests start in P04 with `unittest`) | `pytest` tests from the start | Every behaviour the practice asks for gets an automated check (portfolio rule). P04 can still add its "lock the behaviour" tests. | `python -m pytest` |
| `BookingResult("Accepted")` with a string | `BookingResult(BookingOutcome.ACCEPTED)` | A closed enumeration instead of free text; printing is unchanged (`Accepted R101`). | `test_demo_prints_the_nine_expected_lines` |

## Requirements checklist

Every requirement found in the P03 materials (Student explanation = current curriculum plan,
Activity sheet = Student notes = Presentation notes, which are identical) and the L02 parts P03
depends on.

| # | Requirement (source) | Where it is satisfied | Status |
|---|---|---|---|
| 1 | Set up `hotel-booking/` with `docs/requirements.md`, `docs/design-notes.md`, diagrams (Activity §1) | `hotel-booking/docs/`, `uml/` | Done (diagrams as Mermaid, see Substitutions) |
| 2 | Language version printed (Activity §1.5) | Python 3.13.18 in [observed-runs.md](evidence/observed-runs.md) | Done in container; on the Mac **to do by the student** |
| 3 | design-notes "Why design before code" — classes, data/behaviour, who calls whom (Activity §2) | [design-notes.md](../../hotel-booking/docs/design-notes.md#why-design-before-code) | Done |
| 4 | requirements.md R1–R5 with requirement sentence + Check line (Activity §3) | [requirements.md](../../hotel-booking/docs/requirements.md) | Done |
| 5 | Under R3: three R7 night-by-night examples + two own R8 examples (20–22 booked), shared night named (Activity §3.4–3.5) | requirements.md R3; `test_r3_own_examples_for_r8_booked_20_to_22` | Done |
| 6 | Partner guesses the R8 results (Activity §3.6) | — | **To do by the student** (pair work) |
| 7 | Use case diagram: 2 actors outside, 4 use cases inside, 8 plain lines; one sentence per Cancel line (Activity §4) | [Diagrams.md §1](Diagrams.md#1-use-cases) | Done |
| 8 | Class diagram: 8 boxes, attributes/methods as completed diagram, «enumeration», multiplicities, composition, 2 dashed "uses" (Activity §5) | [Diagrams.md §2](Diagrams.md#2-classes), `uml/class-diagram.mmd` | Done (10 boxes / 11 links; extras explained) |
| 9 | design-notes "Where the methods live" for Cancel() and HasOverlap() (Activity §5.8) | [design-notes.md](../../hotel-booking/docs/design-notes.md#where-the-methods-live) | Done |
| 10 | Sequence - book and Sequence - cancel with numbered messages, replies dashed (Activity §6) | [Diagrams.md §3, §4](Diagrams.md#3-sequence---book-success-path); `test_sequences.py` | Done |
| 11 | Activity - book: start, 2 decisions with Yes/No, actions, end (Activity §7) | [Diagrams.md §5](Diagrams.md#5-activity---book) | Done |
| 12 | Three activity traces: Omar R7 13–15, Nora R7 14–16, Omar R8 15–15 (Activity §7.4–7.6) | [design-notes.md](../../hotel-booking/docs/design-notes.md#activity-traces) | Done |
| 13 | Code following the class diagram 1:1 (DateRange, Guest, Room, ReservationStatus, Reservation, ReservationStore, EmailSender, BookingResult, BookingService, demo) (Activity §8) | `hotel-booking/hotel_booking/`, `main.py`; `test_uml_conformance.py` | Done — Observed |
| 14 | Prediction for Nora before comparing output (Activity §8.3) | [design-notes.md § Prediction](../../hotel-booking/docs/design-notes.md#prediction) | Done (reasoned from the trace) |
| 15 | Program prints the nine expected lines (Activity §8.4) | `test_demo_prints_the_nine_expected_lines`; [O1](evidence/observed-runs.md) | Done — Observed |
| 16 | Proof line under every requirement R1–R5 (Activity §8.5) | [requirements.md](../../hotel-booking/docs/requirements.md) | Done (R5 proof is a test run) |
| 17 | Race: prediction, run `--race`, compare, two-sentence explanation naming the two calls (Activity §9) | [design-notes.md § The race](../../hotel-booking/docs/design-notes.md#the-race); [O2](evidence/observed-runs.md); `test_race_double_books_r7_known_defect` | Done — Observed |
| 18 | Do **not** fix the race in P03 (Activity §9: fixed in P09) | Race kept; pinned as known defect | Done |
| 19 | P03 checklist + run again normally and with `--race` (Activity §10.1–10.2) | [Worksheet.md § Step 9](Worksheet.md#step-9--check-and-hand-over) | Done |
| 20 | Pair next door reads "The race" section (Activity §10.3) | Evidence E10 (Proposed) | **To do by the student** |
| 21 | Copy folder to partner's laptop; keep it for P04 (Activity §10.4–10.5) | — | **To do by the student** |
| 22 | Assign responsibilities to Room, DateRange, Reservation and Notification (curriculum plan 2) | [Domain.md § Responsibilities](Domain.md#responsibilities) | Done |
| 23 | Multiplicities and justification of composition vs inheritance (curriculum plan 2; L02 §12–13) | [Diagrams.md §2](Diagrams.md#2-classes) | Done |
| 24 | Trace success and no-availability paths (curriculum plan 3; L02 §4) | [Diagrams.md §3, §3b](Diagrams.md#3b-sequence---book-no-availability-path); `test_sequence_unavailable_omar_r7` | Done |
| 25 | Map each relationship to a stated requirement (curriculum plan 3) | Relationship table, [Diagrams.md §2](Diagrams.md#2-classes) | Done |
| 26 | Produce a class diagram, booking sequence and **invariant** (curriculum plan) | Diagrams.md §2–3; [Domain.md § Invariant](Domain.md#invariant) | Done |
| 27 | Completed example: R7 12–14 accepted, overlapping request rejected, one accepted reservation saved (curriculum plan) | Demo lines 2–3; `test_r2_accepted_booking_is_saved_confirmed_and_emailed` | Done — Observed |
| 28 | Check: assumptions, a justified decision and its limitation; simulated vs executed distinguished (curriculum plan) | [Domain.md](Domain.md#assumptions); [evidence/Index.md](evidence/Index.md) labels | Done |
| 29 | Entity vs value, encapsulated status, reservation states (L02 §8, §16) | `domain.py` (frozen `DateRange`, read-only `status`); [Diagrams.md §7](Diagrams.md#7-reservation-states); `test_domain.py` | Done |
| 30 | L02 exit check: three answers in `docs/l02-notes.md` (L02 §8; folder layout for P03) | [l02-notes.md](../../hotel-booking/docs/l02-notes.md) | Done |
| 31 | Code and UML match exactly (own standard) | `test_uml_conformance.py` (12 tests), `test_sequences.py` (5 tests) | Done — Observed |
| 32 | Pair work at one laptop, swapping typist each step; attendance (Activity §1) | — | **To do by the student** (classroom) |

The explanation's "previous-syllabus reference" (locked queues/counters, throughput table) is
marked by the course as *not the current lesson instructions* and is not part of P03.

## Self-check before submission

- [x] Every class box is a class and every operation a method (checked by a test, not by eye)
- [x] Every sequence diagram's message order is recorded from the running code
- [x] "Confirmed" means a saved reservation that blocks its room, in every file
- [x] The race is shown, explained and **not** fixed; the fix is left to P09
- [x] Evidence is labelled Proposed / Simulated / Observed; nothing is claimed for the Mac or the classroom that has not happened
