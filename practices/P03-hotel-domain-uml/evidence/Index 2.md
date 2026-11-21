# Evidence index — P03

| ID | Label | Requirement | Action | Expected outcome | Actual outcome | Environment | Limitation |
|---|---|---|---|---|---|---|---|
| E1 | **Observed** | R1–R4 (demo) | `python main.py` | The nine lines of the activity sheet | Identical nine lines ([O1](observed-runs.md#o1--demo--python-mainpy)) | Linux container, Python 3.13.18, 2026-11-21 | One scripted scenario; does not cover R5 (see E3). |
| E2 | **Observed** | R1–R5, R3 invariant (sequential) | `python -m pytest -v` | All tests pass | 52 passed ([O3](observed-runs.md#o3--tests--python--m-pytest--v)) | same | Tests are written by the same author as the code; sequential invariant check covers R7 nights 10–16 only. |
| E3 | **Observed** | R5 view | `test_r5_view_booking_by_id` | R101 → Maya, R7, 12–14 Nov, Confirmed; unknown id → None | Passed | same | Viewed through `ReservationStore.find`; there is no screen or API yet (P07). |
| E4 | **Observed** | Code = class diagram | `tests/test_uml_conformance.py` | Same classes, attributes, operations, enum values; 11 links each visible in code | 12 passed | same | Parses this project's own Mermaid style; a link check proves a reference exists, not its multiplicity. |
| E5 | **Observed** | Message order = sequence diagrams | `tests/test_sequences.py` (spies) | Book: is_valid, has_overlap, count, save, send, reply. Unavailable: stops after has_overlap. Cancel: find, cancel, reply. Race: check, check, save, save | 5 passed | same | `next_id` (a private self-call) and the creation message are not spied, only their effects. |
| E6 | **Observed** | R3 under concurrency (known defect) | `python main.py --race`, 20 repetitions | Course expectation: double booking | 2 Confirmed for R7 12–14 Nov in 20 of 20 runs ([O2](observed-runs.md#o2--race--python-mainpy---race)) | same | The 0.5 s slow step is artificial; real gaps are smaller and timing-dependent. |
| E7 | **Observed** | Control for E6 | `test_without_overlap_in_time_the_second_request_is_refused` | When Omar starts after Maya saved: Unavailable, 1 Confirmed | Passed | same | Shows the check works when requests do not overlap in time — not a fix. |
| E8 | **Observed** | Diagrams render | `mmdc` on all 8 `uml/*.mmd` and on `Diagrams.md` | No parse errors; SVGs produced | 8 × OK ([O5](observed-runs.md#o5--diagram-render-check--mmdc--p-puppeteerjson--i-umlnamemmd--o-umlnamesvg)) | Mermaid CLI 11.16.0, headless Chromium | Rendering proves syntax, not that the drawing is good UML; the review in E10 does that. |
| E9 | **Simulated** | R3 race explanation | Timeline table (Diagrams.md §6) | Both checks before either save | Reasoned timeline; agrees with E6 | Paper model | A model of one interleaving, not all of them. |
| E10 | **Proposed** | Readability of "The race" section | Pair next door reads design-notes.md "The race" (Step 9.3) | They can retell what happened and between which two calls | Not done yet — **to do by the student** | Classroom | Recorded only after it happens. |
| E11 | **Proposed** | Same results on the student's Mac | `python3 main.py`, `python3 main.py --race`, `python3 -m pytest` | Same as E1, E2, E6 | Not run yet — **to do by the student** | macOS, Python ≥ 3.12 | — |

No performance target applies to P03; none is claimed.
