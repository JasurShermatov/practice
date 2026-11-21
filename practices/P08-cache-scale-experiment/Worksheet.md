# P08 worksheet — answers to every "Your turn"

Practice: P08 Cache and scale experiment · Session: Saturday 7 November 2026, 09:30–10:50, room 232.
Paths are relative to `hotel-booking/` unless they start with `practices/`. Evidence labels:
**Observed** = run, output in [evidence/logs](evidence/logs); **Proposed** = to run on the Mac.

## Your turn · open your project

1. *Docker Desktop running* — not possible in the build container (no Docker daemon). Instead a
   local `redis-server` 7.0.15 is started by the evidence scripts; PostgreSQL stays on SQLite here
   (P07 substitution). On the Mac: **to do by the student** (`docker compose up -d`).
2. *Project open, two terminals* — terminal 1 runs `python main.py`, terminal 2 runs
   `tools/measure.py`, `curl` and `redis-cli` (the evidence scripts play both terminals).
3. *P07 checks green first* — **Observed** before any change: 12 unittest tests OK, 5 contracts
   kept, 335 pytest tests, 95 document checks
   ([b0-baseline.txt](evidence/logs/b0-baseline.txt)). The course expects "Contracts: 3 kept";
   this portfolio has the course's 3 plus 2 for the API edge (P07).
