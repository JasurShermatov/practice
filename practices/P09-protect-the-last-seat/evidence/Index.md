# Evidence index — P09

Labels as agreed in L01/P01: **Proposed** (planned, not run), **Simulated** (model / thought
experiment), **Observed** (actually run; command, environment and real output recorded).
Environment for every Observed row: Linux container, Python 3.13.18, pytest 9, mypy (strict),
Starlette 1.7.0, pydantic 2.13.5, uvicorn 0.54.0, SQLite 3.53.1, **PostgreSQL 16.15 server + psql**
(throw-away cluster on 127.0.0.1, created and deleted by the scripts), redis-server 7.0.15, Mermaid
CLI 11.16.0 with headless Chromium. No Docker daemon, no psycopg ([f-tools](logs/f-tools.txt)).
Portfolio build of 2026-11-21. Outputs: [observed-runs.md](observed-runs.md) and [logs/](logs/).
Scripts: [race_experiment.py](race_experiment.py) (+ [serve.py](serve.py), [pg_wire.py](pg_wire.py),
[pg_cluster.py](pg_cluster.py)), [postgres_repairs.py](postgres_repairs.py), [break_the_fix.py](break_the_fix.py),
[render_diagrams.sh](render_diagrams.sh).

| ID | Label | Requirement | Action | Expected | Actual | Limitation |
|---|---|---|---|---|---|---|
| E1 | **Observed** | §1: P08 checks green before any change; the race still there | version-5 copy: pytest, unittest, contracts, `--race` | 427; 14 OK; 6 kept; 2 Confirmed | as expected ([b0-baseline](logs/b0-baseline.txt)) | — |
| E2 | **Observed** | Old tests after the code change, before touching any | full pytest on the P09 code | some red, each explained | 18 failed / 409 passed; document checks 138 passed ([b1](logs/b1-old-tests-after-the-code-change.txt)); every one changed deliberately (README) | — |
| E3 | **Observed** | Step 1: the race tool against the code before the fix, run for real | `race_experiment.py`: version 5 on SQLite (1 and 2 uvicorn processes), `HOTEL_SLOW_STEP=1`, +0.5 s, 1 + 20 rounds; the table read from the database | 201 + 201, two Confirmed rows | 20 of 20 double-booked in both; R101 + R102 in the table ([race-http-before-after](logs/race-http-before-after.txt)) | SQLite file instead of PostgreSQL 18 in Docker |
| E4 | **Observed** | Step 1 on PostgreSQL: version 6 code against the course's Step-1 database (sequence, no constraint) | the same, two instances on PostgreSQL 16 through `pg_wire` | double booking | 20 of 20 (1 and 2 instances); 84 and 90 of 100 simultaneous pairs | Driver = `pg_wire.py`, not psycopg |
| E5 | **Observed** | Step 1: ids — count vs sequence | `postgres_repairs.py` `ids-from-count`, `ids-from-sequence`; burst runs on version 5 | count: second R101 refused (23505 → 500); nextval: 101, 102, no wait, no reuse | as expected; version 5: 63 and 26 of 100 pairs answered 500 ([postgres-repairs](logs/postgres-repairs.txt)) | — |
| E6 | **Observed** | Step 2: the eight-row trace with real timestamps | `race-no-rule`: two psql sessions, server `clock_timestamp()` | both checks 0, both INSERTs, both COMMITs | 0.00 / 0.50 / 1.00 / 1.50 / 2.01 / 2.51 s; two rows | psql sessions driven by a script, offsets by `pg_sleep` |
| E7 | **Observed** | Step 2: anomaly; isolation levels; FOR UPDATE on reservations | `repeatable-read`, `serializable`, `lock-the-reservations` | RR: 2 rows; Serializable: one aborted; FOR UPDATE: 0 rows locked | as expected: 2 rows / 40001 at COMMIT / "locked 0 rows", 2 rows | — |
| E8 | **Observed** | Steps 3–4: in-process lock, one and two processes | `--race`; `serve.py --app-lock` on 1 and 2 instances, 20 rounds + 100 pairs | 1 instance correct, 2 instances double-booked | `--race`: Omar Unavailable ([f-race](logs/f-race.txt)); web app: 0 of 20 vs 20 of 20 | The lock in the web app is an experiment variant (version 5 + lock), not kept code |
| E9 | **Observed** | Step 5: guard row FOR UPDATE, wait measured | `guard-row`, 5 runs | Omar waits ~1 s, then sees 1 | waits 0.90, 0.91, 0.91, 0.92, 0.90 s (median 0.91); 1 row every run | Maya's 1 s hold is chosen (the course's "a second") |
| E10 | **Observed** | Step 6: optimistic version, no wait, retry | `optimistic-version`, 5 runs | loser's UPDATE 0 rows, ROLLBACK, re-check 1 | as expected; ~1.00 s of thrown-away work; nobody waited; 1 row every run | — |
| E11 | **Observed** | Step 7.1–7.2: constraint refused over dirty data, clean-up, accepted | `switch-on`: `p09-upgrade.sql` on version-5 data with R101 + R102 | `could not create exclusion constraint`; nothing left behind; after cancelling R102: `ALTER TABLE`; nextval 103 | as expected | — |
| E12 | **Observed** | Step 7: the constraint, in psql | `exclusion-constraint` (5 runs), `no-code-path` | Omar 23P01; savepoint keeps his transaction; direct INSERT refused; Cancelled blocks nothing; btree_gist required | as expected; Omar's INSERT waited 0.50 s for Maya's undecided row (5 of 5) | — |
| E13 | **Observed** | Why SQLite's trigger is not PostgreSQL's answer | `trigger-in-postgres` | a trigger at Read Committed lets both in | 2 rows (both INSERTs passed the trigger) | — |
| E14 | **Observed** | Step 7: the race repaired through the app, 1 and 2 instances, SQLite and PostgreSQL | `race_experiment.py` version-6 configurations | one 201 + one 409, one Confirmed row | 0 of 20 double-booked in all four; loser refused by the database in 21 of 21 slow-step rounds | — |
| E15 | **Observed** | S2: 100 simultaneous pairs (no slow step), two instances | burst phase | 0 double bookings | SQLite 100/100 correct; PostgreSQL first run 0 double but 1 / 6 deadlock 500s | Found a real bug (next row) |
| E16 | **Observed** | The deadlock (40P01) between simultaneous conflicting INSERTs, fixed | bounded retry from the savepoint; rerun 300 pairs per configuration | 0 answers other than 201/409 | 300/300 correct, 1 and 2 instances; PostgreSQL logged 15 and 7 deadlocks, all retried ([after-the-retry](logs/race-http-postgres-after-the-retry.txt)) | — |
| E17 | **Observed** | Everything at the end | unittest, pytest, mypy, contracts, demo, document checks | all green | 16 OK; 479 passed; mypy clean; 6 kept ([f-unittest](logs/f-unittest.txt), [f-pytest](logs/f-pytest.txt), [f-mypy](logs/f-mypy.txt), [f-contracts](logs/f-contracts.txt), [f-demo](logs/f-demo.txt), [f-doc-checks](logs/f-doc-checks.txt)) | — |
| E18 | **Observed** | The regression tests really guard the fix | `break_the_fix.py`: 9 mutations on copies | each caught | 9 of 9 caught ([break-the-fix](logs/break-the-fix.txt)) | — |
| E19 | **Observed** | Contract kept equal to the code both ways, 1.2.0, `lostTheRace` from a real race | `tests/test_openapi_contract.py` | green | green (inside E17) | Swagger editor not opened |
| E20 | **Observed** | Diagrams render | `render_diagrams.sh` | 9 × exit 0 | 9 × exit 0 ([mmdc](logs/mmdc.txt)) | — |
| E21 | **Observed** | Race tests are stable | the race/uncommitted tests 20 times | green every time | 20 × "9 passed" ([f-race](logs/f-race.txt)) | Timing-based tests on a 2-vCPU container |
| E22 | **Proposed** | On the Mac with Docker (PostgreSQL 18, Redis 8) and psycopg | `docker compose up -d`; `p09-upgrade.sql` on the P08 volume (refused until the pair is cancelled); `python main.py --db postgres` twice with `HOTEL_SLOW_STEP=1`, `HOTEL_PORT=5081`; `python tools/race_http.py http://localhost:5081`; psql count; direct INSERT | one 201 + one 409; 1 row; 23P01 | Not run — **to do by the student** | — |
| E23 | **Simulated** | How often would two guests really race at the hotel's peak? | P07 capacity: ~20 bookings a day, a check-to-commit window of a few ms without the slow step | a real collision is very rare; the constraint is insurance, not throughput | — | A model; the burst runs (E15) show the window is real when two requests do coincide |
