# Individual reflection — Jasur Shermatov

**What I produced:** the P04 hotel app moved into four modules (rooms, reservations, payments,
notifications), each a package with a public contract and an `internal.py`; Notifications' own
`Confirmation` message; a Payments contract with a simulated service; `main.py` as the only app
file that names internal code; three border contracts in `.importlinter` and a standard-library
test that enforces them on every test run; the deliberate red/green demonstration of a broken
border; ADR-001; the "Modules" page; and a written architecture review of the result. The app's
behaviour is unchanged: the same 8 tests, the same nine demo lines, the same race.

**What the move taught me:** most of P06 was mechanical, because P05 had already decided where
everything goes — the P05 tables became the folder layout almost one to one. The one change that
was not mechanical was the `Confirmation` message. Passing five plain fields instead of the
`Reservation` looks like a small edit in one line, but it removed a dependency circle and made a
whole class of bugs impossible: in P04 my tests needed a "cancelling sender" to show what a bad
sender could do; in P06 that sender cannot be written any more, because it never receives the
booking. A border is strongest when the type that crosses it carries nothing to misuse.

**What surprised me:** Python itself gave the first red result of the day, before any code moved:
an empty `notifications/` folder next to `notifications.py` broke all 8 tests, because a package
shadows a module of the same name. P05's plan had warned about it, and seeing it happen made me
order the moves more carefully. The second surprise was Step 7: the 8 behaviour tests stayed green
with the forbidden import in place, for all three rules. That is the whole argument for
architecture tests — the app worked, the structure was already broken, and only the import check
noticed.

**Engineering choices I would defend:** I put the three rules in one file (`.importlinter`) and
made my test read that file, so `lint-imports` on my Mac and `pytest` here can never disagree. I
made the checker follow imports transitively (like import-linter) and tested the checker itself on
small fake packages, so a passing run means something. I used `Decimal` for the deposit amount,
because money arithmetic with floats is a bug waiting for P17.

**What is still weak:** the race (S2) is untouched, on purpose — P09's job. The borders are only as
strong as the habit of running the tests; a dynamic import would pass both checkers. And
`BookingService` still receives a list of rooms instead of asking the catalog, which will matter
when a room can go out of service while the app is running.

**To do myself:** install import-linter on my Mac and run `lint-imports`; open
`docs/diagrams.drawio` in draw.io and check the "Modules" page with my partner; do the step-by-step
moves in class with my partner, swapping who types at every step.
