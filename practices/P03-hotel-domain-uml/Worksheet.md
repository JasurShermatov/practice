# P03 — Activity-sheet answers ("Your turn" steps)

Every "Your turn" block of the P03 activity sheet, in order, with the answer or the file that holds
it. Paths starting with `hotel-booking/` are in the growing codebase; the rest are in this folder.

## Step 0 · Set up the P03 project folder

| Item | Answer |
|---|---|
| `hotel-booking/` with `docs/` | [hotel-booking/](../../hotel-booking/) with [docs/](../../hotel-booking/docs/) |
| `docs/requirements.md`, `docs/design-notes.md` | [requirements.md](../../hotel-booking/docs/requirements.md), [design-notes.md](../../hotel-booking/docs/design-notes.md) |
| `docs/diagrams.drawio` | Replaced by Mermaid sources [uml/](uml/) — see README "Substitutions" |
| Language version printed | `Python 3.13.18` in the build container (course needs ≥ 3.10; the project targets ≥ 3.12). On the Mac: `python3 --version` — **to do by the student**. |

## Step 1 · Why design before code

> Low-level design decides which classes exist, what each one keeps and does, and who calls whom —
> so every rule (like the overlap check in `DateRange.overlaps`) has exactly one home and the
> website and the reception desk can never give different answers.

Self-check: mentions classes ✔, what they keep/do ✔, who calls whom ✔. Full note:
[design-notes.md § Why design before code](../../hotel-booking/docs/design-notes.md#why-design-before-code).

## Step 2 · Requirements

R1–R5 with a Check line each, the three "R7, night by night" examples and two own R8 examples
under R3: [hotel-booking/docs/requirements.md](../../hotel-booking/docs/requirements.md).

Own R8 examples (R8 already booked 20–22 Nov):

| Request | Result | Reason |
|---|---|---|
| Maya R8 22–24 | Accepted | starts on the check-out day; no shared night |
| Omar R8 21–23 | Unavailable | night of the 21st is shared |

Both are automated in `test_r3_own_examples_for_r8_booked_20_to_22`. Step 2.6 (partner guesses
the results without seeing them) is pair work — **to do in class**.

## Step 3 · Use case diagram

2 actors outside the box, 4 goals inside, 8 lines: [Diagrams.md §1](Diagrams.md#1-use-cases).
One sentence per Cancel line: *A guest cancels her own booking on the website. A receptionist
cancels a booking for a guest who phones.*

## Step 4 · Class diagram

All boxes and links: [Diagrams.md §2](Diagrams.md#2-classes) (10 boxes / 11 links — the course's 8
boxes and 7 links plus the result types and two links the code has; reasons listed at the end of
Diagrams.md). "Where the methods live" (Cancel, HasOverlap):
[design-notes.md](../../hotel-booking/docs/design-notes.md#where-the-methods-live).

## Step 5 · Sequence diagrams

- Sequence - book: [Diagrams.md §3](Diagrams.md#3-sequence---book-success-path)
- Sequence - cancel (drawn from the textual description, then compared with the sheet's answer —
  same 6 messages: cancel, find, R101, cancel(), true, true): [Diagrams.md §4](Diagrams.md#4-sequence---cancel)
- Extra, the no-availability path required by the current curriculum plan: [Diagrams.md §3b](Diagrams.md#3b-sequence---book-no-availability-path)

## Step 6 · Activity diagram and traces

Diagram: [Diagrams.md §5](Diagrams.md#5-activity---book). Three traces (Omar R7 13–15, Nora R7
14–16, Omar R8 15–15): [design-notes.md § Activity traces](../../hotel-booking/docs/design-notes.md#activity-traces).

## Step 7 · Write, run and prove the program

| Item | Where |
|---|---|
| Code typed from the class diagram | [hotel-booking/hotel_booking/](../../hotel-booking/hotel_booking/) (`domain.py`, `stores.py`, `notifications.py`, `booking.py`, `demo.py`) and `main.py` |
| Prediction for Nora | Accepted R102 — [design-notes.md § Prediction](../../hotel-booking/docs/design-notes.md#prediction) |
| Program prints the nine lines | [evidence/observed-runs.md O1](evidence/observed-runs.md) |
| Proof line under every requirement | [requirements.md](../../hotel-booking/docs/requirements.md) (R5's proof is a test, because the demo has no View line) |

## Step 8 · The race

Prediction, observed output and the two-sentence explanation (between `has_overlap` and `save`):
[design-notes.md § The race](../../hotel-booking/docs/design-notes.md#the-race). Message-by-message
diagram and timeline: [Diagrams.md §6](Diagrams.md#6-the-race-step-8).

## Step 9 · Check and hand over

| Checklist row (activity sheet) | Status |
|---|---|
| requirements.md: R1–R5 each with Check and Proof; R3 has five examples | ✔ |
| design-notes.md: Why design before code, Where the methods live, Activity traces, Prediction, The race | ✔ |
| Use cases: 2 actors outside, 4 goals inside, 8 lines | ✔ |
| Classes: the course's 8 boxes and 7 links present | ✔ (plus 2 boxes / 4 links that the code needs) |
| Sequence - book and Sequence - cancel: 4 lifelines, 6 numbered messages | Cancel ✔ exactly. Book: 6 lifelines (Maya, BookingService, stay, store, email, created R101), 12 messages — more detailed on purpose, so it matches the code |
| Activity - book: start, two diamonds with Yes/No, actions, end | ✔ |
| Program runs, prints nine lines, `--race` shows the double booking | ✔ Observed |
| 9.3 Pair next door reads "The race" and says whether it is clear | **To do by the student** (classroom) |
| 9.4 Copy the folder to the partner's laptop | **To do by the student** |

## Current curriculum plan (18 Oct 2026) — tasks 1–3 and "Check"

| Item | Answer |
|---|---|
| 1. Read the brief: search dated availability, request a reservation, receive its status; payment simulated | [Domain.md § The brief](Domain.md#the-brief-fictional-classroom-case) |
| 2. Responsibilities of Room, DateRange, Reservation and Notification; multiplicities; composition vs inheritance | [Domain.md § Responsibilities](Domain.md#responsibilities), [Diagrams.md §2](Diagrams.md#2-classes) (link table + "Composition versus inheritance") |
| 3. Trace success and no-availability paths; map each relationship to a requirement | [Diagrams.md §3, §3b](Diagrams.md#3-sequence---book-success-path); relationship → requirement column in [Diagrams.md §2](Diagrams.md#2-classes) |
| Produce: class diagram, booking sequence, invariant | Diagrams.md §2, §3; [Domain.md § Invariant](Domain.md#invariant) |
| Completed example: R7 12–14 accepted, overlapping second request rejected; save one accepted reservation | Demo lines 2–3; `test_r2_accepted_booking_is_saved_confirmed_and_emailed` checks the saved R101 |
| Check: assumptions, a justified decision and its limitation; simulated vs executed | [Domain.md § Assumptions / Justified decision](Domain.md#assumptions); labels in [evidence/Index.md](evidence/Index.md) |

The "previous-syllabus reference" section of the explanation (locked counters/queues, throughput
table) is marked by the course as *not the current lesson instructions*, so it is not answered here.
