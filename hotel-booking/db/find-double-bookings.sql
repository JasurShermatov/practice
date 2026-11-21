-- Every pair of Confirmed reservations that share a night of the same room (P09 Step 7.1).
-- Portable: psql and sqlite3 both run it. Before the no-overlap rule can be switched on over an
-- existing database this must return no row - PostgreSQL refuses ALTER TABLE ... EXCLUDE while
-- such a pair exists, and main.py refuses to upgrade a version-5 SQLite file for the same reason.
-- A pair is fixed by a person, not by a script: cancel one of the two (a real hotel would phone
-- one of the guests), e.g.  UPDATE reservations SET status = 'Cancelled' WHERE id = 'R102';
SELECT earlier.id AS first_id, later.id AS second_id, earlier.room,
       earlier.check_in AS first_check_in, earlier.check_out AS first_check_out,
       later.check_in AS second_check_in, later.check_out AS second_check_out
FROM reservations AS earlier
JOIN reservations AS later
  ON later.room = earlier.room AND earlier.id < later.id
 AND earlier.status = 'Confirmed' AND later.status = 'Confirmed'
 AND earlier.check_in < later.check_out AND later.check_in < earlier.check_out
ORDER BY earlier.id, later.id;
