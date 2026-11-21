# Observed runs — P07

**Label:** Observed — every block below is real output copied from the run (full logs in
[logs/](logs/)). Absolute paths are shortened to `<portfolio>/`, `<project>/`, `<tmp>` or `<scratch>`.
**Environment:** Linux container (kernel 6.18), Python 3.13.18, pytest 9.1.1, mypy (strict),
Starlette 1.7.0, pydantic 2.13.5, uvicorn 0.54.0, SQLite 3.53.1, curl 8.5.0, PostgreSQL 16.15
(server and psql; no Python driver), Docker client + Compose v5.7.1 (no daemon), Mermaid CLI
11.16.0. **Run date:** 2026-11-21 (portfolio build). **Working directory:** `hotel-booking/` unless
stated. My Mac was not used; what only it can run is listed in the README checklist.

## O1 · Start: the P06 safety net

Before any P07 change ([b0-baseline](logs/b0-baseline.txt)):

```text
$ python3 -m pytest -q -p no:cacheprovider
118 passed in 1.79s
$ python3 -m pytest -q -p no:cacheprovider practices/*/checks     # from the portfolio root
49 passed in 0.39s
```

## O2 · Step 1: the estimate

`python3 capacity.py` ([s1-capacity](logs/s1-capacity.txt)) — the course's six lines, then mine:

```text
Searches per day: 1440 visitors x 20 = 28800
Searches per second: average 0.33, peak 3.33 (200 per minute)
Bookings: 20 per day, 0.0023 per second at peak, 1440 searches per booking
Database queries at peak: 3.33 searches/s x 40 rooms = 133.33 per second
Reservation storage: 20 x 365 x 600 bytes = 4.38 MB per year
Bandwidth at peak: search answers 6.67 KB/s, room photos 333.33 KB/s
Database writes at peak: 0.0023 bookings/s x 3 statements = 0.0069 per second
Searches in flight at peak if each took the whole S1 second: 3.33/s x 1 s = 3.33
Storage after 5 years: 4.38 MB x 5 = 21.90 MB
Database queries at peak with 10x visitors: 3.33 x 10 x 40 = 1333.33 per second
```

`tests/test_capacity.py`: 29 passed (part of O10) — the course's numbers, the exact-fraction
arithmetic, every result row of `capacity.md` equal to `capacity.py --table`, the assumptions table
equal to the constants, and the peak equal to `l04-notes.md`. The assumption "one query per room"
counted on real SQL: `test_a_search_asks_the_database_once_per_room[2]` and `[40]` pass (2 and 40
`SELECT EXISTS` statements).

## O3 · Step 2: the compose file

([docker-compose-config](logs/docker-compose-config.txt))

```text
$ docker compose config   # parses and validates docker-compose.yml; needs no daemon
...
    image: postgres:18
    volumes:
      - type: bind
        source: <project>/db/postgres/init.sql
        target: /docker-entrypoint-initdb.d/init.sql
        read_only: true
...
$ docker compose up -d
failed to connect to the docker API at unix:///var/run/docker.sock; check if the path is correct and if the daemon is running: ...
```

## O4 · Step 2 and Step 8: PostgreSQL 16 with psql

A throw-away PostgreSQL 16.15 cluster (initdb, a local socket, user and database `hotel`), then
`python3 -I practices/P07-capacity-api-design/evidence/postgres_sql_check.py hotel-booking -h <socket dir> -p 55432 -U hotel -d hotel`
([postgres-sql-check](logs/postgres-sql-check.txt)). Excerpts (condensed; the `-- request …` comments
and the shortened result tables are mine, the full output is in the log):

