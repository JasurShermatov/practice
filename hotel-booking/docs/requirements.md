# Requirements: hotel booking app, version 1

Fictional classroom case (P03). Rooms R7 (Standard) and R8 (Deluxe); guests book on the website,
a receptionist books for guests who phone or walk in. Both go into **one** shared list of
reservations.

**Stay rule (half-open range).** A stay `12–14 Nov` means the nights of the 12th and the 13th.
The check-in day counts, the check-out day does not, so a new guest may check in on the day the
previous guest checks out. Two stays clash only when they share a night:
`a.check_in < b.check_out and b.check_in < a.check_out`.

**Invariant (the rule the whole course protects).** For every room and every night, at most one
reservation with status *Confirmed* covers that night.

Not in version 1: prices, payments, invoices, logins, housekeeping. Reservations live in memory and
are lost on restart.

Proof lines below are copied from the program output and the test run recorded in
[practices/P03-hotel-domain-uml/evidence/observed-runs.md](../../practices/P03-hotel-domain-uml/evidence/observed-runs.md)
(**Observed**, Linux container, Python 3.13).

## R1 · Search
A guest or receptionist can list the rooms that are free for given dates.
Check: empty hotel, 12–14 November → R7, R8.
Proof: `Free rooms 12-14 Nov: R7, R8`
Tests: `test_r1_search_empty_hotel_lists_every_room`, `test_r1_search_hides_room_with_shared_night`

## R2 · Book
A guest or receptionist can book a free room. The app answers with a reservation id.
Check: Maya books R7 for 12–14 November → Accepted R101.
Proof: `Maya books R7 12-14 Nov: Accepted R101`
Tests: `test_r2_book_free_room_returns_accepted_with_id`, `test_r2_accepted_booking_is_saved_confirmed_and_emailed`, `test_r2_ids_are_numbered_from_r101`

## R3 · No clash
A room never has two Confirmed bookings on the same night. Check-out must be after check-in.
Check: Omar asks for R7 on 13–15 → Unavailable. 15–15 → InvalidDates.

More examples (R7, Maya already has 12–14):
- Maya R7 12–14 → Confirmed (nights of the 12th and 13th)
- Omar R7 13–15 → Unavailable (night of the 13th is shared)
- Nora R7 14–16 → Accepted (no shared night: the 14th is Maya's check-out day)

Own examples (R8 already booked for 20–22 November, nights of the 20th and 21st):
- Maya R8 22–24 → Accepted (starts on the check-out day, no shared night)
- Omar R8 21–23 → Unavailable (night of the 21st is shared)

Proof: `Omar books R7 13-15 Nov: Unavailable`, `Nora books R7 14-16 Nov: Accepted R102`,
`Omar books R8 15-15 Nov: InvalidDates`
Tests: `test_r3_*`, `TestDateRange::test_overlap_counts_nights_not_dates`

Known limitation (**Observed**): the rule holds for one request at a time only. Two simultaneous
requests can both pass the check and both be saved — `python main.py --race` prints
`Confirmed reservations for R7 on 12-14 Nov: 2`. Pinned by `test_race_double_books_r7_known_defect`;
fixed in P09.

## R4 · Cancel
A booking can be cancelled. It is kept as Cancelled and no longer blocks the room.
Check: Maya cancels R101 → R7 is free again for 12–14.
Proof: `Maya cancels R101: True`, then `Free rooms 12-14 Nov: R7, R8`
Tests: `test_r4_cancel_frees_the_room_and_keeps_history`, `test_r4_cancel_twice_or_unknown_id_returns_false`

## R5 · View
A booking can be looked up by its id.
Check: R101 → Maya, R7, 12–14 November, Confirmed.
Proof: `tests/test_booking_service.py::test_r5_view_booking_by_id PASSED` (the nine-line demo has
no View line, so the proof is the test run; `ReservationStore.find("R101")` returns
Maya, R7, 2026-11-12..2026-11-14, Confirmed).
