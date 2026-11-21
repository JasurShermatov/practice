# Evidence index — P07

Labels as agreed in L01/P01: **Proposed** (planned, not run), **Simulated** (model / thought
experiment), **Observed** (actually run; command, environment and real output recorded).
Environment for every Observed row: Linux container (kernel 6.18), Python 3.13.18, pytest 9.1.1,
mypy (strict), Starlette 1.7.0, pydantic 2.13.5, uvicorn 0.54.0, SQLite 3.53.1, curl 8.5.0,
PostgreSQL 16.15 server + psql (no Python driver), Docker client + Compose v5.7.1 (no daemon),
Mermaid CLI 11.16.0 with headless Chromium; portfolio build of 2026-11-21. Outputs:
[observed-runs.md](observed-runs.md) and [logs/](logs/).

| ID | Label | Requirement | Action | Expected | Actual | Limitation |
|---|---|---|---|---|---|---|
| E1 | **Observed** | Start: P06 checks green before any change | `pytest` in hotel-booking; P05+P06 document checks | 118; 49 | 118 passed; 49 passed ([O1](observed-runs.md#o1--start-the-p06-safety-net)) | Only the summary lines were kept |
| E2 | **Simulated** | Step 1: capacity estimate | Arithmetic on assumptions ([capacity.md](../../../hotel-booking/docs/capacity.md)); exact fractions by hand; `capacity.py` prints the course's six lines | 3.33/s = 200/min, 133 q/s, 4.38 MB/yr, 6.67 KB/s + 333 KB/s | Identical ([O2](observed-runs.md#o2--step-1-the-estimate)) | An estimate, not a measurement: P08 measures |
| E3 | **Observed** | Step 1: the doc's numbers are the program's | `tests/test_capacity.py` (29 checks) | green | green ([O2](observed-runs.md#o2--step-1-the-estimate)) | — |
| E4 | **Observed** | Capacity assumption "one query per room per search" | SQLite trace hook on a real search | 2 for 2 rooms, 40 for 40 | 2 and 40 (`test_a_search_asks_the_database_once_per_room`) | SQLite, not PostgreSQL |
| E5 | **Observed** | Step 2: compose file valid | `docker compose config` | parsed, mount + volume resolved | OK ([docker-compose-config](logs/docker-compose-config.txt)) | `up -d` impossible: no daemon (E17) |
| E6 | **Observed** | Step 2: init.sql on PostgreSQL; R7/R8; the DB refuses wrong rows | `psql` on a PostgreSQL 16.15 server | tables, index, 2 rooms; duplicate key + CHECK errors | As expected ([O4](observed-runs.md#o4--step-2-and-step-8-postgresql-16-with-psql)) | PostgreSQL 16 here, the compose file pins 18 |
| E7 | **Observed** | Step 3: contract == implementation, both directions | `tests/test_openapi_contract.py` (35 checks) | green | green ([O5](observed-runs.md#o5--step-3-the-contract-kept-true)) | Swagger editor not opened (E18) |
| E8 | **Observed** | The contract check can fail | 6 mutations on copies (`break_the_contract.py`) | each one red | 6/6 caught ([break-the-contract](logs/break-the-contract.txt)) | — |
| E9 | **Observed** | Step 7: store SQL on PostgreSQL | `postgres_sql_check.py`: the code's statements PREPAREd/EXECUTEd in the order of the seven requests | the seven answers' data; index used | As expected ([postgres-sql-check](logs/postgres-sql-check.txt)) | Through psql, not psycopg |
| E10 | **Observed** | Steps 4–5, 8: real server, real requests, restart | `api_check.py`: `python main.py` (uvicorn) + curl, every section of api-check.md, SIGINT restart | 21/21 exactly as expected; R7 still booked after restart | 21 of 21, 1 restart ([api-check-sqlite](logs/api-check-sqlite.txt)) | SQLite; PostgreSQL column to do (E16) |
| E11 | **Observed** | Step 6: four API tests; 12 unittest; red when 409 → 201 | `unittest -v`; edit, run, undo | 12 OK; 1 failure; 12 OK, same SHA-256 | As expected ([O6](observed-runs.md#o6--step-6-the-api-tests-red-and-green)) | — |
| E12 | **Observed** | Step 7: SQL store keeps the list store's promise | shared store suite on both stores | green | first **red** (unit-of-work visibility), fixed (autoflush), green ([O7](observed-runs.md#o7--step-7-the-sql-store-red-then-green)) | — |
| E13 | **Observed** | Borders still kept, API edge uses contracts only | `python -m tests.test_architecture` | 5 kept | "Contracts: 5 kept, 0 broken." ([f-contracts](logs/f-contracts.txt)) | `lint-imports` not installable (E17) |
| E14 | **Observed** | Race still there (P09) — console, HTTP+SQLite | `main.py --race`; two pinned HTTP race tests ×20 | 2 Confirmed; 201+201 / 201+500 | As expected, 20/20 ([f-race](logs/f-race.txt), [f-race-http-20](logs/f-race-http-20.txt)) | Timing-based; slow step widens the window |
| E15 | **Observed** | Everything at the end | unittest, pytest, mypy, contracts, demo, race, P05–P07 document checks, mmdc | all green | 12 OK; 335 passed; mypy clean; 95 document checks passed ([O10](observed-runs.md#o10--everything-at-the-end)) | — |
| E16 | **Proposed** | Step 8 on PostgreSQL through the app | On the Mac: `docker compose down -v && up -d`, `pip install "psycopg[binary]"`, `python main.py --db postgres`, run api-check.md, psql table query | Same 21 answers; R101 Cancelled, R102 Confirmed | Not run — **to do by the student** | — |
| E17 | **Observed** | Tool availability (honesty) | `import importlinter/psycopg/fastapi/sqlalchemy`; `pip download`; `docker compose up` | — | none installed; PyPI unreachable; no Docker daemon ([f-tools](logs/f-tools.txt), [docker-compose-config](logs/docker-compose-config.txt)) | Reason for the substitutions |
| E18 | **Proposed** | Step 3: Swagger editor shows no errors; Step 4: contract in the browser | Import docs/openapi.yaml at editor.swagger.io; open http://localhost:5080/openapi.yaml | three operations, no red errors | Not run — **to do by the student** | — |
| E19 | **Proposed** | P08: p95 of 1,000 searches, queries per search | P08 | ≤ 1 s (S1) | — | Out of P07's scope |
