# Observed runs — P05

Environment: Linux container, Python 3.13.18, pytest 9.1.1, Mermaid CLI 11.16.0 with headless
Chromium. Session date of the runs: 2026-11-21. The project tests were run on a snapshot copy of
`hotel-booking/` (taken after the P04 refactor had finished) so that P05 wrote nothing into the
project folder.

## O1 · Starting point: the P04 tests

Course command, in the snapshot of `hotel-booking/`:

```text
$ python -m unittest -v
test_a_failed_confirmation_keeps_the_booking ... ok
test_cancelling_frees_the_room_again ... ok
test_check_out_must_be_after_check_in ... ok
test_maya_gets_r7_when_it_is_free ... ok
test_nora_can_arrive_on_the_day_maya_leaves ... ok
test_omar_is_refused_when_a_night_is_shared ... ok
test_one_confirmation_per_accepted_booking ... ok
test_sms_confirmations_need_no_change_to_booking_service ... ok
----------------------------------------------------------------------
Ran 8 tests in 0.002s

OK
```

(Test ids shortened; the full lines read `test_x (test_booking_service.BookingServiceTests.test_x) ... ok`.)

Portfolio suite, same snapshot (with the P03/P04 `uml/` folders copied next to it, because
`test_uml_conformance.py` reads them):

```text
$ python -m pytest -q -p no:cacheprovider
82 passed in 1.60s
```

## O2 · The demo and the race (unchanged behaviour)

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

$ python main.py --race
Maya and Omar both book R7 for 12-14 Nov at the same moment...
Maya: Accepted R101
Omar: Accepted R102
Confirmed reservations for R7 on 12-14 Nov: 2
Double booking! Both requests checked before either one saved.
```

The race output is the reason S2 is marked "not met today" in `docs/quality-scenarios.md`.

## O3 · Document checks

```text
$ python -m pytest -p no:cacheprovider practices/P05-domain-context-boundaries/checks -v
... test_words_table_has_18_rows_each_with_a_meaning_and_a_code_name PASSED
... test_every_code_name_in_the_words_table_exists_in_the_code[DateRange] PASSED
... (12 code names: DateRange, Reservation, ReservationStatus.CONFIRMED, Guest, Room, Room.type,
     ReservationStatus.CANCELLED, BookingService.reserve, BookingService.cancel,
     Reservation.cancel, BookingService.find_free_rooms, NotificationSender.send_confirmation)
... test_each_context_section_has_job_words_rules_needs_and_tells[Rooms|Reservations|Payments|Notifications] PASSED
... test_all_18_words_are_placed_in_exactly_one_context PASSED
... test_same_word_table_has_room_status_and_cancel_and_the_danger_sentence PASSED
... test_rule_owners_eight_cards_one_owner_each_with_a_reason PASSED
... test_every_rule_is_listed_under_its_owner_and_nowhere_else PASSED
... test_context_map_has_4_boxes_and_3_labelled_arrows_from_reservations PASSED
... test_contexts_md_embeds_the_same_map_as_the_mermaid_source PASSED
... test_drawio_page_context_map_has_the_required_shape PASSED
... test_between_contexts_has_one_subsection_per_arrow_with_fields PASSED
... test_six_quality_scenarios_each_with_seven_lines_and_a_numeric_measure PASSED
============================== 26 passed in 0.38s ==============================
```

The code names were resolved against the P04 code in `hotel-booking/hotel_booking/` (parsed with
`ast`, not imported). One check failed on its first run — card 8 is written "(card 8, R6)" and the
check looked for "(card 8)"; the check was corrected to match "(card 8" followed by a word break.

## O4 · Diagram render check

```text
$ mmdc -p puppeteer.json -i diagrams/context-map.mmd -o diagrams/context-map.svg               -> OK
$ mmdc -p puppeteer.json -i diagrams/module-dependencies.mmd -o diagrams/module-dependencies.svg -> OK
$ mmdc -p puppeteer.json -i docs/contexts.md -o contexts-render.md                              -> ✅ contexts-render-1.svg
```

`puppeteer.json`: `{"executablePath": "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome",
"args": ["--no-sandbox"]}`. The PNG previews were inspected by eye: four boxes, Reservations
green, two solid arrows and one green dotted arrow, all labels readable.

## O5 · P05 changed nothing in hotel-booking/

SHA-256 of every file in `hotel-booking/` (caches excluded) taken once the P04 refactor had
finished and again after all P05 checks had run: identical, 23 files.
