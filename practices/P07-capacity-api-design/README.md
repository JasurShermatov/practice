# P07 — Capacity and API design studio

**Session:** Tuesday 3 November 2026, 18:00–19:20 (Asia/Tashkent) · Practice · Group 23-309 SW · Room 222
**Related lecture:** L04 — System design: capacity, APIs, caching and scaling
**Type of work:** evolution of the growing [hotel-booking](../../hotel-booking/README.md) codebase
(version 3 → version 4): capacity estimate, API contract, HTTP API, database store, proof.

## Goal

Give the P06 app an address and a memory without touching its booking rule: estimate the load
first, write the API contract before the code, put the app behind HTTP on
http://localhost:5080, keep the reservations in a database through the same `ReservationStore`
promise, and prove it — every answer of the contract produced by the real server, and a booking
that survives a restart.

## Outputs (requirement → file)

| Step (activity sheet) | Output | File |
|---|---|---|
| Start · open your project | P06 checks green first; `# P07 design notes`; L04 exit-check answers | [design-notes.md](../../hotel-booking/docs/design-notes.md#p07-design-notes), [l04-notes.md](../../hotel-booking/docs/l04-notes.md); [Worksheet § Start](Worksheet.md#your-turn--open-your-project) |
| 1 · Capacity estimate | Assumptions (explicit, with reasons), workload model, results with the calculation, checked by hand, design consequences, what P08 measures; the estimate as a program; doc ↔ program test | [docs/capacity.md](../../hotel-booking/docs/capacity.md), [capacity.py](../../hotel-booking/capacity.py), [tests/test_capacity.py](../../hotel-booking/tests/test_capacity.py) |
| 2 · PostgreSQL in Docker | Compose file (postgres:18, hotel/hotel/hotel, 5432, init script, volume); portable schema (two tables, one per module, no FK, rules + partial index, R7/R8) | [docker-compose.yml](../../hotel-booking/docker-compose.yml), [db/postgres/init.sql](../../hotel-booking/db/postgres/init.sql) |
| 3 · API contract | OpenAPI 3.1: three operations (+ `GET /openapi.yaml`), answers, five operation error titles, examples; API decisions | [docs/openapi.yaml](../../hotel-booking/docs/openapi.yaml), [design-notes § API decisions](../../hotel-booking/docs/design-notes.md#api-decisions), [API-design.md](API-design.md) |
| 3 · contract == implementation (own standard) | Test: every route/status/title in the code is in the contract and vice versa; every example is the real answer; schemas validate | [tests/test_openapi_contract.py](../../hotel-booking/tests/test_openapi_contract.py); mutations: [evidence/break_the_contract.py](evidence/break_the_contract.py) |
| 4 · Console → web app | Dependencies; Api file outside the modules serving the contract; `main.py` starts the web app, `--demo`, `--race` | [requirements.txt](../../hotel-booking/requirements.txt), [pyproject.toml](../../hotel-booking/pyproject.toml), [hotel_booking/api.py](../../hotel-booking/hotel_booking/api.py), [main.py](../../hotel-booking/main.py) |
| 5 · The three endpoints | Read → check → call once → answer; problem details; `to_http`; cursor paging; request bodies for curl | [hotel_booking/api.py](../../hotel-booking/hotel_booking/api.py), [docs/requests/](../../hotel-booking/docs/requests/) |
| 6 · API tests | The four tests (12 with the 8 booking tests); every error path; idempotency; `## API tests` | [test_api.py](../../hotel-booking/test_api.py), [tests/test_api_http.py](../../hotel-booking/tests/test_api_http.py), [design-notes § API tests](../../hotel-booking/docs/design-notes.md#api-tests) |
| 7 · Database stores | `SqlRoomCatalog`, `SqlReservationStore` (identity map, `save_changes`, autoflush) in the modules' internal code; one store suite for both stores | [rooms/internal.py](../../hotel-booking/hotel_booking/rooms/internal.py), [reservations/internal.py](../../hotel-booking/hotel_booking/reservations/internal.py), [tests/test_sql_store.py](../../hotel-booking/tests/test_sql_store.py) |
| 8 · Plug it in and prove it | Unit of work in the wiring; api-check (7 requests + restart + table + 11 more); run against uvicorn + curl; same SQL on PostgreSQL 16 | [main.py](../../hotel-booking/main.py), [docs/api-check.md](../../hotel-booking/docs/api-check.md), [tests/test_api_sqlite.py](../../hotel-booking/tests/test_api_sqlite.py), [evidence/api_check.py](evidence/api_check.py), [evidence/postgres_sql_check.py](evidence/postgres_sql_check.py) |
| 10 · Check and hand over | Everything run once more; `## After`; checklist | [design-notes § After](../../hotel-booking/docs/design-notes.md#after-1), [Worksheet § Step 10](Worksheet.md#step-10--check-your-project-and-see-what-comes-next), checklist below |
| Module boundaries (own standard) | Two new border contracts for the API edge; ast checker + self-tests; class rule allows the edge's pydantic shapes only | [.importlinter](../../hotel-booking/.importlinter), [tests/test_architecture.py](../../hotel-booking/tests/test_architecture.py) |
| Diagrams (Mermaid, render-checked) | As-built module dependencies (checked against the real imports), class diagram (UML-conformance target), cancel sequence, booking request flow, deployment | [diagrams/](diagrams/) |
| Evidence | Index with labels, observed runs, logs | [evidence/Index.md](evidence/Index.md), [evidence/observed-runs.md](evidence/observed-runs.md), [evidence/logs/](evidence/logs/) |
| Document checks | Diagrams, design-notes sections, folder, api-check ↔ log, compose, contract, capacity, links | [checks/test_p07_docs.py](checks/test_p07_docs.py) |
| Answers to every "Your turn" | Step by step | [Worksheet.md](Worksheet.md) |
| Reflection | Individual | [reflections/Jasur-Shermatov.md](reflections/Jasur-Shermatov.md) |

## How to check

```bash
cd hotel-booking
python3 -m unittest -v                 # Ran 12 tests ... OK   (8 booking + 4 API)
python3 -m tests.test_architecture     # Contracts: 5 kept, 0 broken.
python3 -m pytest                      # 335 passed
python3 -m mypy                        # Success: no issues found in 22 source files
python3 capacity.py                    # the estimate, line by line
python3 main.py --demo                 # the nine P04 lines
python3 main.py --race                 # still double-books (P09)
python3 main.py                        # the API on http://localhost:5080 (SQLite file hotel.sqlite3)
cd ..
python3 -I practices/P07-capacity-api-design/evidence/api_check.py hotel-booking        # runs docs/api-check.md against the real server
python3 -I practices/P07-capacity-api-design/evidence/break_the_contract.py hotel-booking
python3 -m pytest -p no:cacheprovider practices/*/checks                                # P05, P06, P07 document checks
```

On the Mac, for PostgreSQL: `cd hotel-booking && docker compose up -d && pip install "psycopg[binary]"
&& python main.py --db postgres`, then the requests of `docs/api-check.md` (tick the PostgreSQL column).
Re-render a diagram: `mmdc -p diagrams/puppeteer-config.linux-build.json -i diagrams/X.mmd -o diagrams/X.svg`
(the config points at the container's Chromium with `--no-sandbox`; on a Mac plain `mmdc -i … -o …`).
On macOS `mmdc` works without this file: `mmdc -i diagrams/X.mmd -o diagrams/X.svg` (`diagrams/puppeteer-config.linux-build.json` only points the Linux build environment at its headless Chromium).

## What changed in the code (version 3 → 4)

| File | Change | Kind |
|---|---|---|
| `hotel_booking/api.py` (new) | The HTTP edge: Starlette routes, pydantic request/answer models, problem details for every error (incl. 404/405/500), `to_http`, cursor paging, `GET /openapi.yaml`; blocking work in a thread pool through the unit of work | new edge |
| `hotel_booking/reservations/internal.py` | + `SqlReservationStore` (+ SQL constants, `as_date`) | new internal class |
| `hotel_booking/rooms/internal.py` | + `SqlRoomCatalog` | new internal class |
| `hotel_booking/reservations/booking.py`, `domain.py`, contracts | **unchanged** — the booking rule did not move | — |
| `main.py` | No flag → web app (`--db sqlite|postgres`, `--port`); `--demo`; `--race`; `sqlite_connector`, `postgres_connector`, `sql_unit_of_work`, `build_api` | wiring (deliberate behaviour change of the CLI, as the sheet says) |
| `capacity.py` (new) | The estimate as a program | docs tooling |
| `db/postgres/init.sql`, `docker-compose.yml` (new) | Schema (portable) and PostgreSQL service | infrastructure |
| `docs/` | `capacity.md`, `openapi.yaml`, `api-check.md`, `requests/*.json`, `l04-notes.md` (new); `design-notes.md` P07 sections | docs |
| `.importlinter` | + 2 contracts for the API edge (5 in total) | architecture check |
| `test_api.py` (new) | The course's four API tests | tests |
| `tests/test_api_http.py`, `test_openapi_contract.py`, `test_sql_store.py`, `test_api_sqlite.py`, `test_capacity.py` (new) | Error paths, contract both ways, store substitution + database rules, wiring + restart + race, estimate | tests |
| `tests/test_architecture.py` | 5 contracts; class rule allows `api.py` (pydantic shapes only, new check); checker self-tests for both new rules | tests (deliberate, noted in docstring) |
| `tests/test_demo_and_race.py` | "main without flags runs the demo" → "main --demo runs the demo" | tests (deliberate, noted) |
| `tests/test_dependency_rule.py` | SQL classes are concrete helpers; the API names none (new check) | tests (deliberate, noted) |
| `tests/test_uml_conformance.py` | `CLASS_DIAGRAM` → [P07 class diagram](diagrams/class-diagram.mmd); 2 internal classes, 2 implements lines, 18 links | tests (deliberate, noted) |
| `practices/P06-…/checks/test_p06_docs.py` | The P06 as-built diagram is now a snapshot: every P06 arrow must still exist; equality with the live code moved to the P07 check | doc check (deliberate, noted) |
| `requirements.txt`, `pyproject.toml`, `README.md` | Runtime deps, version 0.7.0, test paths, mypy files; README v4 | config/docs |

Old tests after the code change, before any test update: 5 failed / 113 passed, and 1 P06 document
check failed — each an expected consequence of a deliberate change, each updated with a note
([b1-old-tests-after-the-code-change](evidence/logs/b1-old-tests-after-the-code-change.txt)). The 8
booking tests and the P09 race pins did not change.

## Substitutions (honest record)

| Course material uses | This portfolio uses | Why | Requirement still covered by |
|---|---|---|---|
| FastAPI (+ its TestClient) | **Starlette** routes + **pydantic** models; `starlette.testclient.TestClient` | FastAPI is not installed and PyPI is unreachable here (E17); FastAPI is built on Starlette, so routing, requests, responses and the test client are the same machinery. The contract is hand-written in both cases (the course disables FastAPI's generated one) | `test_api.py` (the four tests), `tests/test_api_http.py`, `tests/test_openapi_contract.py` |
| SQLAlchemy ORM + psycopg, `PostgresReservationStore` / `PostgresRoomCatalog` | **`SqlReservationStore` / `SqlRoomCatalog`** on plain DB-API 2: `sqlite3` (default, tests) or `psycopg` (`--db postgres`); hand-written portable SQL; identity map + `save_changes` = the course's unit of work | Neither library is installable here. The name says what it is: one store for both databases. The same promise (5 methods) and the same `save_changes` as the reference | `tests/test_sql_store.py` (shared suite with the list store), `tests/test_api_sqlite.py`, E9 |
| `db/init.sql` | **`db/postgres/init.sql`**, which SQLite runs too | Own standard; one schema for both databases cannot drift | `test_sqlite_runs_the_file_docker_compose_mounts_into_postgresql`; E6 |
| `docker compose up -d`, psql inside the container | `docker compose config` (validation) + a local **PostgreSQL 16.15** server with `psql` | No Docker daemon here (E17). PostgreSQL 16 vs the compose file's 18: the SQL used is standard and unchanged since well before 16 | E5, E6, E9; the Docker run: **to do by the student** (E16) |
| API check against PostgreSQL with `curl.exe` | Against SQLite with `curl`, executed by `api_check.py` from the document itself; PostgreSQL column left unticked | No driver/daemon here; macOS uses `curl` | E10; PostgreSQL: **to do by the student** |
| `python -m unittest` → 12 tests, then `lint-imports` → "Contracts: 3 kept" | 12 unittest tests (same four API tests) **and** 5 contracts (the 3 + 2 for the API edge) checked by the stdlib ast test; full suite 335 | import-linter not installable (E17); the API edge deserves its own borders | `tests/test_architecture.py`; `lint-imports` on the Mac: to do |
| Swagger editor shows no errors | Structural + schema checks in `test_openapi_contract.py` (refs, ids, params, descriptions, examples valid, contract == code) | No browser/network here | E7, E8; editor: **to do by the student** (E18) |
| Five error titles | Five operation titles **+ MethodNotAllowed + InternalError** | Every answer of the API, even a wrong method or a crash, should have the one error shape (L04 rule 2) | `test_the_problem_title_list_is_exactly_what_the_code_can_send` |
| `BookingResult("Accepted", …)` strings | `BookingOutcome` enum (since P04); `to_http` matches on it | Kept from earlier versions | `to_http`, contract test |

## Requirements checklist

Sources: P07 Activity sheet (= Student explanation = Student notes = Presentation notes; compared
with `diff`, identical apart from the title block), catalog entry, L04 activity sheet (T10 estimate,
T11 API rules, idempotency, exit check), the Python reference (structure and interfaces) and my
own portfolio conventions.

| # | Requirement (source) | Where it is satisfied | Status |
|---|---|---|---|
| 1 | Start: P06 checks green; `# P07 design notes`; `docs/l04-notes.md` with the peak (Start) | E1; design-notes; l04-notes.md | Done — Observed |
| 2 | Docker Desktop running (Start, Step 2) | — | **To do by the student** (no daemon here) |
| 3 | Step 1: `docs/capacity.md` — heading + line, five assumptions, five results worked out, "To measure later" with the two P08 lines | capacity.md; `test_capacity.py`; `test_capacity_has_the_course_checklist_parts` | Done — Observed (numbers Simulated by nature) |
| 4 | Step 1: peak agrees with l04-notes (3.33/s, 200/min) | `test_the_peak_agrees_with_the_l04_notes` | Done — Observed |
| 5 | Explicit workload assumptions, arithmetic shown and checked | capacity.md (workload model, reasons, calculation column, *Checked by hand*); `capacity.py`; `test_the_arithmetic_with_exact_fractions`, row-by-row doc test; E4 | Done — Observed |
| 6 | Step 2: `docker-compose.yml` as the sheet (postgres:18, hotel, 5432, init.sql, volume) | docker-compose.yml; `test_docker_compose_is_the_sheets_service`; E5 | Done — Observed (config) |
| 7 | Step 2: `db/init.sql` two tables, one per module, no FK, PK, CHECKs, R7/R8 | db/postgres/init.sql; `test_init_sql_has_the_two_tables_and_the_rules`; E6 | Done — Observed (PostgreSQL 16 + SQLite) |
| 8 | Step 2: `docker compose up -d`, `ps`, psql shows R7/R8 | E6 shows R7/R8 on PostgreSQL 16 via psql | Partly — the Docker run is **to do by the student** |
| 9 | Step 2: the database refuses a second R101 and a no-night stay | E6 (PostgreSQL errors), `test_the_primary_key_refuses_a_second_r101`, `test_the_database_refuses_a_wrong_row_by_itself` | Done — Observed |
| 10 | Step 3: `docs/openapi.yaml` — three operations, answers, five error titles, problem details, the three decisions | openapi.yaml; `test_contract_has_the_course_operations_and_titles` | Done — Observed |
| 11 | Step 3: Swagger editor shows no errors | E7 (structural checks) | **To do by the student** (E18) |
| 12 | Step 3: `## API decisions` in design-notes | design-notes | Done |
| 13 | OpenAPI matches the implemented API exactly; test both directions | `tests/test_openapi_contract.py` (35 checks); E8 mutations 6/6 | Done — Observed |
| 14 | API design — resources, methods, status codes, error format, idempotency | [API-design.md](API-design.md); `test_api_http.py` idempotency tests | Done — Observed |
| 15 | Step 4: framework installed, Api file outside the modules serving `/openapi.yaml`; no flag → web app; `--demo`/`--race` unchanged | api.py, main.py; `test_the_contract_is_served_from_the_file`, `test_main_without_a_flag_starts_the_web_app`, `test_main_demo_flag_runs_the_demo`; E10 §22 | Done — Observed |
| 16 | Starlette + pydantic; dependencies listed | api.py; requirements.txt | Done |
| 17 | Step 5: read → check → call once → answer; `to_http`; `limit`/`after` in text order; `docs/requests/` three bodies; curl checks incl. `limit=1` → `"next":"R7"` | api.py; `test_search_limit_1_gives_one_room_and_next`, `test_search_pages_follow_text_order_and_the_cursor`; `test_course_request_bodies_are_exactly_the_sheets`; E10 | Done — Observed |
| 18 | Step 6: the four API tests; 15 green (Python: 12 tests + contracts) | test_api.py; E11 (12 OK; 5 contracts) | Done — Observed |
| 19 | Step 6: 409 → 201 fails, then back | E11 | Done — Observed |
| 20 | Step 6: `## API tests` with one line per test | design-notes; `test_design_notes_have_the_p07_sections` | Done |
| 21 | API tests via TestClient covering success and **every** error path | `tests/test_api_http.py` (92), contract probes (every documented answer) | Done — Observed |
| 22 | Step 7: catalog and store over the init.sql tables, in Rooms'/Reservations' internal code; rule unchanged | internal.py ×2; booking.py unchanged; `test_booking_service_gives_the_same_records_on_both_stores` | Done — Observed |
| 23 | Persistence adapter behind the existing `ReservationStore` contract (sqlite3) | `SqlReservationStore`; shared store suite; UML: `implements` checked | Done — Observed |
| 24 | Step 7: checks still green; only the wiring names the stores | `test_only_main_creates_concrete_classes_of_the_modules`, `test_the_api_names_no_concrete_helper`, contracts | Done — Observed |
| 25 | Step 7: find each numbered arrow of the cancel diagram in the code | [cancel-sequence](diagrams/cancel-sequence.svg); Worksheet § Step 7 item 6; `test_cancel_sequence_follows_the_code` | Done |
| 26 | Step 8: wiring picks the database stores; unit of work saves at the end (rolls back on error) | main.py; `test_a_request_that_fails_half_way_leaves_nothing_behind` | Done — Observed |
| 27 | Step 8: `docs/api-check.md`; seven ✓; restart check; table R101 Cancelled / R102 Confirmed | api-check.md; E10 (SQLite, 21/21 + restart); `test_api_check_seven_requests_then_the_restart`; `test_api_check_ticks_are_backed_by_the_observed_run` | Done on SQLite — Observed; **PostgreSQL column to do by the student** (E16) |
| 28 | Real run of the API with uvicorn + curl, real outputs | E10 log incl. uvicorn's access log | Done — Observed |
| 29 | `db/postgres/init.sql` + `docker-compose.yml` for the Mac; PostgreSQL-specific statements documented | both files; init.sql header (none PostgreSQL-only in P07; date/text note) | Done |
| 30 | Respect module boundaries; update `.importlinter` and the ast test for the API layer; API uses public contracts only | 2 new contracts; checker self-tests for each; E13 "5 kept" | Done — Observed |
| 31 | §10: keep earlier tests green, update deliberately with notes | Notes in each changed test module; table above; b1 log | Done — Observed |
| 32 | §10: race still double-books; keep the P09 defect pinned | `test_race_double_books_r7_known_defect` (unchanged) + two HTTP/SQLite race pins, 20/20 (E14) | Done — Observed |
| 33 | §10: run everything; `## After` (checks, seven answers, restart) | E15; design-notes § After | Done — Observed |
| 34 | §10: P07 checklist (capacity, compose/init, openapi, Api file, checks, stores, api-check, design-notes) | this table; `checks/test_p07_docs.py` | Done (Docker items: student) |
| 35 | Diagrams in Mermaid, render-checked with `mmdc` (own standard) | [diagrams/](diagrams/); [logs/mmdc.txt](evidence/logs/mmdc.txt) (5 × exit 0) | Done — Observed |
| 36 | Evidence labelled; reflection; worksheet answers (own standard) | evidence/; reflection; Worksheet | Done |
| 37 | P07 row in the portfolio README (own standard) | [../../README.md](../../README.md); `test_portfolio_readme_has_a_p07_row` | Done |
| 38 | §10: `docker compose down` (keep the data for P08); copy the folder to the partner; pair work, swapping the typist | — | **To do by the student** |

The sheet's "Where the hotel app goes next" (P08 cache, L05, P09 race fix) is a preview, not a P07
task; the known limitations in the [project README](../../hotel-booking/README.md#known-limitations-of-version-7)
point at those practices.

## Self-check before submission

- [x] `BookingService` and the booking rule unchanged; the 8 booking tests unchanged; demo identical; race still there
- [x] Every route, status, error title and example of the contract is produced by the code — and nothing else is
- [x] Every error path has a test; the four course API tests pass and were seen failing (409 → 201)
- [x] The SQL store passes the same suite as the list store (after a real red → green)
- [x] The API edge uses public contracts only; 5 border contracts kept; checker tested on each new rule
- [x] Real server, real curl: 21/21; the booking survives a restart
- [x] Nothing claims a Docker, psycopg, Swagger-editor or `lint-imports` run that did not happen
