# Capacity estimate: hotel booking app

These are estimates from assumptions, not measurements. P08 measures the real app.

**Label:** Simulated (arithmetic on written-down assumptions; no program was timed). The numbers
are produced by [`capacity.py`](../capacity.py) (`python capacity.py`, `python capacity.py
--table`), and `tests/test_capacity.py` fails if a number below differs from the program, or if
the peak here differs from the first answer in [l04-notes.md](l04-notes.md).

## Workload model

What the hotel's web app is asked to do, per request type (the three operations of
[openapi.yaml](openapi.yaml)):

| Request | Share | What it costs in the database today |
|---|---|---|
| `GET /rooms/availability` (search) | almost all: 1,440 per booking | one `SELECT EXISTS …` per room on sale (`BookingService.find_free_rooms` asks the store once per room) |
| `POST /reservations` (book) | 20 a day | 3 statements: overlap check, the next id (`nextval` since P09; `count(*)` before), `INSERT`; then `COMMIT` |
| `DELETE /reservations/{id}` (cancel) | rare; not modelled | `SELECT` by id + one `UPDATE` at the end of the request |

Room photos are served with the booking page, not by this API; they are in the bandwidth line
because they share the hotel's connection.

## Assumptions

| Assumption | Value | Reason |
|---|---|---|
| Visitors per day | 1,440 | the booking page today: about one visitor a minute |
| Searches per visitor | 20 | guests try several dates |
| Bookings per day | 20 | 40 rooms, most stays are two nights |
| Peak factor | 10 | Friday evenings and holiday sales |
| Queries per search | 40 | FindFreeRooms asks once per room |
| Bytes per reservation | 600 | one row plus its index entry |
| Search answer | 2 KB | the JSON of one availability page |
| Room photos per visit | 2 MB | ten photos of 200 KB on the booking page |

Added in this portfolio (my assumptions, same status — guesses to check):

| Assumption | Value | Reason |
|---|---|---|
| Statements per booking | 3 | counted in `SqlReservationStore`: overlap, count, insert |
| Time limit per search | 1 s | S1: p95 ≤ 1 second ([quality-scenarios.md](quality-scenarios.md)) |
| Retention | 5 years | reservations are never deleted (history; ids come from the row count) |
| Growth factor | 10 | "what if the hotel's site gets ten times the visitors" |

## Results

Calculations use the unrounded values (0.33 is 0.333…); results are rounded only when printed.

| Number | Calculation | Result |
|---|---|---|
| Searches, average | 1,440 × 20 = 28,800 a day; 28,800 ÷ 86,400 s | 0.33 per second |
| Searches, peak | 0.33 × 10 | 3.33 per second = 200 a minute (S1) |
| Database queries, peak | 3.33 × 40 rooms | 133 per second |
| Storage | 20 bookings × 365 days × 600 bytes | 4.38 MB a year |
| Bandwidth, peak | 3.33 × 2 KB search answers; 0.17 × 2 MB photos | search 6.67 KB/s, photos 333 KB/s |

Further results (portfolio additions):

| Number | Calculation | Result |
|---|---|---|
| Bookings, peak | 20 ÷ 86,400 s × 10 | 0.0023 per second (one every 432 s) |
| Reads per write | 28,800 searches ÷ 20 bookings | 1,440 searches per booking |
| Database writes, peak | 0.0023 × 3 statements | 0.0069 per second |
| Searches in flight, peak | 3.33 per second × 1 s (Little's law, worst S1 case) | 3.33 requests at once |
| Storage, retention | 4.38 MB × 5 years | 21.90 MB |
| Database queries, growth | 3.33 × 10 (visitors) × 40 rooms | 1,333 per second |

## Checked by hand

The same arithmetic as exact fractions, so it can be checked without a calculator:

- 1,440 × 20 = 28,800 searches a day; 28,800 ÷ 86,400 = **1/3** ≈ 0.33 per second.
- Peak: 1/3 × 10 = **10/3** ≈ 3.33 per second; × 60 = **200 a minute** — exactly S1's 200 searches
  in one minute, and the first line of [l04-notes.md](l04-notes.md).
- Database: 10/3 × 40 = **400/3** ≈ 133.3 queries a second.
- Storage: 20 × 365 = 7,300 rows a year; × 600 B = 4,380,000 B = **4.38 MB** (decimal MB).
- Visitors at the peak: 1,440 ÷ 86,400 × 10 = **1/6** ≈ 0.17 per second; × 2,000 KB = **333.3 KB/s**
  of photos, against 10/3 × 2 = **6.67 KB/s** of search answers (photos are 98% of the bytes).
- Bookings at the peak: 20 ÷ 86,400 × 10 = 1/432 per second, i.e. **one every 432 seconds**.
- Little's law (L = λ × W): 10/3 requests a second × 1 s = **3.33** searches in the app at once,
  even if every one took the whole second S1 allows.

## What it means for the design

1. **Reads dominate (1,440 : 1).** 133 of every ~133.34 database statements a second at the peak
   come from searches; bookings add 0.007. So the search is what P08 caches — not the bookings,
   which must always read the database (L04 T12: booking never reads the cache).
2. **The cost of a search grows with the number of rooms**, not only with visitors: one query per
   room. Ten times the visitors means 1,333 queries a second for 40 rooms. One query per search
   (ask for all blocked rooms at once) or a cache are the two ways out; P08 measures which matters.
3. **Concurrency is small.** About 3–4 requests in flight at the worst; one app process (Starlette
   runs blocking database work in a thread pool) is enough for the estimate. Scaling out is not
   needed for load — it is needed for availability later, and it needs the shared database P07
   adds (L04: stateless instances, one shared store).
4. **Storage does not matter** (22 MB in five years); **photos dominate bandwidth** and belong on
   static hosting or a CDN, not in this API.
5. The partial index `reservations_confirmed_room_stay` in `db/postgres/init.sql` serves the
   overlap question, which is asked 133 times a second at the peak.

## Checked against the code (Observed)

- The assumption "one query per room per search" was counted on the real SQL: with SQLite's trace
  hook, a search runs exactly 2 statements for the 2 rooms R7 and R8, and exactly 40 for a 40-room
  catalog (`tests/test_sql_store.py::test_a_search_asks_the_database_once_per_room`).
- The overlap question uses the partial index (`EXPLAIN QUERY PLAN` on SQLite,
  `test_the_overlap_question_uses_the_partial_index`).

## To measure later

- p95 of 1,000 searches for 12–14 Nov, target ≤ 1 s (S1): P08. **Measured in P08:** 1.31 ms
  without a cache, 1.13 ms with the Redis cache (median of 5 runs, SQLite, one client) — S1 met
  for one guest at a time ([cache-experiment.md](cache-experiment.md)).
- Database queries per search (GET /stats): P08. **Measured in P08:** exactly one per room —
  2,000 for 1,000 searches with 2 rooms, 40,000 with 40 rooms — so the assumption "one query per
  room per search" holds; with the cache 2 (and 40) for the same 1,000 searches.
- p95 under the 200-a-minute load with a load-test tool: P23.
- The size of the reservations table against 4.38 MB a year: P24.

If a measurement disagrees with this estimate, the measurement wins and the assumption above is
corrected (L04: an estimate is not a benchmark).
