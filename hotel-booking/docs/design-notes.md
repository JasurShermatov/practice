# P03 design notes

Short answers from each P03 step. Diagrams:
[practices/P03-hotel-domain-uml/Diagrams.md](../../practices/P03-hotel-domain-uml/Diagrams.md).
Later practices add their own sections below the P03 ones.

## Why design before code

Low-level design decides which classes exist (Guest, Room, DateRange, Reservation,
ReservationStore, EmailSender, BookingService), what each one keeps and does, and who calls whom —
for example that BookingService asks ReservationStore `has_overlap(room, stay)` before it saves.
Deciding this first gives every rule exactly one home: the overlap rule lives only in
`DateRange.overlaps()`, so the website and the reception desk can never disagree, and a rule change
(such as a cleaning day after each stay) is one edit, not two.

## Where the methods live

- **`cancel()` lives in `Reservation`**, because cancelling changes the reservation's own status and
  the "already cancelled → return False" rule must be checked in one place. Other code may not set
  the status directly (it is a read-only property); it has to ask the reservation.
- **`has_overlap(room, stay)` lives in `ReservationStore`**, because only the store can see all the
  reservations. It does not repeat the date rule: it asks each row `blocks(room, stay)`, and the
  row asks its `DateRange` `overlaps(...)`.
- `overlaps(other)` lives in `DateRange` (needs only the two pairs of dates); `blocks(room, stay)`
  in `Reservation` (only it knows its status, room and stay); `reserve(...)` in `BookingService`
  (it runs the steps in order: check, save, email, answer).

## Activity traces

Diagram: Activity - book (two decisions, then save → email → Accepted).

1. **Omar, R7, 13–15 Nov** (Maya has R7 12–14): first diamond "Check-out after check-in?" → Yes.
   Second diamond "A Confirmed booking shares a night?" → Yes, the night of the 13th. The request
   ends at **Unavailable · save nothing**.
2. **Nora, R7, 14–16 Nov** (Maya has R7 12–14): first diamond → Yes (16 > 14). Second diamond →
   No (Maya's last night is the 13th; 14 < 14 is false). Save the reservation as Confirmed → send
   the confirmation email → **Accepted R102**.
3. **Omar, R8, 15–15 Nov**: first diamond → No (check-out is not after check-in, zero nights). The
   request ends at **InvalidDates · save nothing**; the second diamond is never reached, so the
   store is not even asked.

## Prediction

Reasoned from the activity trace above (not from the output): Nora asks for R7 14–16 after Maya holds R7 12–14 and Omar was refused.
Prediction: **Accepted R102** — no shared night, and Omar's refused request saved nothing, so the
next id is R102.
Result (**Observed**): `Nora books R7 14-16 Nov: Accepted R102` — matches.

## The race

**Prediction** (reasoned from the check-then-save order of the sequence diagram): when Maya and Omar book R7 for 12–14 Nov at the same moment with a slow step
between check and save, R7 will end with **2 Confirmed reservations**, because both requests can
run `has_overlap` before either runs `save`.

**Result (Observed, `python main.py --race`):** `Maya: Accepted R101`, `Omar: Accepted R102`,
`Confirmed reservations for R7 on 12-14 Nov: 2` — the prediction held.

**What happened:** both requests checked the store while it was still empty, so both got "free",
and each then saved on the strength of its own out-of-date answer — R3 is broken although every
single-request example passes. The problem sits between `self._store.has_overlap(room, stay)` (the
check) and `self._store.save(reservation)` (the act) in `BookingService.reserve`: the two calls are
not one atomic step.

**Not fixed in P03, on purpose.** A lock in the code would only help while the app runs as one
process; real deployments run several copies. P09 fixes it in the database (locks / constraints)
after P07 adds one. The test `test_race_double_books_r7_known_defect` pins the defect so that the
fix will be visible as a deliberate test change.
