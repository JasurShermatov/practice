# ADR-002: Cache the free-room search in Redis

Status: Accepted (P08). Session: Saturday 7 November 2026. Next to [ADR-001](adr-001-modular-monolith.md).

## Context

- Every search asks the database once per room. Measured: 1,000 searches for one stay cost
  2,000 queries with our two rooms and 40,000 with the 40 rooms of the capacity estimate
  ([cache-experiment.md](cache-experiment.md)); at the estimated peak that is 133 queries a
  second ([capacity.md](capacity.md)).
- A search answer changes only when someone books or cancels. Between two changes the same answer
  is computed again and again (S6: energy per 1,000 searches).
- Searches are already fast enough for S1 here (p95 1.31 ms without a cache, target ≤ 1 s), so
  the reason for a cache is the *load on the database*, which grows with rooms and guests — not
  today's latency.
- The booking rule (S2: never a double booking) must never depend on a copy. A guest may see a
  room a moment too long; a booking may never be decided from a copy (L04 T12).
- The app must stay a stateless modular monolith (ADR-001): any instance can answer any request,
  so the cache must be shared by the instances, not kept inside one of them.

## Decision

1. **Cache-aside, for `GET /rooms/availability` only.** The search looks in the cache first; on a
   miss it asks the database through the unit of work and keeps a copy. `POST /reservations` and
   `DELETE /reservations/{id}` never read the cache — the database is the source of truth.
2. **Key** `availability:v{version}:{checkIn}:{checkOut}` (one copy per stay); **value** the free
   room numbers in text order, such as `R7,R8`; paging (`limit`, `after`) is done on the copy.
3. **TTL 30 seconds** (`SET … EX 30`): the upper bound for any copy that is ever wrong.
4. **Invalidation by version:** after a booking or cancel has been *committed*, the app runs
   `INCR availability:version`. Every key built afterwards is new, so no older copy is read again;
   the old copies expire by themselves. The key is built *before* the database is asked, so an
   answer read just before a booking is stored under the old, unreachable version.
5. **Where it sits:** at the HTTP edge (`hotel_booking/api_cache.py` + the Redis adapter
   `api_redis.py`), outside the four modules. The cache stores text and imports no module (a sixth
   border contract in `.importlinter`); no module imports the cache. `BookingService` did not change.
6. **Redis** (`redis:8` in `docker-compose.yml`, no volume) as the shared store; the app connects at
   start-up and refuses to start if Redis does not answer `PING` (a wrong configuration should be
   loud). `--cache memory` (one process) and `--cache off` exist for experiments and laptops.
7. **A failing cache never fails a request** (my change to the course's reference): while Redis
   does not answer, a search is answered from the database (`X-Cache: bypass`), a booking or cancel
   is answered as saved, and `cacheErrors` in `GET /stats` and the app log show it. Every Redis
   command has a 0.5 s timeout.

## Alternatives considered

- **No cache.** Always fresh, nothing more to run. But every search costs one query per room, and
  that cost grows with the hotel (1.51 ms and 40 queries per search with 40 rooms, measured).
- **TTL only.** Simplest cache. But after a booking the search shows the booked room for up to
  30 seconds — seen for real in Step 5 (R7 listed after Maya booked it).
- **Invalidation only (no TTL).** Fresh after every change, but one missed invalidation (Redis
  briefly unreachable, a crash between the commit and the INCR, a code path that forgets it) keeps
  a wrong copy until Redis restarts.
- **Delete exactly the affected keys.** Precise, but a booking for 12–14 Nov affects every cached
  stay that shares a night with it; finding them needs a scan or an index of keys. One version
  number makes them all unreachable at once.
- **A cache inside each app instance** (`--cache memory`). Fastest in the measurement (0.57 ms
  against 0.72 ms), but each instance would have its own copies and its own version: a booking
  handled by instance A would not invalidate instance B. Kept only as a single-process option.
- **Course reference: fail when Redis is down.** Simple and honest, but a guest whose booking was
  saved would get an error, retry, and receive 409 for her own room (POST is not idempotent until
  P11). I preferred answering from the database and relying on the TTL.

## Consequences

+ 1,000 searches for the same stay cost **2 database queries instead of 2,000** (40 instead of
  40,000 with 40 rooms) — measured, every run.
+ The average search got faster by about 22 % with two rooms and 41 % with 40; CPU per 1,000
  searches fell by 14 % and 40 % (cache-experiment.md).
+ If an invalidation is ever missed, a copy is wrong for **at most 30 seconds**; it can mislead a
  search, never a booking (Step 5: Omar got 409).
+ Redis going down slows searches back to "no cache" but answers every request (observed in Step 8).
- Every booking empties every cached search. In a busy sale the hit rate falls: one miss per
  booking (measured: 20 bookings in 1,000 searches → 98 % hits).
- **Stampede:** several misses at the same moment all ask the database (8 clients → 8 misses, 16
  queries, measured). Nothing prevents it yet.
- **Hot key:** in December one key (`…:2026-12-31:2027-01-02`) answers almost every search; with
  several Redis servers it still lives on one.
- A tiny stale window remains between the commit and the INCR (a search in between can still hit
  the old copy). If the INCR fails, the window is up to 30 s. If Redis restarts or evicts the
  version key, the version starts at 0 again — harmless after a restart (the copies are gone too),
  bounded by the TTL after an eviction.
- Redis is one more program to run and to watch; a fail-open cache can hide an outage, so
  `cacheErrors` and the log lines must be looked at (monitoring arrives later in the course).
- The same search now has two code paths (hit and miss); both are tested, and the answer is the
  same byte for byte.

## Revisit when

- Bookings, not searches, limit the app — that is already the case after this decision (P09 makes
  the booking itself safe under concurrency).
- The hit rate measured under real load (P23) is much lower than in cache-experiment.md, or the
  stampede after an invalidation shows up in the database's load.
- The hotel runs more than one app instance or more than one Redis server (hot key, failover).
- Measured on PostgreSQL in Docker on the Mac, the numbers change the trade-off (the gain should
  grow; to be confirmed).
