# Individual reflection — Jasur Shermatov

**What I produced:** the five version-1 requirements with checks and proof lines, the use case,
class, sequence (book, no-availability, cancel, race), activity and state diagrams, and the first
version of the `hotel-booking` Python code that follows the class diagram one to one, with tests
that check the requirements, the message order of the sequence diagrams and the class diagram
itself.

**What the design made clearer:** writing the "Where the methods live" table first meant the code
had almost no decisions left: `overlaps` needs only dates, so it went to `DateRange`; `blocks` needs
status, room and stay, so it went to `Reservation`; `has_overlap` needs all reservations, so it
went to the store. The relationship → requirement table also showed that every line on the class
diagram is there for a requirement — there was nothing to justify an inheritance arrow.

**What surprised me:** keeping the diagram and the code *exactly* equal was harder than drawing
either one. The course diagram leaves out `BookingResult`, `count()` and the creation of the
reservation; the code cannot. Making a test parse the class diagram turned "the UML matches the
code" from a claim into an observed check.

**The bug I now own:** every single-request test passes, yet `--race` double-books R7 in 20 of 20
runs. The cause is check-then-act: `has_overlap` and `save` are two calls with a gap between them.
I pinned this behaviour in a test that P09 will have to change on purpose.

**Open question and next action:** I do not yet know whether a unique constraint alone can express
"no two Confirmed stays of the same room overlap" (it is a range rule, not equality), or whether
the database needs a lock or an exclusion constraint. Next: in P04, put the store and the sender
behind interfaces without changing the nine demo lines; keep this question for P07–P09.
