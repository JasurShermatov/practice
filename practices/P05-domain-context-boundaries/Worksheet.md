# P05 — Answers to every "Your turn"

One section per "Your turn" box of the activity sheet, in order. Most answers are files; this page
says where each one is and records the checks the sheet asks for.

## Start · check your starting point

1. Opened `hotel-booking/` (the P04 app).
2. Ran the tests. Course version: `python -m unittest -v` → 8 passing. Portfolio version:
   `python -m pytest` in `hotel-booking/`, run on a read-only snapshot copy so that P05 writes
   nothing into the project (evidence E1):

   ```text
   $ python -m unittest -v      # the course's 8 P04 tests (test_booking_service.py)
   Ran 8 tests in 0.002s
   OK
   $ python -m pytest -q        # the whole portfolio suite
   82 passed in 1.60s
   ```

   Full output: [evidence/observed-runs.md § O1](evidence/observed-runs.md#o1--starting-point-the-p04-tests).

3. `docs/` contains `requirements.md` (R1–R6) and `design-notes.md`. The P03/P04 diagrams are
   Mermaid files in the practice folders instead of `docs/diagrams.drawio` (P03 substitution).
   The L03 exit-check answers are in [docs/l03-notes.md](docs/l03-notes.md); today starts from
   answer 1 (Reservations owns the booking rule).
4. Created the two files of today: [docs/quality-scenarios.md](docs/quality-scenarios.md) and
   [docs/contexts.md](docs/contexts.md) (kept in the practice folder; see README "Where these
   files belong").

## Step 1 · write the six scenarios

[docs/quality-scenarios.md](docs/quality-scenarios.md): Stakeholders table, S3 copied from the
example, then S1, S2, S4, S5, S6 with the same seven lines.

- Step 1.2 (S1 split): Source = 200 guests; Stimulus = they search free rooms for 12–14 Nov;
  Environment = within one minute; Artifact = the free-room search in BookingService.
- Step 1.4 (tables render): checked by parsing every table (`test_six_quality_scenarios_…`).
- Step 1.5 (a number in every Measure): S1 "p95 ≤ 1 second; 0 wrong answers", S2 "100 Confirmed
  and 100 Unavailable; 0 double bookings", S3 "0 lost bookings", S4 "0 of 100", S5 "0 lines …
  at most 2 files", S6 "at least 20% fewer watt-hours per 1,000 completed searches".

Added beyond the sheet: a summary table with today's status of each scenario (S2 is **not met**
today — the P03 race), and which context each scenario presses on.

## Step 2 · write the Words table

[docs/contexts.md § Words](docs/contexts.md#words): 18 rows, each with a one-sentence meaning
(with a hotel example where possible) and its Python name, or "not in code yet" for Nightly price,
Out of service, Deposit, Paid, Declined, Sent, Failed. The 12 code names were checked against
the code (`test_every_code_name_in_the_words_table_exists_in_the_code`, parsing
`hotel_booking/` with `ast`). A short extra table lists words we met but did not add (Accepted /
Unavailable / InvalidDates, Refund, Channel …) and why.

## Step 3 · write the four contexts

[docs/contexts.md § Rooms](docs/contexts.md#rooms), [§ Reservations](docs/contexts.md#reservations),
[§ Payments](docs/contexts.md#payments), [§ Notifications](docs/contexts.md#notifications) — each
with "Job: …" and its own Words table.

Compared with the sheet's sorting check: Rooms 4 (Room, Room type, Nightly price, Out of
service), Reservations 8 (Guest, Stay, Reservation, Confirmed, Cancelled, Book, Cancel, Free rooms),
Payments 3 (Deposit, Paid, Declined), Notifications 3 (Confirmation message, Sent, Failed) =
18, each once. Same as the answer. "Room" is in Rooms, where its meaning is decided.

## Step 4 · write the words with two meanings

[docs/contexts.md § Same word, different meaning](docs/contexts.md#same-word-different-meaning):
Status, Room and Cancel in our own words, plus a Guest row.

The sentence: *If Notifications could set a reservation's status to Failed, a failed confirmation
email to Maya would overwrite R101's Confirmed with Failed, R7 would look free again for 12–14 Nov,
Omar could book it, and Maya would lose her room because of a message — breaking R6 and, through
it, R3.* Compared with the example: it names the guest who loses the room (Maya, R7) and the rule
(R6).

## Step 5 · give every rule one owner

[docs/contexts.md § Rule owners](docs/contexts.md#rule-owners): eight cards, one owner and a
one-sentence reason each; each context section lists its rules under "Rules this context owns:"
(Rooms 4, 5 · Reservations 1, 2, 3 · Payments 6, 7 · Notifications 8).

Compared with the "?" answers: all eight owners are the same. The reason for card 6 is
deliberately different: the course's example says Payments "asks Rooms for the nightly price",
which would add a Payments → Rooms arrow that the map (all arrows from Reservations) does not
have. Decision D1: Rooms prices the stay, Reservations passes that price, Payments applies the
30%.

## Step 6 · draw the page "Context map"

[diagrams/context-map.drawio](diagrams/context-map.drawio) (page "Context map", course layout:
Rooms top left, Payments top right, Reservations bottom left, Notifications bottom right),
plus [diagrams/context-map.mmd](diagrams/context-map.mmd) rendered to
[context-map.svg](diagrams/context-map.svg).

Step 6.7 check: 4 boxes, 1 green (Reservations); 3 labelled arrows, all starting at Reservations;
2 solid ("Asks: which rooms exist?", "Asks: take a deposit (P17)"), 1 green dotted ("Announces:
ReservationConfirmed"). Checked automatically for both files (`test_context_map_…`,
`test_drawio_page_…`); the Mermaid file was rendered with `mmdc` without errors (E2).

## Step 7 · write what crosses each border

[docs/contexts.md § Between contexts](docs/contexts.md#between-contexts):

- Reservations → Notifications: ReservationConfirmed (event) — copied, five fields.
- Reservations → Rooms: which rooms exist? (question) — Sent when, what Reservations sends
  (nothing today; the stay once "out of service" exists), the answer (number, type, later
  nightly price), Never crosses; plus the P17 question "what does this room cost for this stay?".
- Reservations → Payments: take a deposit (question, from P17) — reservation id and amount;
  answer Paid or Declined; Never crosses.

Step 7.4: every context section ends with "Needs from other contexts:" and "Tells other
contexts:" ("nothing" where there is nothing). Step 7.5: 3 subsections = 3 arrows, each with
fields (`test_between_contexts_…`).

## Step 8 · check and hand over

| File or page | It is finished when | Status |
|---|---|---|
| docs/quality-scenarios.md | Stakeholders table, S1–S6 with seven lines each; every Measure has a number | Done — checked |
| docs/contexts.md · Words | 18 words, each with a meaning and its code name (or "not in code yet") | Done — checked, code names exist |
| docs/contexts.md · four context sections | Job, Words, Rules this context owns, Needs, Tells | Done — checked |
| docs/contexts.md · Same word, different meaning | Room, Status, Cancel + the sentence | Done — checked |
| docs/contexts.md · Rule owners | 8 cards, one owner and a reason each | Done — checked |
| docs/contexts.md · Between contexts | 3 borders, each with its fields | Done — checked |
| Context map (draw.io page + Mermaid) | 4 boxes (Reservations green), 3 labelled arrows from Reservations | Done — checked, rendered |
| Code | Unchanged: the same tests pass | Unchanged — Observed (SHA-256 identical, E5) |

1. Went through the checklist with `checks/test_p05_docs.py` (26 checks, all passing, E3) and by
   reading each file.
2. Ran the project tests again: still 8 passing with `unittest` and 82 with `pytest`, the same nine demo lines, the race still double-books (E1, E2) — P05 changed no file in `hotel-booking/` (E5).
3. Copy the folder to the partner's laptop — **to do by the student**.
4. Keep the folder: P06 starts from it — the three `docs/*.md` files are copied into
   `hotel-booking/docs/` at the start of P06 (README, "Where these files belong").
