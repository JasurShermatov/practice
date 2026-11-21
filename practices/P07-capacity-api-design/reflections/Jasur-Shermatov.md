# Individual reflection — Jasur Shermatov

**What I produced:** a capacity estimate for the hotel app that is also a small program, so the
document cannot keep a stale number; an OpenAPI 3.1 contract written before the code; a Starlette
+ pydantic HTTP API in front of the P06 modules, with one error shape for every failure and cursor
paging; a SQL store and catalog behind the same promises as the lists, with a unit of work per
request; a portable schema for SQLite and PostgreSQL with a Docker Compose file for my Mac; and
proof that the running server answers exactly what the contract says, including after a restart.
`BookingService` did not change by a single line.

**What the estimate taught me:** the numbers are tiny — 3.33 searches a second, 22 MB in five
years — and that is the point. Storage and raw request rate will not hurt this app; what grows is
*queries per search*, because the search asks the database once per room. 1,440 reads for every
write tells me where P08's cache goes and why booking must never read from it. Writing the estimate
as a program and testing the document against it costs a few lines, and it means that when P08's
measurement corrects an assumption, every derived number changes with it — none can be forgotten.

**What surprised me:** the most useful red result of the practice came from a test I wrote for a
different reason. I ran one store test suite against both the list store and the new SQL store,
expecting it to pass. It failed: inside one unit of work, after a cancel, the SQL store still
reported the room as booked, because I wrote status changes only at commit time. Through HTTP
nobody would have noticed — each request is its own unit of work — but the two stores no longer
kept the same promise. Autoflush before a query fixed it. Substitutability is not a property you
can see in the code; you have to test it.

The second surprise was the race. I expected the database to stop it; it does not. With a slow
step, both requests check before either saves, and then each numbers its booking *after* the
other's commit, so both succeed as R101 and R102 — a real double booking through SQL. When the
timing is different, both choose R101 and the primary key refuses the second with a 500. One bug,
two symptoms, both pinned for P09.

**Engineering choices I would defend:** contract first, and a test that keeps contract and code
equal in *both* directions — reading the status codes out of the code with `ast` and replaying
every example in the contract against the app. Six deliberate mutations, from either side, were
all caught. Every error, including a wrong method and a crash, uses problem details, because a
client should never have to guess the shape of an error. The endpoint checks only what the domain
cannot know and calls it once; a malformed request never opens a database connection. One schema
file serves both databases so they cannot drift.

**What I could not do here and why:** the build environment had no Docker daemon and no PostgreSQL
driver, so `python main.py --db postgres` has not been run. I ran the schema and every SQL statement
of the store on a real PostgreSQL 16 server through `psql` instead, in the order of the seven
requests, and recorded it — but the full run through Docker and psycopg, the Swagger editor and
the PostgreSQL column of the API check are mine to do on my Mac.

**What I would improve next:** the search's N queries (one `SELECT … room IN (…)` would do), an
idempotency key for POST (a retried booking today answers 409 for the guest's own stay), sending the
confirmation after the commit instead of before it, and the race — which is P09's job, inside
Reservations and the database, not in the API.
