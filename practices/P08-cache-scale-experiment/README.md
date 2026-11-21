# P08 — Cache and scale experiment

**Session:** Saturday 7 November 2026, 09:30–10:50 (Asia/Tashkent) · Practice · Group 23-309 SW · Room 232
**Related lecture:** L04 — System design: capacity, APIs, caching and scaling (T12: the stale-cache risk)
**Type of work:** evolution of the growing [hotel-booking](../../hotel-booking/README.md) codebase
(version 4 → version 5): measure the search, cache it, measure again, find where a cache can be
wrong, decide and record.

## Goal

Answer P07's "To measure later" with real numbers, then make the busiest part — the free-room
search — cheap for the database without ever letting a cached copy decide a booking: measure
without a cache, add cache-aside in Redis (versioned key, TTL 30 s), measure the same workload
again, watch the stale result happen, fix it with invalidation, look at the hot key and the next
bottleneck, and write the decision down as ADR-002.

## Outputs (requirement → file)

| Step (activity sheet) | Output | File |
|---|---|---|
| Start · open your project | P07 checks green first; `# P08 design notes`; "To measure later" answered | [b0-baseline](evidence/logs/b0-baseline.txt), [design-notes § P08](../../hotel-booking/docs/design-notes.md#p08-design-notes), [capacity.md](../../hotel-booking/docs/capacity.md#to-measure-later) |
| 1 · Measure without a cache | `GET /stats` in the contract (1.1.0) and the code; `Stats` + `CountingReservationStore`; the wiring and the test helper count; the measurement tool; row "No cache" | [openapi.yaml](../../hotel-booking/docs/openapi.yaml), [api.py](../../hotel-booking/hotel_booking/api.py), [api_stats.py](../../hotel-booking/hotel_booking/api_stats.py), [main.py](../../hotel-booking/main.py), [test_api.py](../../hotel-booking/test_api.py), [tools/measure.py](../../hotel-booking/tools/measure.py), [cache-experiment.md](../../hotel-booking/docs/cache-experiment.md#measurements) |
| 2 · Start Redis | `cache` service (redis:8, 6379, no volume) | [docker-compose.yml](../../hotel-booking/docker-compose.yml); [docker-compose-config](evidence/logs/docker-compose-config.txt) |
| 3 · Cache-aside for the search | Cache file (key with version, value, TTL 30 s, `KeyValueStore`); Redis adapter; search endpoint reads the cache first; wiring connects to Redis; test helper with a cache "in a dictionary"; the diagram's arrows found in the code | [api_cache.py](../../hotel-booking/hotel_booking/api_cache.py), [api_redis.py](../../hotel-booking/hotel_booking/api_redis.py), [api.py](../../hotel-booking/hotel_booking/api.py) `search_free_rooms`, [main.py](../../hotel-booking/main.py) `build_cache`, [Worksheet § Step 3](Worksheet.md#step-3--your-turn--add-the-cache), [search-through-cache](diagrams/search-through-cache.svg) |
| 4 · Measure with the cache | FLUSHALL, the same 1,000 searches, row "Cache-aside, TTL 30 s", two lines below the table | [cache-experiment.md](../../hotel-booking/docs/cache-experiment.md#measurements), [run_experiment.py](evidence/run_experiment.py), [experiment-summary](evidence/logs/experiment-summary.md) |
| 5 · See the stale result | The four requests, stale third answer, 409; "Stale result"; `## Cache rule` | [cache-behaviour § C](evidence/logs/cache-behaviour.txt), [cache-experiment.md § Stale result](../../hotel-booking/docs/cache-experiment.md#stale-result-step-5-before-invalidation), [design-notes § Cache rule](../../hotel-booking/docs/design-notes.md#cache-rule), [stale-result](diagrams/stale-result.svg) |
| 6 · Invalidate on every change | INCR after a committed 201/204; the two course tests; red without the line; "After invalidation" | [api.py](../../hotel-booking/hotel_booking/api.py) `invalidate_cache`, [test_api.py](../../hotel-booking/test_api.py), [break-the-cache](evidence/logs/break-the-cache.txt), [cache-behaviour § D](evidence/logs/cache-behaviour.txt) |
| 7 · Hot key and the next bottleneck | New Year measurement, KEYS before/after a booking and after the TTL; busy sale; section in own words | [cache-experiment.md § Hot key](../../hotel-booking/docs/cache-experiment.md#hot-key-and-the-next-bottleneck-step-7), [cache-behaviour § E, F](evidence/logs/cache-behaviour.txt), [bottleneck-moves](diagrams/bottleneck-moves.svg), [maya-newyear.json](../../hotel-booking/docs/requests/maya-newyear.json) |
| 8 · ADR-002 | Context, decision, alternatives, consequences, revisit when — own words, own numbers; what happens when Redis stops | [adr-002-cache-availability.md](../../hotel-booking/docs/adr-002-cache-availability.md), [cache-behaviour § G](evidence/logs/cache-behaviour.txt) |
| 10 · Check and hand over | Everything run once more; `## After` (three lines); checklist | [f-* logs](evidence/logs/), [design-notes § After](../../hotel-booking/docs/design-notes.md#after-2), checklist below |
| Cache design | What is cached, key, TTL/invalidation, where it sits relative to the module borders | [ADR-002 § Decision](../../hotel-booking/docs/adr-002-cache-availability.md#decision), [module-dependencies](diagrams/module-dependencies.svg), [cache-classes](diagrams/cache-classes.svg), [.importlinter](../../hotel-booking/.importlinter) |
| Real experiment | Workload stated, environment, repeated interleaved runs, real numbers, honest limitations; scale scenarios (40 rooms, 8 clients); CPU as S6 proxy | [cache-experiment.md](../../hotel-booking/docs/cache-experiment.md), [experiment-raw](evidence/logs/experiment-raw.txt), [experiment-results.json](evidence/logs/experiment-results.json) |
| Correctness cost | Stale availability demonstrated by a test and for real; mitigation (invalidation after commit + TTL) tested | `test_stale_result_without_invalidation_known_trade_off`, `test_step5_…`, `test_step6_…`, `test_with_invalidation_…` |
| Tests for hit/miss/expiry/invalidation | Unit, HTTP, real Redis, wiring, tool | [test_cache.py](../../hotel-booking/tests/test_cache.py), [test_api_cache.py](../../hotel-booking/tests/test_api_cache.py), [test_redis_store.py](../../hotel-booking/tests/test_redis_store.py), [test_cache_wiring.py](../../hotel-booking/tests/test_cache_wiring.py), [test_measure.py](../../hotel-booking/tests/test_measure.py) |
| OpenAPI kept equal both ways | `/stats`, `Stats`, `X-Cache`; contract test updated, new header direction | [openapi.yaml](../../hotel-booking/docs/openapi.yaml), [test_openapi_contract.py](../../hotel-booking/tests/test_openapi_contract.py) |
| Diagrams (Mermaid, render-checked) | As-built imports (checked), cache classes (checked), search sequence, stale vs fresh, deployment + scale-out, bottleneck | [diagrams/](diagrams/), [mmdc log](evidence/logs/mmdc.txt) |
| Evidence | Index with labels, observed runs, logs, scripts | [evidence/Index.md](evidence/Index.md), [observed-runs.md](evidence/observed-runs.md) |
| Document checks | Diagrams = code, sections, folder, compose, contract, table = observed summary, logs, links | [checks/test_p08_docs.py](checks/test_p08_docs.py) |
| Answers to every "Your turn" | Step by step | [Worksheet.md](Worksheet.md) |
| Reflection | Individual | [reflections/Jasur-Shermatov.md](reflections/Jasur-Shermatov.md) |

## How to check

```bash
cd hotel-booking
python3 -m unittest -v                 # Ran 14 tests ... OK   (8 booking + 6 API)
python3 -m tests.test_architecture     # Contracts: 6 kept, 0 broken.
python3 -m pytest                      # 427 passed (the Redis tests need redis-server; they skip without it)
python3 -m mypy                        # Success: no issues found in 31 source files
python3 main.py --demo                 # the nine P04 lines
python3 main.py --race                 # still double-books (P09)
docker compose up -d                   # on the Mac: PostgreSQL 18 + Redis 8
python3 main.py                        # the API with the Redis cache (or --cache memory / --cache off)
python3 tools/measure.py               # second terminal: 1,000 searches
cd ..
python3 -I practices/P08-cache-scale-experiment/evidence/run_experiment.py hotel-booking   # the whole experiment (own redis-server)
python3 -I practices/P08-cache-scale-experiment/evidence/cache_behaviour.py hotel-booking  # Steps 2-8 with curl + redis-cli
python3 -I practices/P08-cache-scale-experiment/evidence/break_the_cache.py hotel-booking  # 9 mutations, all must be caught
python3 -m pytest -p no:cacheprovider practices/*/checks                                  # P05-P08 document checks
```

From P08 on, `python main.py` needs Redis (as in the course). The P07 script `api_check.py` therefore
runs with `HOTEL_REDIS_PORT` pointing at a running Redis — done here: 21 of 21
([api-check-with-redis-cache](evidence/logs/api-check-with-redis-cache.txt)).
Re-render a diagram: `mmdc -p diagrams/puppeteer-config.linux-build.json -i diagrams/X.mmd -o diagrams/X.svg`.
On macOS `mmdc` works without this file: `mmdc -i diagrams/X.mmd -o diagrams/X.svg` (`diagrams/puppeteer-config.linux-build.json` only points the Linux build environment at its headless Chromium).

## What changed in the code (version 4 → 5)

| File | Change | Kind |
|---|---|---|
| `hotel_booking/api_stats.py` (new) | `Stats` (5 counters under a lock), `CountingReservationStore` (decorator keeping the `ReservationStore` promise) | new edge file |
| `hotel_booking/api_cache.py` (new) | `KeyValueStore` promise, `CacheError`, `AvailabilityCache` (key with version, `lookup`, `put`, `invalidate`, TTL 30 s), `InMemoryKeyValueStore` (expiry, clock) | new edge file |
| `hotel_booking/api_redis.py` (new) | `RedisKeyValueStore`: RESP2 over a socket, pooled connections, timeouts, every failure → `CacheError` | new edge file |
| `hotel_booking/api.py` | `GET /stats` (`StatsView`); `search_free_rooms` (cache-aside, `X-Cache`); `invalidate_cache` after the unit of work of a 201/204; fail-open; `create_app(rooms, unit_of_work, stats, cache, *, contract)` | edge (contract keyword-only now) |
| `hotel_booking/reservations/…`, `rooms/…`, `BookingService` | **unchanged** — the booking rule did not move | — |
| `main.py` | Counting store in the unit of work; `build_cache` (`--cache redis|memory|off`, PING at start-up), `--no-invalidation`, `ServerOptions`; version 5 | wiring |
| `tools/measure.py` (new) | The measurement tool (course lines + p50/p99/max, throughput, `--clients`, `--json`) | tool |
| `docs/openapi.yaml` | 1.1.0: `GET /stats`, `Stats`, `X-Cache` header, caching note | contract |
| `docs/` | `cache-experiment.md`, `adr-002-cache-availability.md` (new); `design-notes.md` P08 sections; `capacity.md` "To measure later" answered; `requests/maya-newyear.json` | docs |
| `docker-compose.yml` | + `cache: redis:8` (no volume, healthcheck) | infrastructure |
| `.importlinter` | Two API contracts cover the 3 new edge files; + "The availability cache depends on no module" (6 in total) | architecture check |
| `test_api.py` | Helper with `Stats`, counting store and in-memory cache; + the course's 2 cache tests (`cacheErrors` added to the expected `/stats` text) | tests (deliberate, noted in docstring) |
| `tests/test_cache.py`, `test_api_cache.py`, `test_redis_store.py`, `test_cache_wiring.py`, `test_measure.py` (new), `tests/conftest.py` (+ `redis_server` fixture) | 83 new tests | tests |
| `tests/test_openapi_contract.py` | getStats in the operation list; probe app with stats + cache; probe for the `/stats` example; `StatsView` ↔ `Stats`; header values validated; new check: every header the code sets is documented | tests (deliberate, noted) |
| `tests/test_architecture.py` | `EDGE_FILES` + 3 files; 6 contracts; 2 new design arrows; 3 new checker self-tests | tests (deliberate, noted) |
| `tests/test_api_sqlite.py` | The two CLI tests compare `ServerOptions` instead of `(database, port)` | tests (deliberate, noted) |
| `practices/P07-…/checks/test_p07_docs.py` | The P07 as-built diagram is a snapshot (every P07 arrow must still exist; equality moved to the P08 check); `maya-newyear.json` is not an api-check file | doc check (deliberate, noted) |
| `requirements.txt`, `pyproject.toml`, `README.md` | Note on Redis (no package), version 0.8.0, mypy files, README v5 | config/docs |

Old tests after the code change, before any test update: 4 failed / 331 passed — each an expected
consequence of a deliberate change ([b1](evidence/logs/b1-old-tests-after-the-code-change.txt)).
The 8 booking tests, the four P07 API tests and the P09 race pins did not change.

## Substitutions (honest record)

| Course material uses | This portfolio uses | Why | Requirement still covered by |
|---|---|---|---|
| `redis` package (redis-py 8.1) | **`hotel_booking/api_redis.py`**: a small RESP2 client on the standard library (GET, SET EX, INCR, PING, FLUSHDB; pool; timeouts) behind the same `KeyValueStore` promise | redis-py is not installed and PyPI is unreachable (E19). The protocol is small and documented; swapping in redis-py later changes one file | `test_redis_store.py` against a real redis-server (wire format, expiry, error replies, pooling, outage) |
| `docker compose up -d` with `redis:8`; `docker compose exec cache redis-cli …` | A local **redis-server 7.0.15** started by the scripts and tests; `redis-cli -p <port> …` | No Docker daemon here (E19). GET, SET EX, INCR, KEYS, TTL, FLUSHALL behave the same in 7 and 8 | E7–E12; compose file validated (`docker compose config`); the Docker run: **to do by the student** (E20) |
| PostgreSQL in Docker for the measurements | **SQLite** file (the P07 default) | psycopg cannot be installed (P07 substitution) | E4/E5; the numbers' limits in cache-experiment.md; PostgreSQL run: **to do** (E20) |
| FastAPI (+ TestClient) | Starlette + pydantic (P07 substitution) | — | as in P07 |
| Stats and the counting store inside `api.py` | **`api_stats.py`** next to `api.py`; cache in `api_cache.py` (as the course) + `api_redis.py` | P07's architecture rule keeps `api.py` to HTTP shapes; one cohesive file per concern | `test_api_edge_classes_are_only_http_shapes`, 6 contracts |
| Four counters | Four **+ `cacheErrors`** | The fail-open cache needs a visible signal | contract test, `test_cache_down_*` |
| Edit the invalidate line out (Step 5) and back in (Step 6) | `--no-invalidation` switch (`AvailabilityCache(invalidate_on_change=False)`); the line removal itself is done on copies by `break_the_cache.py` | The stale result stays reproducible with the final code; the sheet's "watch the test fail" is still shown | E8, E10 |
| Redis down → search fails, booking saved but error | **Fail-open**: search from the database, booking 201, `cacheErrors` + log | Avoids an error for a saved booking (POST is not idempotent until P11); TTL bounds a missed invalidation | E12, `test_cache_down_*`, ADR-002 |
| `lint-imports` → "Contracts: 3 kept" | 6 contracts checked by the stdlib ast test | import-linter not installable; the edge deserves its own borders | `tests/test_architecture.py`; `lint-imports` on the Mac: to do |
| "17 green: 14 tests and 3 contracts" | 14 unittest tests **and** 6 contracts; full suite 427 | Portfolio adds tests beyond the course's | E18 |
| `curl.exe` (Windows) | `curl` (Linux/macOS) | Student uses macOS | — |

## Requirements checklist

Sources: P08 Activity sheet (= Student explanation = Student notes = Presentation notes, compared
with `diff`: identical apart from the title block), catalog entry (Saturday 7 Nov 2026, room 232),
L04 (T12 stale-cache risk, scale up/out, stateless instances), the Python reference (structure and
interfaces) and my own portfolio conventions.

| # | Requirement (source) | Where it is satisfied | Status |
|---|---|---|---|
| 1 | Start: Docker Desktop running; `docker compose up -d` (Start) | — | **To do by the student** (no daemon here) |
| 2 | Start: P07 checks green; `# P08 design notes`; find "To measure later" | E1; design-notes; capacity.md answered | Done — Observed |
| 3 | Step 1: `/stats` + `Stats` schema in openapi.yaml, version 1.1.0 | openapi.yaml; `test_contract_is_1_1_0_with_get_stats`; contract test | Done — Observed |
| 4 | Step 1: `Stats` (thread-safe) and `CountingReservationStore` | api_stats.py; `test_counters_are_exact_under_threads`, `test_the_counting_store_counts_every_promised_call…` | Done — Observed |
| 5 | Step 1: GET /stats; `searches` counted after the checks; wiring and test helper count | api.py, main.py, test_api.py; `test_a_rejected_search_is_not_counted`, `test_stats_count_real_sql_queries` | Done — Observed |
| 6 | Step 1: measurement tool (1,000 searches, one connection, average, p95, total, stats difference) | tools/measure.py; `test_measure.py` (real uvicorn) | Done — Observed |
| 7 | Step 1: row "No cache" with own times | cache-experiment.md (5 runs); `test_the_measurement_table_is_the_observed_summary` | Done — Observed |
| 8 | Step 2: cache service in docker-compose.yml, comment line | docker-compose.yml; `test_docker_compose_has_the_course_cache_service`; compose config log | Done — Observed (config) |
| 9 | Step 2: `docker compose up -d`, `ps`, `redis-cli ping` → PONG | PONG from local redis-server (E7) | Partly — Docker run **to do by the student** |
| 10 | Step 3: Redis client installed | RESP2 client (substitution) | Done — substitution recorded |
| 11 | Step 3: cache file (key with version, value, TTL 30 s, three commands behind a contract) | api_cache.py; `test_cache.py` | Done — Observed |
| 12 | Step 3: search reads Redis first, database only on a miss, keeps a copy; paging on the copy; a hit opens no unit of work | api.py `search_free_rooms`; `test_first_search_misses_second_hits_and_asks_nobody`, `test_paging_is_done_on_the_copy` | Done — Observed |
| 13 | Step 3: wiring connects to Redis (HOTEL_REDIS_PORT), stops if Redis is not running | main.py `build_cache`; `test_the_app_does_not_start_when_redis_does_not_answer`, `test_redis_address_from_the_environment` | Done — Observed |
| 14 | Step 3: tests without Redis (cache in a dictionary); checks still green | test_api.py helper; E18 | Done — Observed |
| 15 | Step 3: two searches → one key in Redis | E7 | Done — Observed |
| 16 | Step 3: find each numbered arrow of the diagram in the code | Worksheet § Step 3 item 7; [search-through-cache](diagrams/search-through-cache.svg); `test_search_sequence_uses_the_real_key_commands_and_names` | Done |
| 17 | Step 4: FLUSHALL, same 1,000 searches → 2 queries, 999 hits, 1 miss; row "Cache-aside, TTL 30 s"; two lines (S1, queries removed) | cache-experiment.md; E4 (every run); `test_every_run_has_the_expected_counts` | Done — Observed |
| 18 | Step 5: empty database + cache; four requests; third answer stale; fourth 409 | E8; `test_step5_the_stale_result_through_the_real_wiring`; `test_stale_result_without_invalidation_known_trade_off` | Done — Observed |
| 19 | Step 5: "Stale result" section; `## Cache rule` with "booking never reads the cache" | cache-experiment.md; design-notes; `test_design_notes_have_the_p08_sections` | Done |
| 20 | Step 6: invalidate after the unit of work, only for 201 and 204 | api.py; `test_the_version_is_raised_after_the_unit_of_work`, `test_a_request_that_changes_nothing_keeps_the_version`, `test_a_409_keeps_the_version` | Done — Observed |
| 21 | Step 6: the two cache tests; 14 unittest tests + contracts green | test_api.py; E18 (14 OK, 6 kept) | Done — Observed |
| 22 | Step 6: remove the invalidate line → the second test fails; put it back | E10 (mutation 1) | Done — Observed |
| 23 | Step 6: the four requests again → third answer R8 only; "After invalidation" | E9; cache-experiment.md | Done — Observed |
| 24 | Step 7: New Year measurement (999 hits); KEYS; booking + KEYS (new version next to the old, old expires); section in own words | E11; cache-experiment.md § Hot key | Done — Observed |
| 25 | Step 8: ADR-002 with the five sections, own words and numbers | adr-002; `test_adr_002_has_the_five_sections_and_the_course_alternatives` | Done |
| 26 | Step 8: what happens if Redis stops | E12; ADR-002 Decision 7 + Consequences | Done — Observed (own fail-open design) |
| 27 | §10: run everything (checks, demo, race, API, tool) | E16–E18 | Done — Observed |
| 28 | §10: race still double-books (P09) | E17; pins unchanged | Done — Observed |
| 29 | §10: P08 checklist (openapi, compose, Api folder, tool, checks, cache-experiment, ADR-002, design-notes) | this table; `checks/test_p08_docs.py` | Done (Docker items: student) |
| 30 | §10: `## After` with three lines | design-notes; doc check | Done |
| 31 | §10: `docker compose down` (without -v); copy the folder to the partner; pair work, swapping the typist | — | **To do by the student** |
| 32 | Cache design — what, key, TTL/invalidation, where relative to module boundaries | ADR-002 Decision 1–6; `.importlinter` cache contract; module-dependencies diagram (= real imports) | Done — Observed |
| 33 | Measurement tool + REAL experiment with and without cache, workload stated, environment, repeated runs, limitations | cache-experiment.md; run_experiment.py; E4–E6 | Done — Observed |
| 34 | Correctness cost demonstrated by a test, with the mitigation | E8/E9; stale tests (pinned) + invalidation tests; ordering tests | Done — Observed |
| 35 | OpenAPI updated, contract test passing both directions | E14; new header direction check | Done — Observed |
| 36 | Tests for hit/miss/expiry/invalidation | 83 tests in five files (E13) + 2 course tests | Done — Observed |
| 37 | Earlier tests green; changes deliberate with notes; boundary checks pass; race pinned | b1 log; notes in each changed test module; 6 kept; E17 | Done — Observed |
| 38 | Diagrams in Mermaid, render-checked with mmdc | [diagrams/](diagrams/) (6), [mmdc log](evidence/logs/mmdc.txt) | Done — Observed |
| 39 | Evidence logs, worksheet answers, reflection; root README row | evidence/, Worksheet.md, reflection, `test_portfolio_readme_has_a_p08_row` | Done |
| 40 | E20: the experiment on the Mac with PostgreSQL 18 + Redis 8 in Docker; Swagger editor check of 1.1.0; `lint-imports` | — | **To do by the student** |

## Self-check before submission

- [x] `BookingService` and the booking rule unchanged; the 8 booking tests unchanged; demo identical; race still there
- [x] Booking and cancelling never read the cache (ast test, mutation 4 caught); the version rises only after a commit
- [x] Every number in cache-experiment.md comes from a logged run (the doc check compares the table with the summary)
- [x] The stale result was seen, pinned by a test, and fixed; the fix was seen failing when removed
- [x] Contract 1.1.0 equals the code both ways; 6 border contracts kept; the cache knows no module
- [x] Nothing claims a Docker, PostgreSQL-through-the-app, redis-py, Swagger-editor or `lint-imports` run that did not happen