4. `# P08 design notes` added at the bottom of [design-notes.md](../../hotel-booking/docs/design-notes.md#p08-design-notes).
5. "To measure later" in [capacity.md](../../hotel-booking/docs/capacity.md#to-measure-later): both
   P08 lines are now answered with measured numbers (p95 1.31 ms / 1.13 ms; exactly one query per
   room per search).

## Step 1 · Your turn · measure the search

1. `/stats` operation and `Stats` schema in [openapi.yaml](../../hotel-booking/docs/openapi.yaml),
   version **1.1.0** (a new operation breaks no client). Portfolio additions: the fifth counter
   `cacheErrors` and the `X-Cache` header of the search (both documented, both checked).
2. `Stats` and `CountingReservationStore` — in [hotel_booking/api_stats.py](../../hotel-booking/hotel_booking/api_stats.py)
   (the course keeps them in `api.py`; here `api.py` holds only HTTP shapes, a P07 architecture
   rule). `Stats.add` takes a lock (Starlette's thread pool runs requests in parallel; the test
   `test_counters_are_exact_under_threads` adds 80,000 times from 8 threads).
3. `GET /stats` and `stats.add("searches")` right after the search's checks
   ([api.py](../../hotel-booking/hotel_booking/api.py) `find_free_rooms`); the wiring wraps the
   SQL store (`main.py` `sql_unit_of_work`); the test helper of `test_api.py` wraps the list store.
4. Checks after Step 1: green (the old tests that had to change, and why, are listed in the
   P08 README; [b1 log](evidence/logs/b1-old-tests-after-the-code-change.txt)).
5. [tools/measure.py](../../hotel-booking/tools/measure.py): standard library, one keep-alive
   connection per client, prints the course's five lines (average, p95, total, GET /stats
   difference) plus p50/p99/max, throughput and the X-Cache count; `--clients`, `--json`.
6. Row "No cache" in [cache-experiment.md](../../hotel-booking/docs/cache-experiment.md#measurements):
   **Observed**, median of 5 runs: 1,000 searches, **2,000 queries**, 0 hits, average 0.92 ms,
   p95 1.31 ms (`python main.py --cache off`).

*Explanation check:* 2,000 queries for 1,000 searches = one per room per search — the P07 estimate
was right, and the SQLite trace in `test_stats_count_real_sql_queries` confirms the counter
counts real SELECTs.

## Step 2 · Your turn · start Redis

1. `cache` service added to [docker-compose.yml](../../hotel-booking/docker-compose.yml) above
   `volumes:` — `image: redis:8`, `"6379:6379"`, no volume (plus a `redis-cli ping` healthcheck).
2. First comment line: "The hotel booking app's database and cache …".
3. – 5. `docker compose up -d` / `ps` / `exec cache redis-cli ping` — **to do by the student** on
   the Mac. Observed here instead: `docker compose config` accepts the file with both services
   ([docker-compose-config.txt](evidence/logs/docker-compose-config.txt)), and a local redis-server
   answers `PONG` ([cache-behaviour.txt § A](evidence/logs/cache-behaviour.txt)).

*Why no volume:* Redis holds only copies. Losing them costs one database question per stay; losing
PostgreSQL's volume would lose bookings.

## Step 3 · Your turn · add the cache

1. Install line: the course installs `redis==8.1.0`. Not installable here (no PyPI), so
   [api_redis.py](../../hotel-booking/hotel_booking/api_redis.py) speaks Redis's RESP2 protocol with
   the standard library (substitution; nothing to install).
2. Cache file: [api_cache.py](../../hotel-booking/hotel_booking/api_cache.py) — `KeyValueStore`
   (GET, SET with TTL, INCR), `AvailabilityCache` (key with version, TTL 30 s, `invalidate`),
   `InMemoryKeyValueStore` (with real expiry and an injectable clock).
3. Search endpoint: `search_free_rooms` in api.py — key and lookup first, hit → rooms from the
   copy without a unit of work, miss → `find_free_rooms` through the unit of work, then `put`.
   Paging happens on the copy.
4. `create_app(rooms, unit_of_work, stats, cache)` — cache is the last parameter as in the course;
   the wiring connects to Redis (`build_cache`, `redis_from_environment`, PING at start-up).
5. Test helper with the cache "in a dictionary" (`InMemoryKeyValueStore`) in `test_api.py`; checks green.
6. Two searches + `KEYS "availability:*"` → one key `availability:v0:2026-11-12:2026-11-14`,
   value `R7,R8`, `TTL` 30 — **Observed** ([§ B](evidence/logs/cache-behaviour.txt)).
7. The numbered arrows of the course diagram "One search through the cache", found in my code
   (as built: [search-through-cache](diagrams/search-through-cache.svg)):

| Arrow | What happens | Where in the code |
|---|---|---|
| 1 | The tool/curl sends GET /rooms/availability | `tools/measure.py` `Client.get`; `api.py` `find_free_rooms` (route `/rooms/availability`) |
| 2 | Read the version, build the key, GET the copy | `api.py` `search_free_rooms` → `run_in_threadpool(cache.lookup, …)`; `api_cache.py` `key` / `lookup`; `api_redis.py` `get` → `GET` |
| 3 | Miss: run FindFreeRooms through the unit of work | `api.py` `search_free_rooms` → `in_unit_of_work(… service.find_free_rooms(stay))`; `main.py` `sql_unit_of_work` |
| 4 | BookingService asks the store once per room; the counting store adds 1 each | `booking.py` `find_free_rooms` → `has_overlap`; `api_stats.py` `CountingReservationStore.has_overlap` |
| 5 | One SELECT per room | `reservations/internal.py` `SqlReservationStore.has_overlap` → `HAS_OVERLAP` (`SELECT EXISTS (SELECT 1 FROM reservations WHERE room = ? AND status = 'Confirmed' AND …)`) |
| 6 | Keep the answer: SET key "R7,R8" EX 30 | `api.py` → `run_in_threadpool(cache.put, …)`; `api_cache.py` `put`; `api_redis.py` `set` → `SET … EX 30` |
| 7 | After a 201/204: INCR availability:version | `api.py` `reserve` / `cancel` → `invalidate_cache` (after `in_unit_of_work`); `api_cache.py` `invalidate`; `api_redis.py` `increment` → `INCR` |

A hit uses only arrows 1 and 2 (`test_first_search_misses_second_hits_and_asks_nobody`: one unit
of work for two searches).

## Step 4 · Your turn · measure with the cache

1. – 3. App with Redis, `FLUSHALL`, the tool: **Observed** — `{"searches":1000,"databaseQueries":2,"cacheHits":999,"cacheMisses":1,"cacheErrors":0}`
   in every one of the 5 runs ([experiment-raw.txt](evidence/logs/experiment-raw.txt)).
4. Row "Cache-aside, TTL 30 s": average **0.72 ms**, p95 **1.13 ms** (median of 5).
5. Two lines below the table: both runs meet S1 (p95 ≤ 1 s) by far, with two rooms and one client;
   the cache removed 1,998 of 2,000 queries (and 39,960 of 40,000 with 40 rooms, measured).

*Beyond the sheet (Observed, all in cache-experiment.md):* repeated, interleaved runs with ranges;
the in-process cache as a third row; CPU per 1,000 searches (S6 proxy); 40 rooms; 8 clients at once
(which showed a cache stampede: 8 misses).

## Step 5 · Your turn · watch the stale result

1. Fresh database and empty cache; app started with `--no-invalidation` (the switch replaces
   "edit the invalidate line out and back in").
2. – 3. The four requests within 30 s — **Observed** ([§ C](evidence/logs/cache-behaviour.txt)):
   200 R7+R8 (miss) → 201 R101 → **200 R7+R8 (hit, stale)** → **409 Unavailable**.
4. Section "Stale result" in [cache-experiment.md](../../hotel-booking/docs/cache-experiment.md#stale-result-step-5-before-invalidation).
5. `## Cache rule` in design-notes: "Booking never reads the cache."

Pinned as tests: `test_stale_result_without_invalidation_known_trade_off` (list store, fake clock —
the TTL then ends the stale copy) and `test_step5_the_stale_result_through_the_real_wiring` (SQLite + real Redis).

## Step 6 · Your turn · invalidate

1. `invalidate_cache` after the unit of work in `reserve` (only for `ACCEPTED`) and `cancel` (only
   for 204).
2. The two course tests in `test_api.py`; `python -m unittest` → **Ran 14 tests … OK**; contracts
   **6 kept** (course: 3).
3. Removed the invalidate line from POST (on a copy): the course's second cache test failed —
   `test_a_booking_and_a_cancel_make_the_next_search_fresh` — plus 8 pytest checks; then the
   original was green again ([break-the-cache.txt](evidence/logs/break-the-cache.txt), mutation 1;
   8 more mutations, all caught).
4. Fresh database and cache, the four requests again — **Observed** ([§ D](evidence/logs/cache-behaviour.txt)):
   third answer **R8 only** (miss, key `…:v1:…`); cancel R101 → version 2 → R7 and R8 again.
5. Section "After invalidation" in cache-experiment.md.

## Step 7 · Your turn · find the next bottleneck

1. `tools/measure.py 2026-12-31 2027-01-02`: **999 hits**, 1 miss, 2 queries (§ E).
2. `KEYS availability:*`: the one New Year key (no version key yet: nobody had booked).
3. New Year booking (`docs/requests/maya-newyear.json`), one search, KEYS: `…:v0:…`, `…:v1:…` and
   `availability:version` side by side; 31 s later only `availability:version` — the old copy
   expired by itself.
4. Section "Hot key and the next bottleneck" — own words, plus a measured busy sale (40 rooms, a
   booking after every 50th of 1,000 searches: 98 % hits, 860 queries instead of 40,000) and the
   diagram [bottleneck-moves](diagrams/bottleneck-moves.svg).

## Step 8 · Your turn · write ADR-002

1. – 3. [docs/adr-002-cache-availability.md](../../hotel-booking/docs/adr-002-cache-availability.md):
   Context, Decision, Alternatives considered, Consequences, Revisit when — own words, own numbers.
   It also records where the cache sits (edge, sixth border contract) and the decision to keep
   requests working when Redis stops (observed in § G), which differs from the course reference.

## Step 10 · Your turn · check and hand over

1. Run everything — **Observed** at the end ([f-* logs](evidence/logs/)): unittest 14 OK, 6 contracts
   kept, full pytest suite, mypy strict, demo (nine lines unchanged), race (still double-books), the
   API with Redis, the measurement tool, every document check, every diagram rendered.
2. The course checklist, item by item: see the P08 README "Requirements checklist".
3. `## After` in design-notes with the three lines (checks; the two measurements; the stale result
   and its fix).
4. `docker compose down` without `-v` (keep the data for P09) — **to do by the student** on the Mac.
5. Copy the folder to the partner's laptop; pair work with the typist swapped at every step — **to
   do by the student**.

## The open question P08 leaves for P09

Searches no longer load the database; bookings do (3 exact queries each). And two bookings for R7
at exactly the same moment can still both pass the check: the race is pinned by
`test_race_double_books_r7_known_defect` and the two HTTP/SQLite race tests, unchanged in P08 —
the cache neither causes nor fixes it, because booking never reads the cache.
