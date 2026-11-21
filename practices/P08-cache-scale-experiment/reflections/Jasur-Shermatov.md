# Reflection — P08 Cache and scale experiment

Jasur Shermatov · 23-309 SW

**What I expected.** After P07 I was sure the cache would make the search several times faster.
The counts did what I expected: 2,000 database questions became 2 in every single run. The times
did not. With two rooms on a local SQLite file, a search without a cache took 0.92 ms and with
Redis 0.72 ms — about 22 % better, not "several times". A local SQLite query costs microseconds,
while a cache hit still makes two Redis round trips and a thread-pool hop. With 40 rooms the gain
was clear (p95 1.86 → 1.22 ms, 40,000 → 40 queries). So the cache is mainly protection for the
database as the hotel grows, not a latency trick at today's size. I would not have known that
without measuring both rows the same way, several times, interleaved.

**What surprised me.** Two things I only saw because I ran more than the sheet asked. First, the
8-client run produced 8 misses every time: all clients found an empty cache at the same moment and
all asked the database. ADR-002 now names this stampede as a real cost. Second, the hit rate is
not limited only by bookings: the 30-second TTL also ends every copy, so if guests search many
different dates, a copy may serve only a couple of searches. The spread of searched dates is
something to measure in P23, not to guess.

**The correctness cost.** Seeing the stale result with my own `curl` made the cache rule concrete:
the third search still listed R7 after Maya booked it, but Omar got 409 because booking asks the
database. I kept a `--no-invalidation` switch instead of editing the line in and out, so the
experiment can be repeated, and I pinned it as a test. The ordering details matter more than I
thought: raise the version only after the commit, and build the key before reading the database —
one of my mutations moved the INCR before the save and the tests caught it.

**A decision I made differently from the reference.** In the course's version a booking is saved
but answered with an error when Redis is down, and a search fails. I chose fail-open: searches fall
back to the database and bookings are answered 201, with a `cacheErrors` counter and a log line.
I watched it work when I stopped Redis mid-run. The cost is that an outage is quieter, so the
counter must be watched.

**Limits of what I did.** Everything ran in a Linux container on SQLite with Redis 7 on localhost;
I could not run Docker, PostgreSQL through the app, or redis-py there, so I wrote a small Redis
protocol client with the standard library and tested it against a real redis-server. On my Mac I
still have to run the experiment with `docker compose` (PostgreSQL 18 + Redis 8), where I expect the
"No cache" row to be slower and the gain larger, and do the pair work.

**Next.** The bottleneck moved to bookings: 3 exact queries each, which cannot be cached, and two
simultaneous bookings of R7 still both succeed. That is P09.