```text
\i <project>/db/postgres/init.sql
CREATE TABLE
CREATE TABLE
CREATE INDEX
INSERT 0 2
INSERT INTO reservations VALUES ('R101', 'Omar', 'omar@example.com', 'R7', '2026-11-12', '2026-11-14', 'Confirmed');
ERROR:  duplicate key value violates unique constraint "reservations_pkey"
DETAIL:  Key (id)=(R101) already exists.
INSERT INTO reservations VALUES ('R102', 'Omar', 'omar@example.com', 'R8', '2026-11-15', '2026-11-15', 'Confirmed');
ERROR:  new row for relation "reservations" violates check constraint "reservations_check"
PREPARE has_overlap AS SELECT EXISTS (SELECT 1 FROM reservations WHERE room = $1 AND status = 'Confirmed' AND check_in < $2 AND $3 < check_out);
...
EXECUTE has_overlap('R7', '2026-11-15', '2026-11-13');      -- request 3: Omar's 13-15 Nov
 t
EXECUTE update_status('Cancelled', 'R101');                  -- request 6
UPDATE 1
SELECT id, guest_name, room, check_in, check_out, status FROM reservations ORDER BY id;
 R101 | Maya       | R7   | 2026-11-12 | 2026-11-14 | Cancelled
 R102 | Maya       | R7   | 2026-11-12 | 2026-11-14 | Confirmed
EXPLAIN (COSTS OFF) SELECT EXISTS (...)
     ->  Index Only Scan using reservations_confirmed_room_stay on reservations
```

`SELECT * FROM rooms;` on that server ([postgres-rooms](logs/postgres-rooms.txt)): R7 Standard,
R8 Deluxe (2 rows). The cluster was stopped and deleted afterwards.

## O5 · Step 3: the contract, kept true

`tests/test_openapi_contract.py`: 35 passed (part of O10). Six deliberate mismatches on throw-away
copies ([break-the-contract](logs/break-the-contract.txt)):

```text
Unchanged copy: 35 passed in 0.38s
1. code answers a status the contract does not list (UnknownRoom 400 -> 404)        2 failed, 33 passed
2. code serves a route the contract does not have (GET /stats)                       1 failed, 34 passed
3. contract forgets an answer the code gives (POST /reservations 409 removed)        4 failed, 31 passed
4. contract example differs from the real body (detail reworded)                     1 failed, 34 passed
5. contract renames an answer field (notificationFailed -> notificationsFailed)      1 failed, 34 passed
6. code adds an error title the contract's Problem list lacks                        3 failed, 32 passed
Every mutation was caught.
```

(One line per mutation, condensed from the log, which also names every failing check.)

## O6 · Step 6: the API tests, red and green

409 changed to 201 in `test_booking_answers_201_then_409_for_a_shared_night`
([s6-red-409-to-201](logs/s6-red-409-to-201.txt)):

```text
FAIL: test_booking_answers_201_then_409_for_a_shared_night (test_api.ApiTests.test_booking_answers_201_then_409_for_a_shared_night)
AssertionError: 201 != 409
Ran 4 tests in 0.054s
FAILED (failures=1)
```

Changed back — same SHA-256 as before the edit — and the whole unittest run
([s6-green-after-undo](logs/s6-green-after-undo.txt)):

```text
416598d449615929c4bda37040bbf7ea92255d7c2272e51c2c41d8b29d3e4be3  test_api.py
Ran 12 tests in 0.055s
OK
```

## O7 · Step 7: the SQL store, red then green

First run of the shared store suite ([s7-red-unit-of-work](logs/s7-red-unit-of-work.txt)):

```text
E       At index 8 diff: ['R8'] != ['R7', 'R8']
FAILED tests/test_sql_store.py::test_booking_service_gives_the_same_records_on_both_stores[sql]
1 failed, 40 passed in 0.41s
```

Inside one unit of work, after `cancel("R101")`, the SQL store still reported R7 as booked (the
status was written only at commit). After the autoflush fix ([s7-green-unit-of-work](logs/s7-green-unit-of-work.txt)):
`41 passed in 0.49s`.

## O8 · Step 8: the API check against the real server (SQLite)

`python3 -I practices/P07-capacity-api-design/evidence/api_check.py hotel-booking` from the
portfolio root ([api-check-sqlite](logs/api-check-sqlite.txt)): `python main.py --port 5080`
(uvicorn) over an empty database file, every command of `docs/api-check.md` run with curl:

