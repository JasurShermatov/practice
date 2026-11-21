# Observed runs

**Label:** Observed — every block below is real output, copied from the run.
**Environment:** Linux container (kernel 6.18), Python 3.13.18, pytest 9.1.1, mypy (strict),
Mermaid CLI 11.16.0 with headless Chromium. **Run date:** 2026-11-21 (portfolio build).
**Working directory:** `hotel-booking/` (diagrams: `practices/P03-hotel-domain-uml/uml/`).
The student's own machine (macOS) has not been used for these runs; re-running there is listed in
the README checklist.

## O1 · Demo — `python main.py`

```text
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

Matches the nine expected lines of the activity sheet exactly (also asserted by
`test_demo_prints_the_nine_expected_lines`).

## O2 · Race — `python main.py --race`

```text
Maya and Omar both book R7 for 12-14 Nov at the same moment...
Maya: Accepted R101
Omar: Accepted R102
Confirmed reservations for R7 on 12-14 Nov: 2
Double booking! Both requests checked before either one saved.
```

Repeated 20 times (`for i in $(seq 1 20); do python main.py --race | grep Confirmed; done | sort | uniq -c`):

```text
     20 Confirmed reservations for R7 on 12-14 Nov: 2
```

20 of 20 runs double-booked: with a 0.5 s slow step and a 0.1 s stagger, both checks always happen
before either save. This shows the defect is real, not that it happens 100 % of the time in
production — there the gap is much smaller and the result depends on timing.

## O3 · Tests — `python -m pytest -v`

```text
tests/test_booking_service.py::test_r1_search_empty_hotel_lists_every_room PASSED [  1%]
tests/test_booking_service.py::test_r1_search_hides_room_with_shared_night PASSED [  3%]
tests/test_booking_service.py::test_r2_book_free_room_returns_accepted_with_id PASSED [  5%]
tests/test_booking_service.py::test_r2_accepted_booking_is_saved_confirmed_and_emailed PASSED [  7%]
tests/test_booking_service.py::test_r2_ids_are_numbered_from_r101 PASSED [  9%]
tests/test_booking_service.py::test_r3_clash_is_unavailable_and_saves_nothing PASSED [ 11%]
tests/test_booking_service.py::test_r3_check_out_day_is_free_for_the_next_guest PASSED [ 13%]
tests/test_booking_service.py::test_r3_invalid_dates_save_nothing PASSED [ 15%]
tests/test_booking_service.py::test_r3_own_examples_for_r8_booked_20_to_22 PASSED [ 17%]
tests/test_booking_service.py::test_r3_invariant_at_most_one_confirmed_per_room_night PASSED [ 19%]
tests/test_booking_service.py::test_r4_cancel_frees_the_room_and_keeps_history PASSED [ 21%]
tests/test_booking_service.py::test_r4_cancel_twice_or_unknown_id_returns_false PASSED [ 23%]
tests/test_booking_service.py::test_r4_new_booking_after_cancel_gets_a_new_id PASSED [ 25%]
tests/test_booking_service.py::test_r5_view_booking_by_id PASSED         [ 26%]
tests/test_demo_and_race.py::test_demo_prints_the_nine_expected_lines PASSED [ 28%]
tests/test_demo_and_race.py::test_main_without_flags_runs_the_demo PASSED [ 30%]
tests/test_demo_and_race.py::test_race_double_books_r7_known_defect PASSED [ 32%]
tests/test_demo_and_race.py::test_without_overlap_in_time_the_second_request_is_refused PASSED [ 34%]
tests/test_domain.py::TestDateRange::test_check_out_after_check_in_is_valid PASSED [ 36%]
tests/test_domain.py::TestDateRange::test_zero_or_negative_nights_is_invalid[15-15] PASSED [ 38%]
tests/test_domain.py::TestDateRange::test_zero_or_negative_nights_is_invalid[16-14] PASSED [ 40%]
tests/test_domain.py::TestDateRange::test_overlap_counts_nights_not_dates[omar-13-15] PASSED [ 42%]
tests/test_domain.py::TestDateRange::test_overlap_counts_nights_not_dates[nora-14-16] PASSED [ 44%]
tests/test_domain.py::TestDateRange::test_overlap_counts_nights_not_dates[reverse-order] PASSED [ 46%]
tests/test_domain.py::TestDateRange::test_overlap_counts_nights_not_dates[ends-on-check-in] PASSED [ 48%]
tests/test_domain.py::TestDateRange::test_overlap_counts_nights_not_dates[night-of-12th] PASSED [ 50%]
tests/test_domain.py::TestDateRange::test_overlap_counts_nights_not_dates[inside] PASSED [ 51%]
tests/test_domain.py::TestDateRange::test_overlap_counts_nights_not_dates[around] PASSED [ 53%]
tests/test_domain.py::TestDateRange::test_overlap_counts_nights_not_dates[identical] PASSED [ 55%]
tests/test_domain.py::TestDateRange::test_is_a_value_equal_by_content_and_immutable PASSED [ 57%]
tests/test_domain.py::TestReservation::test_new_reservation_is_confirmed_and_keeps_its_facts PASSED [ 59%]
tests/test_domain.py::TestReservation::test_blocks_only_same_room_and_shared_night PASSED [ 61%]
tests/test_domain.py::TestReservation::test_cancel_once_then_again PASSED [ 63%]
tests/test_domain.py::TestReservation::test_cancelled_reservation_no_longer_blocks PASSED [ 65%]
tests/test_domain.py::TestReservation::test_status_can_only_change_through_cancel PASSED [ 67%]
tests/test_sequences.py::test_sequence_book_maya_r7 PASSED               [ 69%]
tests/test_sequences.py::test_sequence_unavailable_omar_r7 PASSED        [ 71%]
tests/test_sequences.py::test_sequence_invalid_dates_stops_before_the_store PASSED [ 73%]
tests/test_sequences.py::test_sequence_cancel_r101 PASSED                [ 75%]
tests/test_sequences.py::test_sequence_race_both_checks_before_either_save PASSED [ 76%]
tests/test_uml_conformance.py::test_diagram_has_exactly_the_public_classes_of_the_package PASSED [ 78%]
tests/test_uml_conformance.py::test_class_members_match_the_diagram[BookingResult] PASSED [ 80%]
tests/test_uml_conformance.py::test_class_members_match_the_diagram[BookingService] PASSED [ 82%]
tests/test_uml_conformance.py::test_class_members_match_the_diagram[DateRange] PASSED [ 84%]
tests/test_uml_conformance.py::test_class_members_match_the_diagram[EmailSender] PASSED [ 86%]
tests/test_uml_conformance.py::test_class_members_match_the_diagram[Guest] PASSED [ 88%]
tests/test_uml_conformance.py::test_class_members_match_the_diagram[Reservation] PASSED [ 90%]
tests/test_uml_conformance.py::test_class_members_match_the_diagram[ReservationStore] PASSED [ 92%]
tests/test_uml_conformance.py::test_class_members_match_the_diagram[Room] PASSED [ 94%]
tests/test_uml_conformance.py::test_enumeration_values_match_the_diagram[ReservationStatus] PASSED [ 96%]
tests/test_uml_conformance.py::test_enumeration_values_match_the_diagram[BookingOutcome] PASSED [ 98%]
tests/test_uml_conformance.py::test_every_relationship_is_visible_in_the_source PASSED [100%]
============================== 52 passed in 1.13s ==============================
```

## O4 · Type check — `python -m mypy` (strict, `hotel_booking/` and `main.py`)

```text
Success: no issues found in 7 source files
```

## O5 · Diagram render check — `mmdc -p puppeteer.json -i uml/<name>.mmd -o uml/<name>.svg`

`puppeteer.json`: `{"executablePath": "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome", "args": ["--no-sandbox"]}`

```text
OK   activity-book.mmd -> activity-book.svg
OK   class-diagram.mmd -> class-diagram.svg
OK   sequence-book.mmd -> sequence-book.svg
OK   sequence-cancel.mmd -> sequence-cancel.svg
OK   sequence-race.mmd -> sequence-race.svg
OK   sequence-unavailable.mmd -> sequence-unavailable.svg
OK   state-reservation.mmd -> state-reservation.svg
OK   use-case-diagram.mmd -> use-case-diagram.svg
```

The Markdown file `Diagrams.md` was also rendered as a whole (`mmdc -i Diagrams.md -o …`):
all 8 embedded Mermaid blocks produced SVGs without a parse error.
