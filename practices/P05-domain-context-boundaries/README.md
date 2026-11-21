# P05 — Hotel domain and context boundaries

**Session:** Tuesday 27 October 2026, 18:00–19:20 (Asia/Tashkent) · Practice · Group 23-309 SW · Room 222
**Related lecture:** L03 — DDD, architectural styles and the modular monolith
**Type of work:** design and documentation only. P05 changes **no code**; the hotel-booking
app stays exactly as P04 left it, and P06 turns this design into modules.

## Goal

Decide which business area of the hotel owns what, before touching the code: write down who cares
about the app and what "good" means (six measurable quality scenarios), the hotel's words
(ubiquitous language), the four bounded contexts with their jobs, the words that change meaning
between contexts, one owner for every rule, the context map, and exactly what crosses each border
— so that P06's move into modules becomes a copying job.

## Outputs (requirement → file)

| Step (activity sheet) | Output | File |
|---|---|---|
| Start · check your starting point | P04 tests run; the two new files created; L03 exit-check answers | [Worksheet.md § Start](Worksheet.md#start--check-your-starting-point), [docs/l03-notes.md](docs/l03-notes.md) |
| 1 · Stakeholders and S1–S6 | Stakeholders table; six scenarios, seven lines each, every Measure with a number | [docs/quality-scenarios.md](docs/quality-scenarios.md) |
| 2 · The hotel's words | Words table: 18 words, meaning, name in our code | [docs/contexts.md § Words](docs/contexts.md#words) |
| 3 · Four contexts | Rooms, Reservations, Payments, Notifications: Job + Words table each | [docs/contexts.md § Rooms … Notifications](docs/contexts.md#rooms) |
| 4 · Same word, two meanings | Room, Status, Cancel (+ Guest) and the sentence on one shared status | [docs/contexts.md § Same word, different meaning](docs/contexts.md#same-word-different-meaning) |
| 5 · Who owns each rule | 8 rule cards, one owner and a reason each; "Rules this context owns" in every section | [docs/contexts.md § Rule owners](docs/contexts.md#rule-owners) |
| 6 · Context map | 4 boxes (Reservations green), 3 labelled arrows from Reservations (2 solid, 1 dotted) | [diagrams/context-map.mmd](diagrams/context-map.mmd) → [.svg](diagrams/context-map.svg); draw.io page "Context map": [diagrams/context-map.drawio](diagrams/context-map.drawio); embedded in [contexts.md § Context map](docs/contexts.md#context-map) |
| 7 · What crosses each border | 3 borders with Sent when / sends / answer / fields / Never crosses; "Needs" and "Tells" lines per context | [docs/contexts.md § Between contexts](docs/contexts.md#between-contexts) |
| 8 · Check and hand over | Checklist, test re-run, hand-over | [Worksheet.md § Step 8](Worksheet.md#step-8--check-and-hand-over), [checks/test_p05_docs.py](checks/test_p05_docs.py) |
| Design decisions found while modelling | D1 deposit amount, D2 Room vs room number, open ReservationCancelled | [docs/contexts.md § Decisions](docs/contexts.md#decisions-and-open-questions) |
| Implications for the code (input for P06) | Context → package, class moves, rule → code, border → contract, import rules, change-impact check, target module diagram | [Implications-for-the-code.md](Implications-for-the-code.md), [diagrams/module-dependencies.mmd](diagrams/module-dependencies.mmd) → [.svg](diagrams/module-dependencies.svg) |
| Evidence | Index with Proposed / Simulated / Observed labels; real outputs | [evidence/Index.md](evidence/Index.md), [evidence/observed-runs.md](evidence/observed-runs.md) |
| Reflection | Individual reflection | [reflections/Jasur-Shermatov.md](reflections/Jasur-Shermatov.md) |

### Where these files belong in the project

The activity sheet puts `quality-scenarios.md`, `contexts.md` (and `l03-notes.md`) into
`hotel-booking/docs/`. While P05 was written, `hotel-booking/` was being refactored for P04, so
this practice does not write into it; the three files live in [docs/](docs/) here, written so
they can be copied unchanged:

```bash
cp practices/P05-domain-context-boundaries/docs/{quality-scenarios,contexts,l03-notes}.md hotel-booking/docs/
```

(The relative links inside `contexts.md` to `../diagrams/` point at this practice's diagrams; after
copying, P06 should keep the diagrams next to them or adjust the links.) **Done in P06:** the files
were copied at the start of P06 and their diagram links adjusted.

## How to check

```bash
# from the portfolio root
python3 -m pytest -p no:cacheprovider practices/P05-domain-context-boundaries/checks -v   # 26 document checks
cd hotel-booking && python3 -m pytest                                                     # P04 code, unchanged by P05

# re-render the diagrams (inside a container add a puppeteer config with "--no-sandbox")
mmdc -i practices/P05-domain-context-boundaries/diagrams/context-map.mmd -o practices/P05-domain-context-boundaries/diagrams/context-map.svg
```

`checks/test_p05_docs.py` parses the documents and the code (with `ast`, read-only) and fails if a
count is wrong (18 words, 4/8/3/3 placement, 8 owners, 3 borders, 6 × 7 scenario lines, a number
in every Measure), if the map loses its shape (in Mermaid or draw.io), if the map embedded in
`contexts.md` differs from its source, or if a code name in the Words table does not exist in
`hotel-booking/hotel_booking/`.

## Substitutions (honest record)

| Course material uses | This portfolio uses | Why | Requirement still covered by |
|---|---|---|---|
| draw.io page "Context map" inside `docs/diagrams.drawio` | Mermaid source + SVG (render-checked with `mmdc`), **and** a hand-written draw.io file with one page "Context map" | Same convention as P03 (text diagrams, rendered automatically). The `.drawio` file is provided as well because the step names draw.io; it opens in app.diagrams.net. It could not be opened in draw.io here — its shape (4 boxes, 1 green, 3 edges from Reservations, 1 dotted green) is checked by parsing its XML. | `test_context_map_*`, `test_drawio_page_context_map_has_the_required_shape` |
| Mermaid layout = course layout (Rooms top-left, Payments top-right, Reservations bottom-left, Notifications bottom-right) | Mermaid auto-layout puts Reservations on the left and the three others on the right | Mermaid has no fixed positions; the draw.io page follows the course layout exactly | Same boxes, colours, arrows and labels |
| Files in `hotel-booking/docs/` | Files in `practices/P05-…/docs/` | `hotel-booking/` was being changed by P04 at the time; P05 must not change it | Copy command above (to do at the start of P06) |
| `python -m unittest -v` (8 P04 tests) | `python -m pytest` in `hotel-booking/` (the portfolio's P04 suite) | The portfolio has used pytest since P03 | [Worksheet § Start](Worksheet.md#start--check-your-starting-point), evidence E1 |
| "No coding" | No application code changed; a small test file checks the *documents* | Portfolio rule: every check is automated where possible, and the Words table must name classes that really exist | `checks/test_p05_docs.py` |

## Requirements checklist

Every requirement found in the P05 materials (Student explanation = Activity sheet = Student
notes = Presentation notes; the activity sheet adds nothing beyond the explanation — compared
line by line) and the L03 parts P05 depends on (L03 activity sheet §2, §5 and the exit check).

| # | Requirement (source) | Where it is satisfied | Status |
|---|---|---|---|
| 1 | Start: open the folder, run the P04 tests (8 passing in the course version) (Start 1–2) | [Worksheet § Start](Worksheet.md#start--check-your-starting-point); E1 | Done — Observed (8 `unittest` tests OK; 82 `pytest` passed) |
| 2 | Start: docs folder has requirements.md, design-notes.md, diagrams; l03-notes.md if at L03 (Start 3) | requirements.md, design-notes.md present; diagrams are Mermaid (P03 substitution); [docs/l03-notes.md](docs/l03-notes.md) | Done |
| 3 | Start: create `quality-scenarios.md` and `contexts.md` (Start 4) | [docs/](docs/) | Done (location: see "Where these files belong") |
| 4 | Step 1: Stakeholders table (5 stakeholders) | [quality-scenarios.md § Stakeholders](docs/quality-scenarios.md#stakeholders) | Done |
| 5 | Step 1: S3 copied, then S1, S2, S4, S5, S6, each a seven-line table (Source, Stimulus, Environment, Artifact, Response, Measure, Checked in) | [quality-scenarios.md](docs/quality-scenarios.md); `test_six_quality_scenarios_…` | Done — Observed (check) |
| 6 | Step 1: every Measure contains a number; tables render as tables | same test; Markdown parsed by the check | Done — Observed |
| 7 | Step 2: `# Hotel contexts` + Words table with the three example rows, code names in our language | [contexts.md § Words](docs/contexts.md#words) | Done |
| 8 | Step 2: rows for Guest, Room, Room type, Nightly price, Out of service, Cancelled, Book, Cancel, Free rooms, Deposit, Paid, Declined, Confirmation message, Sent, Failed; one-sentence meaning with an example | same | Done |
| 9 | Step 2: "Name in our code" from the code, "not in code yet" otherwise; 18 rows; every code name exists | same; `test_every_code_name_in_the_words_table_exists_in_the_code` (12 names) | Done — Observed |
| 10 | Step 3: four headings, each with "Job: …" | [contexts.md § Rooms…](docs/contexts.md#rooms) | Done |
| 11 | Step 3: Reservations Words table (Stay, Reservation, Confirmed, Cancelled + Guest, Book, Cancel, Free rooms); other words in their contexts; all 18 placed once (4/8/3/3) | same; `test_all_18_words_are_placed_in_exactly_one_context` | Done — Observed |
| 12 | Step 4: "Same word, different meaning" with Status, Room, Cancel in own words | [contexts.md § Same word](docs/contexts.md#same-word-different-meaning) | Done (+ Guest row) |
| 13 | Step 4: one sentence on Notifications setting Failed — names the guest who loses the room and R6 | same | Done |
| 14 | Step 5: Rule owners table, cards 1 and 6 copied, cards 2–5, 7, 8 added with owner and reason | [contexts.md § Rule owners](docs/contexts.md#rule-owners) | Done |
| 15 | Step 5: "Rules this context owns:" bullets in every context section; each card one owner; every context ≥ 1 rule; compared with the course answers | same; `test_every_rule_is_listed_under_its_owner_and_nowhere_else` | Done — Observed (owners match; card 6 reason differs, D1) |
| 16 | Step 6: context map page — 4 boxes in the course layout with name + three lines, Reservations green, 2 solid "Asks:" arrows, 1 green dotted "Announces: ReservationConfirmed", all from Reservations | [diagrams/](diagrams/) (Mermaid + draw.io); `test_context_map_…`, `test_drawio_…` | Done — Observed (render + structure) |
| 17 | Step 7: "Between contexts" — ReservationConfirmed copied; Rooms question and Payments question (P17) each with Sent when / sends / answer + fields / Never crosses | [contexts.md § Between contexts](docs/contexts.md#between-contexts); `test_between_contexts_…` | Done — Observed |
| 18 | Step 7: "Needs from other contexts" and "Tells other contexts" in every section ("nothing" where nothing) | context sections; `test_each_context_section_…` | Done — Observed |
| 19 | Step 8: go through the checklist; fix anything missing | [Worksheet § Step 8](Worksheet.md#step-8--check-and-hand-over) | Done |
| 20 | Step 8: run the tests again — code unchanged, same tests pass | Worksheet § Step 8; E1/E2 | Done — Observed (P05 changed no file in `hotel-booking/`) |
| 21 | Step 8: copy the folder to the partner's laptop; keep it for P06 | — | **To do by the student** |
| 22 | Pair work on one laptop, swapping typist at every step; attendance | — | **To do by the student** (classroom) |
| 23 | Files placed in `hotel-booking/docs/` (folder layout at the end of P05) | Copy command in this README | Done at the start of P06 (links adjusted; see [P06 Worksheet](../P06-modular-monolith-review/Worksheet.md#your-turn--open-your-project)) |
| 24 | L03 exit check: three answers in `docs/l03-notes.md` (P05 starts from answer 1) | [docs/l03-notes.md](docs/l03-notes.md) | Done |
| 25 | Each context will become a module, each rule owner a place in code, each border a contract (P05 → P06 link; own standard: "Implications for the code") | [Implications-for-the-code.md](Implications-for-the-code.md) | Done — Proposed (implemented in P06) |
| 26 | Evidence labelled Proposed / Simulated / Observed; reflection | [evidence/Index.md](evidence/Index.md), [reflections/](reflections/Jasur-Shermatov.md) | Done |

The L03 "Student explanation" mostly contains previous-syllabus material (threads and locks)
that the course marks as *not the current lesson instructions*; it is not part of P05.

## Self-check before submission

- [x] Every word has one meaning inside its context, and every code name exists in the code (checked by a test)
- [x] Every rule card has exactly one owner, and the reason names the data the owner keeps
- [x] Every arrow on the map has a subsection with its fields and a "Never crosses" line
- [x] All arrows start at Reservations; no context calls Reservations
- [x] No file under `hotel-booking/` was changed by P05
- [x] Evidence is labelled; the change-impact check is marked Simulated, the P06 plan Proposed