```text
Server started in 0.73 s: python main.py --port 5080
## 2. Maya books R7 for 12–14 Nov
$ curl -s -w "\n%{http_code}\n" -X POST -H "Content-Type: application/json" --data "@docs/requests/maya-r7.json" http://localhost:5080/reservations
{"id":"R101","status":"Confirmed","notificationFailed":false}
201
✓ matches Expected
...
## 9. Stop the app (Ctrl+C in its terminal) and start it again
Server stopped with SIGINT (exit code 0); restarted in 0.30 s over the same database file.
## 10. After the restart, search 12–14 Nov: R7 is still booked
{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R8","type":"Deluxe"}],"next":null}
200
✓ matches Expected
## 11. The reservations table
R101 | Maya | R7 | 2026-11-12 | 2026-11-14 | Cancelled
R102 | Maya | R7 | 2026-11-12 | 2026-11-14 | Confirmed
✓ matches Expected
...
## 21. A method the path does not support (the Allow header names the right one)
HTTP/1.1 405 Method Not Allowed
allow: POST
content-type: application/problem+json
✓ matches Expected
Result: 21 of 21 answers exactly as expected, 1 restart.
---- server log (uvicorn) ----
INFO:     127.0.0.1:46142 - "POST /reservations HTTP/1.1" 201 Created
INFO:     127.0.0.1:46148 - "POST /reservations HTTP/1.1" 409 Conflict
```

## O9 · The old tests after the code change

Right after the P07 code was added, before any test was touched
([b1-old-tests-after-the-code-change](logs/b1-old-tests-after-the-code-change.txt)): 5 failed /
113 passed in hotel-booking (class rule, `main([])`, three UML-conformance checks) and 1 failed in
the P06 document checks (`KeyError: 'api'`). Each was an expected consequence of a deliberate P07
change and was updated with a note in its docstring; the 8 booking tests and the race pins were not
touched.

## O10 · Everything at the end

| Check | Command | Result | Log |
|---|---|---|---|
| Course tests | `python3 -m unittest -v` | `Ran 12 tests … OK` (8 booking + 4 API) | [f-unittest](logs/f-unittest.txt) |
| Borders | `python3 -m tests.test_architecture` | 5 × KEPT, `Contracts: 5 kept, 0 broken.` | [f-contracts](logs/f-contracts.txt) |
| Full suite | `python3 -m pytest -p no:cacheprovider -v` | `335 passed` | [f-pytest](logs/f-pytest.txt) |
| Types | `python3 -m mypy` | `Success: no issues found in 22 source files` | [f-mypy](logs/f-mypy.txt) |
| Demo | `python3 main.py --demo` | the nine lines, `Confirmation emails sent: 2` | [f-demo](logs/f-demo.txt) |
| Race | `python3 main.py --race` | `Confirmed reservations for R7 on 12-14 Nov: 2` — Double booking! | [f-race](logs/f-race.txt) |
| Race over HTTP + SQLite ×20 | the two pinned race tests, 20 runs | `2 passed` in 20 of 20 | [f-race-http-20](logs/f-race-http-20.txt) |
| Document checks | `python3 -m pytest -p no:cacheprovider practices/*/checks` (portfolio root) | `95 passed` (P05 26, P06 26, P07 43) | [f-doc-checks](logs/f-doc-checks.txt) |
| Diagrams | `mmdc -p puppeteer-config.linux-build.json -i X.mmd -o X.svg`, 5 files | 5 × `exit 0` | [mmdc](logs/mmdc.txt) |
| Tools available | imports, `pip download`, versions | no importlinter/psycopg/fastapi/sqlalchemy; PyPI unreachable | [f-tools](logs/f-tools.txt) |

Full suite by file: `test_api.py` 4, `test_booking_service.py` 8, `tests/test_api_http.py` 92,
`test_api_sqlite.py` 8, `test_architecture.py` 18, `test_booking_service.py` (pytest) 14,
`test_capacity.py` 29, `test_demo_and_race.py` 5, `test_dependency_rule.py` 4, `test_domain.py` 17,
`test_modules.py` 13, `test_openapi_contract.py` 35, `test_sequences.py` 6, `test_sql_store.py` 41,
`test_substitution.py` 10, `test_uml_conformance.py` 31 — 335.
