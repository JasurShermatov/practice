# L04 notes

Exit check of lecture L04 (System design: capacity, APIs, caching and scaling), in my own words.
P07 Step 1 starts from answer 1; [capacity.md](capacity.md) must agree with it (checked by
`tests/test_capacity.py`).

1. **Peak: 3.33 searches per second (200 a minute)** = 1,440 visitors × 20 searches ÷ 86,400 seconds
   × a peak factor of 10.
2. **Reservations must live in PostgreSQL before the app can run as two instances**, because each
   instance would otherwise keep its own list: both could accept R7 for the same nights (both even
   as R101); with one shared database every instance sees every booking.
3. **Risk of caching the free-room search: a stale result** — after Maya books R7 a cached search
   can still show R7 as free until the entry expires (e.g. 30 s). The rule that keeps bookings
   correct: booking never reads the cache; `POST /reservations` always checks the database (and a
   booking invalidates the cached searches).
