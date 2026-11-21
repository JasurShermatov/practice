# L05 notes

Exit check of lecture L05 (Application concurrency and database correctness), in my own words,
applied to the hotel. The L05 case is a lab with 20 seats and 19 accepted bookings where two
students ask for the last seat; the hotel's "last seat" is R7 for 12–14 November. P09 starts by
re-reading these three answers ("the repair you chose there is the one Step 7 builds").

1. **Invariant and what breaks it.** A room never has two Confirmed reservations covering the
   same night (R3). `BookingService.reserve` checks (`has_overlap`) and then saves; two requests
   can both check before either saves, both read "free" and both insert a *different* row. That is
   write skew, not a lost update: nothing either request read was overwritten, so Repeatable Read
   does not stop it; Serializable would, by aborting one of them.
2. **Mechanism and boundary.** Put the rule where every writer must pass: in the database, as a
   constraint on the `reservations` table (PostgreSQL: an exclusion constraint on room + date
   range for Confirmed rows). The store translates that one refusal into the same Unavailable the
   pre-check gives, so the guest sees 409, never a database error. A lock inside the app is not
   enough: it protects one process, and `docs/capacity.md` already plans for a second instance.
   The id must come from the database too (a sequence), or two requests can both count 0 rows and
   both call their booking R101.
3. **Limitation and evidence.** The constraint covers a rule that fits inside one table; a rule that
   spans tables (later: payments) needs a lock row or Serializable. It cannot be switched on while
   the data already breaks it. Evidence planned (Proposed at L05, Observed in P09): the race tool
   before and after the change (one 201 + one 409, one row in the table), the same with two
   instances, a direct `INSERT` in psql refused, and two tests that keep it true.
