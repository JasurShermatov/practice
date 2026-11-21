# Advanced Software Design & Architecture — practice portfolio

PDP University · Pearson BTEC Level 6 · Unit 3 (70727U)
Student: Jasur Shermatov · Group: 23-309 SW

This repository holds my practice work for the course. Every practice lives in its own folder
and builds on the same fictional project from the course brief: a small **concert ticket-booking
app** for organiser Claire (20 unnumbered tickets per concert, one ticket per customer, no
payment in version one).

From P03 on, the practices also grow one Python codebase, [hotel-booking/](hotel-booking), for a
separately introduced fictional hotel (rooms R7 and R8, one guest per room per night).

| Practice | Topic | Folder | Status |
|---|---|---|---|
| P01 | Course introduction workshop and project baseline | [practices/P01-project-baseline](practices/P01-project-baseline) | Done (classmate cross-check and online submission: to do by the student) |
| P02 | OS introduction, kernels and process lifecycle | [practices/P02-os-process-lifecycle](practices/P02-os-process-lifecycle) | Done (Linux observed; macOS rerun, pair review and online submission to do) |
| P03 | Hotel booking domain and UML workshop (starts the [hotel-booking](hotel-booking) codebase) | [practices/P03-hotel-domain-uml](practices/P03-hotel-domain-uml) | Done (pair review and partner hand-over: to do by the student) |
| P04 | Refactor a reservation design (SOLID: storage and notification behind protocols; hotel-booking version 2, R6, SMS) | [practices/P04-refactor-reservation](practices/P04-refactor-reservation) | Done (8 unittest / 82 total tests observed; macOS rerun, pair work and partner hand-over: to do by the student) |
| P05 | Hotel domain and context boundaries (quality scenarios S1–S6, ubiquitous language, four bounded contexts, rule owners, context map, borders; design only, no code change) | [practices/P05-domain-context-boundaries](practices/P05-domain-context-boundaries) | Done (26 document checks observed; docs copied into hotel-booking/docs at the start of P06; pair work and partner hand-over: to do) |
| P06 | Modular-monolith architecture review (hotel-booking version 3: four modules with public contracts and internal code, `Confirmation` message, Payments contract, wiring in `main.py`; border contracts in `.importlinter` enforced by a stdlib `ast` test, broken on purpose and restored; ADR-001; "Modules" page; architecture review) | [practices/P06-modular-monolith-review](practices/P06-modular-monolith-review) | Done (8 unittest / 118 total tests, 3 contracts kept, red/green border demo observed; `lint-imports` on the Mac, draw.io check and pair work: to do by the student) |
| P07 | Capacity and API design studio (hotel-booking version 4: capacity estimate checked against a program; hand-written OpenAPI 3.1 contract kept equal to the code in both directions; Starlette + pydantic HTTP API with problem-details errors and cursor paging; SQL store/catalog behind the same promises with a unit of work per request, SQLite by default and the same schema for PostgreSQL in `docker-compose.yml`; api-check run against the real uvicorn server) | [practices/P07-capacity-api-design](practices/P07-capacity-api-design) | Done (12 unittest / 335 total tests, 5 contracts kept, 21/21 curl answers on SQLite with restart, store SQL observed on PostgreSQL 16 via psql; Docker + psycopg run on the Mac, Swagger editor and pair work: to do by the student) |
| P08 | Cache and scale experiment (hotel-booking version 5: `GET /stats` and a counting store; `tools/measure.py`; the search measured without and with a cache-aside Redis cache — key with a version, TTL 30 s, invalidation after every committed booking/cancel, fail-open; the stale result seen and fixed; hot key, stampede and the next bottleneck; contract 1.1.0; `docs/cache-experiment.md` with real repeated runs; ADR-002) | [practices/P08-cache-scale-experiment](practices/P08-cache-scale-experiment) | Done (14 unittest / 427 total tests, 6 contracts kept; 1,000 searches: 2,000 → 2 queries, p95 1.31 → 1.13 ms (median of 5); Docker run on the Mac, PostgreSQL measurement and pair work: to do by the student) |
| P09 | Protect the last seat (hotel-booking version 6: the P03 race fixed - the store's `save` refuses a double booking (`OverlapRejected` → 409), PostgreSQL exclusion constraint `reservations_no_overlap` + id sequence, SQLite triggers + id table, list store under a lock; `tools/race_http.py`, `HOTEL_SLOW_STEP`/`HOTEL_PORT`; the interleaving traced; four repairs measured on PostgreSQL 16; contract 1.2.0; ADR-003) | [practices/P09-protect-the-last-seat](practices/P09-protect-the-last-seat) | Done (16 unittest / 479 total tests, 6 contracts kept; race tool 20 of 20 double bookings before → 0 of 20 after, 1 and 2 instances, SQLite and PostgreSQL 16; 300 simultaneous pairs 0 double bookings; Docker/psycopg run on the Mac, commit and pair work: to do by the student) |
| P10 | Bounded async processing (hotel-booking version 7: the confirmation email left the booking request - a bounded queue (10) with a fixed pool of worker threads (1) that refuses and counts when full, never waits; a place held inside the transaction and the email published only after COMMIT (refusal → `notificationFailed: true`, rollback never emailed); retry policy, sender timeout, drain with a time limit on Ctrl+C/SIGTERM that names whoever is owed; GET /stats + 5 queue counters, contract 1.3.0; `tools/burst.py` run for real; `docs/queue-trace.md`; ADR-004; 7th border contract + "only the queue starts threads") | [practices/P10-bounded-async-processing](practices/P10-bounded-async-processing) | Done (19 unittest / 540 total tests, 7 contracts kept; booking 1.04 s → p50 3.4 ms with a 1 s mail server; burst of 30: 11 accepted / 19 refused and counted, all 30 booked; drain 10 of 10 on Ctrl+C and SIGTERM; P09 race 0 of 20 on SQLite and PostgreSQL 16; Docker/psycopg run on the Mac, commit and pair work: to do by the student) |

## AI assistance

This portfolio was drafted with the help of an AI assistant (Claude by Anthropic), in line with the course's guidance on using AI tools (L01/P01). Every test, run and measurement reported as **Observed** was actually executed, and its real output is kept in the practice's `evidence/` folder. Steps that need me in person (pair work, classmate review, online worksheet submission, runs on my Mac) are marked "to do by the student".

## How to read the evidence

Evidence claims (checks, models and results) carry one of three labels, as agreed in L01/P01:

- **Proposed** — a plan or a check we intend to run. Nothing has been executed.
- **Simulated** — the result of a classroom model or thought experiment, not a running system.
- **Observed** — a result recorded after actually running something, with its environment.

Numeric quality targets that have not been agreed are written as **to agree**. A target is never
reported as met before a test has produced an observed result.
