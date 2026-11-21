# P06 — Modular-monolith architecture review

**Session:** Saturday 31 October 2026, 09:30–10:50 (Asia/Tashkent) · Practice · Group 23-309 SW · Room 232
**Related lecture:** L03 — DDD, architectural styles and the modular monolith
**Type of work:** refactoring of the growing [hotel-booking](../../hotel-booking/README.md) codebase
(version 2 → version 3) into a modular monolith, with architecture tests, an ADR and a review.

## Goal

Make the P05 design real in the code: each of the four contexts (Rooms, Reservations, Payments,
Notifications) becomes a module with a public contract and internal code, `main.py` is the only
app file that names internal classes, and a test fails the moment one module reaches into
another's internal code — **without changing what the app does**. Then record the decision
(ADR-001), draw the page "Modules", and review the result against the design.

## Outputs (requirement → file)

| Step (activity sheet) | Output | File |
|---|---|---|
| Start · open your project | P05 docs copied into the project (links fixed); `# P06 design notes` heading | [hotel-booking/docs/](../../hotel-booking/docs/) (`quality-scenarios.md`, `contexts.md`, `l03-notes.md`); [Worksheet § Start](Worksheet.md#your-turn--open-your-project) |
| 1 · Lock the behaviour | Tests, demo, race before any move; `## Before` | [design-notes.md § Before](../../hotel-booking/docs/design-notes.md#before); [Worksheet § Step 1](Worksheet.md#step-1--lock-the-behaviour--run-the-safety-net); O1 |
| 2 · Module folders | Four packages; `## Modules` table | `hotel_booking/{rooms,reservations,payments,notifications}/`; [design-notes.md § Modules](../../hotel-booking/docs/design-notes.md#modules); O2 |
| 3 · Move Rooms, then Notifications | `rooms/` (Room, RoomCatalog, InMemoryRoomCatalog); `notifications/` (Confirmation, NotificationSender, Email/Sms senders); BookingService sends a `Confirmation`; fake sender adapted | [rooms/](../../hotel-booking/hotel_booking/rooms/), [notifications/](../../hotel-booking/hotel_booking/notifications/), [reservations/booking.py](../../hotel-booking/hotel_booking/reservations/booking.py), [test_booking_service.py](../../hotel-booking/test_booking_service.py); O3 |
| 4 · Move Reservations, add Payments | `reservations/` (domain, booking, internal); `payments/` (PaymentStatus, PaymentService, SimulatedPaymentService); "where every P04 class is now" | [reservations/](../../hotel-booking/hotel_booking/reservations/), [payments/](../../hotel-booking/hotel_booking/payments/); [Worksheet § Step 4](Worksheet.md#where-every-p04-class-is-now); O3 |
| 5 · Wiring | `main.py` creates catalog, store, sender; passes `catalog.all()`; only app file naming internals | [main.py](../../hotel-booking/main.py); O4 |
| 6 · Architecture tests | 3 forbidden contracts; stdlib `ast` enforcement + lint-imports-style CLI; `## Architecture rules` | [.importlinter](../../hotel-booking/.importlinter), [tests/test_architecture.py](../../hotel-booking/tests/test_architecture.py); [design-notes.md § Architecture rules](../../hotel-booking/docs/design-notes.md#architecture-rules); O5 |
| 7 · Break it on purpose | Red result naming the bad dependency, undo, green; `## Broken on purpose`; all three rules on a copy | [Worksheet § Step 7](Worksheet.md#step-7--break-it-read-it-undo-it); [evidence/break_the_border.py](evidence/break_the_border.py); O6, O7 |
| 8 · Prove, decide, draw | `## After`; ADR-001; draw.io page "Modules" | [design-notes.md § After](../../hotel-booking/docs/design-notes.md#after); [adr-001-modular-monolith.md](../../hotel-booking/docs/adr-001-modular-monolith.md); [diagrams.drawio](../../hotel-booking/docs/diagrams.drawio) (pages "Context map", "Modules"); O8 |
| Architecture review (the practice's title; L03 §3–4 questions) | R1–R10 answers, findings F1–F8, differences from the P05 plan | [Architecture-review.md](Architecture-review.md) |
| Diagrams (Mermaid, render-checked) | Modules page, as-built module dependencies (checked against the real imports), class diagram by module (UML-conformance target) | [diagrams/](diagrams/): [modules](diagrams/modules.mmd) → [svg](diagrams/modules.svg), [module-dependencies](diagrams/module-dependencies.mmd) → [svg](diagrams/module-dependencies.svg), [class-diagram](diagrams/class-diagram.mmd) → [svg](diagrams/class-diagram.svg) |
| Tests for the new contracts | Rooms catalog, Payments deposit, Confirmation translation | [tests/test_modules.py](../../hotel-booking/tests/test_modules.py) |
| Document checks | draw.io page shape, design-notes sections, ADR sections, folder layout, links | [checks/test_p06_docs.py](checks/test_p06_docs.py) |
| Evidence | Index with labels; real outputs after every move | [evidence/Index.md](evidence/Index.md), [evidence/observed-runs.md](evidence/observed-runs.md), [evidence/logs/](evidence/logs/) |
| Before/after scenario | Version 2 vs version 3: identical answers and records | [evidence/compare_behaviour.py](evidence/compare_behaviour.py) |
| Reflection | Individual reflection | [reflections/Jasur-Shermatov.md](reflections/Jasur-Shermatov.md) |
| Answers to every "Your turn" | Step by step, with logs | [Worksheet.md](Worksheet.md) |

## How to check

```bash
cd hotel-booking
python3 -m unittest -v                 # the course's 8 tests: OK
python3 -m tests.test_architecture     # Contracts: 3 kept, 0 broken.  (stdlib; same rules as lint-imports)
lint-imports                           # on a machine with import-linter (pip install -r requirements.txt)
python3 main.py                        # the same nine lines as P04
python3 main.py --race                 # still double-books (known defect until P09)
python3 -m pytest                      # 118 passed (8 unittest + 110 pytest)
python3 -m mypy                        # strict: no issues in 19 source files
cd ..
python3 -m pytest -p no:cacheprovider practices/P06-modular-monolith-review/checks    # P06 document checks
python3 -m pytest -p no:cacheprovider practices/P05-domain-context-boundaries/checks  # P05 still consistent
python3 -I practices/P06-modular-monolith-review/evidence/break_the_border.py hotel-booking   # break each rule on a copy
```

Re-render a diagram (inside a container the puppeteer config with `--no-sandbox` is needed):
`mmdc -p diagrams/puppeteer-config.json -i diagrams/modules.mmd -o diagrams/modules.svg` (on a Mac,
plain `mmdc -i … -o …`; the config's `executablePath` is the container's Chromium).

## What changed in the code (version 2 → 3)

| File | Change | Kind |
|---|---|---|
| `hotel_booking/__init__.py` | Docstring only; re-exports nothing (it handed out internal classes) | refactoring |
| `hotel_booking/rooms/` (new) | `catalog.py`: `Room` (moved unchanged), `RoomCatalog` protocol; `internal.py`: `InMemoryRoomCatalog`; `__init__.py` contract | refactoring + new contract |
| `hotel_booking/notifications/` (new; `notifications.py` deleted) | `__init__.py`: `Confirmation` (5 frozen fields), `NotificationSender(confirmation)`; `internal.py`: Email/Sms senders | refactoring + new message type |
| `hotel_booking/reservations/` (new; `domain.py`, `booking.py`, `stores.py` deleted) | `domain.py` (moved), `booking.py` (`ReservationStore` + `BookingService`, which now builds the `Confirmation`), `internal.py` (`InMemoryReservationStore`) | refactoring |
| `hotel_booking/payments/` (new) | `PaymentStatus`, `PaymentService(take_deposit(reservation_id, amount: Decimal))`, `SimulatedPaymentService` | new module (not called before P17) |
| `hotel_booking/demo.py` | Imports contracts only; `run_demo(service, emails_sent)` takes a function instead of the internal sender | refactoring |
| `main.py` | Creates `InMemoryRoomCatalog` and passes `catalog.all()`; imports internals from the modules | wiring |
| `.importlinter` (new) | The three border contracts | architecture check |
| `test_booking_service.py` | Same 8 test methods; imports, the fake sender (`Confirmation`) and the R6 logger name adapted (noted in its docstring) | tests (deliberate) |
| `tests/conftest.py`, `test_booking_service.py`, `test_domain.py` | Imports only | tests (deliberate) |
| `tests/test_sequences.py` | Imports; spies log `confirmation.reservation_id`; expected logs unchanged | tests (deliberate) |
| `tests/test_demo_and_race.py` | `run_demo(service, lambda: email.sent)`; expected outputs unchanged | tests (deliberate) |
| `tests/test_substitution.py` | P04's `CancellingSender` can no longer be written → `MeddlingSender` shows it is contained; `ForgetfulStore` is the new "bad substitute is caught" example | tests (deliberate) |
| `tests/test_dependency_rule.py` | Paths into the modules; covers all concrete classes; domain may import only the Rooms contract | tests (deliberate) |
| `tests/test_uml_conformance.py` | `CLASS_DIAGRAM` → [P06 class diagram](diagrams/class-diagram.mmd); parses Mermaid namespaces; new checks: module of every box, `<<internal>>` = classes of `internal.py`, the diagram respects the borders | tests (deliberate) |
| `tests/test_architecture.py`, `tests/test_modules.py` (new) | Border contracts (+ extras, self-tests, CLI); new contracts' behaviour | tests |
| `docs/` | P05 docs copied; `design-notes.md` P06 sections; ADR-001; `diagrams.drawio` | docs |
| `pyproject.toml`, `requirements.txt`, `README.md` | version 0.6.0; mypy on new tests; import-linter as dev tool; README v3 | config/docs |

## Substitutions (honest record)

| Course material uses | This portfolio uses | Why | Requirement still covered by |
|---|---|---|---|
| `pip install import-linter` + `lint-imports` | `.importlinter` (for `lint-imports` on the Mac) **and** `tests/test_architecture.py`: stdlib `configparser` reads that same file, `ast` builds the import graph (direct, relative and indirect imports), each contract is a parametrized test; `python -m tests.test_architecture` prints KEPT/BROKEN and "Contracts: N kept, M broken." like lint-imports | import-linter is not installed and PyPI is unreachable here (E13). One rules file, so the two checkers cannot drift. The checker is itself tested on small fake packages (each rule, relative and indirect imports). | `test_contract_is_kept[*]`, `test_checker_catches_*`; O5–O7. `lint-imports` itself: **to run on the student's Mac** |
| Contracts in `pyproject.toml` `[tool.importlinter]` | `.importlinter` (INI) | Task brief asks for a `.importlinter` file; lint-imports reads it by default; keeping both would duplicate the rules | `pyproject.toml` comment points to it |
| `python -m unittest` = 8 tests, then "Contracts: 3 kept" | Same 8 `unittest` tests; the 3 contracts run in pytest and via the CLI; the full suite is 118 | Portfolio rule: every behaviour gets an automated check | O8 |
| draw.io page "Modules" in `docs/diagrams.drawio` | The page itself (hand-written XML, second page after "Context map") **plus** a Mermaid twin rendered with `mmdc` | Same convention as P03–P05; the `.drawio` could not be opened in the draw.io app here, so its shape is checked by parsing its XML | `test_modules_page_has_the_required_shape`, `test_mermaid_modules_page_matches_the_drawio_page` |
| `main.py` holds the scenario and the wiring | `main.py` = wiring (`build_app`); the scenario stays in `hotel_booking/demo.py` (since P04), now using contracts only | Tests import the scenario; the extra architecture rule checks `demo.py` like a module | `test_no_module_imports_another_modules_internal_code` |
| `BookingResult("Accepted", …)`, public mutable `Reservation` fields | `BookingOutcome` enum; read-only `Reservation` (kept from P03/P04) | Encapsulation (L02); not touched by P06 | `tests/test_domain.py` |
| L03's Python preview of the contract: `amount: float` | `amount: Decimal`, as the P06 activity sheet's Python tab and reference code have it | Exact money arithmetic (P05 recommendation); P06 itself already corrected the L03 preview | `test_deposit_arithmetic_is_exact_with_decimal` |
| `ADR-001 Status: Accepted, 25 October 2026` | "Accepted — decided in L03, implemented and checked in P06" | No past date is claimed for this write-up | `test_adr_001_has_status_and_the_five_sections` |

## Requirements checklist

Sources: Activity sheet (= Student explanation = Student notes = Presentation notes; compared with
`diff`, identical apart from the title block), catalog entry, L03 activity sheet §3, §4 and §6 (the
P06 preview, "How to check an ADR"), the P05 plan (Implications-for-the-code.md) and the task brief.

| # | Requirement (source) | Where it is satisfied | Status |
|---|---|---|---|
| 1 | Open the project with `docs/contexts.md` beside the code; add `# P06 design notes` (Start) | P05 docs copied into `hotel-booking/docs/`; heading in design-notes.md | Done |
| 2 | Copy P05's three docs into `hotel-booking/docs/`, fixing relative links (P05 README; brief) | [hotel-booking/docs/](../../hotel-booking/docs/); `test_copied_p05_docs_keep_their_content`, `test_every_relative_link_resolves` | Done — Observed |
| 3 | Step 1: run the 8 tests, demo, race; `## Before` with three lines | design-notes § Before; O1 | Done — Observed |
| 4 | Step 2: four module folders, `__init__.py` each; `## Modules` table; tests still 8 | packages; design-notes § Modules; O2 | Done — Observed (name clash found and handled) |
| 5 | Step 3.0: replace `hotel_booking/__init__.py` with the docstring-only version; imports from the module packages | `hotel_booking/__init__.py`; `test_package_root_exports_nothing` | Done |
| 6 | Step 3.1: Rooms — `Room`, room catalog promise, `InMemoryRoomCatalog`; tests 8 | `rooms/`; O3 | Done — Observed |
| 7 | Step 3.2: Notifications contract (`Confirmation` with the five P05 fields, sender promise) + internal senders; old file deleted | `notifications/`; `test_confirmation_is_exactly_the_p05_fields_and_frozen` | Done — Observed |
| 8 | Step 3.3: BookingService sends a `Confirmation` | `reservations/booking.py` `_try_to_confirm`; `test_reservations_sends_the_five_border_fields` | Done — Observed |
| 9 | Step 3.5: fake sender receives a `Confirmation` and records its id; tests 8 | `test_booking_service.py`; O3 | Done — Observed |
| 10 | Step 4.1: Reservations (domain types, BookingService, store promise, internal store); old files deleted; tests 8 | `reservations/`; O3 | Done — Observed |
| 11 | Step 4.2: Payments contract (`PaymentStatus`, payment promise) + `SimulatedPaymentService` (positive → Paid, else Declined) | `payments/`; `test_simulated_payment_*` | Done — Observed |
| 12 | Step 4.5: no class left in its old place | `test_every_class_lives_in_one_of_the_four_modules`, `test_project_folder_matches_the_finished_p06_folder` | Done — Observed |
| 13 | Step 5: main creates the catalog with R7, R8 and passes `catalog.all()`; only app file naming internal classes; tests may too | `main.py`; `test_only_main_creates_concrete_classes_of_the_modules`, `test_no_module_imports_another_modules_internal_code`; O4 | Done — Observed |
| 14 | Step 5.3: search the module folders for `internal` | [s5-internal-search](evidence/logs/s5-internal-search.txt) | Done — Observed |
| 15 | Step 5.4 / 8: the same nine demo lines | `diff` empty; `test_demo_prints_the_nine_expected_lines` | Done — Observed |
| 16 | Step 6: the three rules as checks; `## Architecture rules` in plain words | `.importlinter`, `tests/test_architecture.py`; design-notes § Architecture rules; O5 | Done — Observed (stdlib substitute) |
| 17 | Step 6: install import-linter and see "Contracts: 3 kept, 0 broken." from `lint-imports` | E13 (not installable here); E15 | **To do by the student** (Mac) — the stdlib checker prints the same three KEPT lines |
| 18 | Step 7: add the forbidden line, predict, run, read the message (names BookingService's file and the sender), undo, green; `## Broken on purpose` | O6; design-notes § Broken on purpose | Done — Observed |
| 19 | Brief: boundary test fails on a deliberate bad import, passes after removal | O6 (real file, same SHA-256 after undo), O7 (all three rules on a copy) | Done — Observed |
| 20 | Step 8.1: run everything at the end: 8 tests + 3 contracts, nine lines, race still double-books | O8 | Done — Observed |
| 21 | Step 8.2: `## After`, compared with Before (must match) | design-notes § After | Done |
| 22 | Step 8.3: `docs/adr-001-modular-monolith.md` (own words) | [ADR-001](../../hotel-booking/docs/adr-001-modular-monolith.md); `test_adr_001_has_status_and_the_five_sections` | Done |
| 23 | Step 8.4: draw.io page "Modules": 5 boxes (Reservations green, internal sender purple dashed), 3 Uses, 1 Implements, red Forbidden | [diagrams.drawio](../../hotel-booking/docs/diagrams.drawio); Mermaid twin; `test_modules_page_has_the_required_shape` | Done — Observed (XML; app not opened) |
| 24 | P06 checklist (code, checks, demo/race, design-notes sections, ADR, Modules page) | [Worksheet § checklist](Worksheet.md#your-p06-checklist); checks | Done |
| 25 | Keep the P09 race defect pinned | `test_race_double_books_r7_known_defect`, `test_main_race_flag_still_double_books`; 20/20 | Done — Observed |
| 26 | Keep all existing tests green; update deliberately with notes where module paths change (brief) | Notes in every touched test module docstring; table above | Done — Observed (118 passed) |
| 27 | UML-conformance `CLASS_DIAGRAM` points at P06's class/module diagram (brief) | `tests/test_uml_conformance.py` → [diagrams/class-diagram.mmd](diagrams/class-diagram.mmd) | Done — Observed (29 checks) |
| 28 | `.importlinter` contract file AND stdlib `ast` pytest failing on forbidden imports (brief) | both; O5–O7 | Done — Observed |
| 29 | Mermaid diagrams render-checked with `mmdc` (brief) | [logs/mmdc.txt](evidence/logs/mmdc.txt) | Done — Observed |
| 30 | Architecture review answers (practice title; L03 "Contract or reach-in?", "Who stops the forbidden arrow?", "How to check an ADR") | [Architecture-review.md](Architecture-review.md) R3, R7, R8 | Done |
| 31 | Behaviour unchanged (refactoring): only imports and the fake sender adapt in the 8 tests | Diff of the test class body: only the logger name line (O8, Worksheet); [cmp-v2-v3](evidence/logs/cmp-v2-v3.txt) | Done — Observed |
| 32 | Follow the P05 plan; note differences | [Architecture-review § Differences](Architecture-review.md#differences-from-the-p05-plan) | Done |
| 33 | Evidence labelled; reflection | [evidence/Index.md](evidence/Index.md); [reflection](reflections/Jasur-Shermatov.md) | Done |
| 34 | P06 row in the portfolio README | [../../README.md](../../README.md) | Done |
| 35 | Pair work on one laptop, swapping typist at every step; attendance | — | **To do by the student** (classroom) |
| 36 | Same results on the student's Mac (incl. `lint-imports`, opening the draw.io page) | E15, E16 | **To do by the student** |

The activity sheet's "Where the hotel app goes next" (L04, P07, P08) is a preview, not a P06
task; ADR-001's "Revisit when" and the review's findings point at those practices.

## Self-check before submission

- [x] Every class is in one of the four modules; `main.py` is the only app file that names internal code
- [x] 8 behaviour tests unchanged in their bodies; 3 contracts kept; demo identical; race still there
- [x] Each architecture check was seen failing (all three rules) and passing again
- [x] The class diagram, the Modules page and the as-built diagram are checked against the code
- [x] Evidence is labelled; nothing claims a `lint-imports` run that did not happen
