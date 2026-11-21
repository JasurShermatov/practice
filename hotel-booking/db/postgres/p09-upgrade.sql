-- P09: bring a database created by version 5 (P07/P08 init.sql) up to version 6.
-- init.sql runs only when the database is created, so the running database needs the same
-- changes once, by hand:
--
--   docker compose exec -T db psql -U hotel -d hotel -v ON_ERROR_STOP=1 < db/postgres/p09-upgrade.sql
--
-- It runs in one transaction: if the ALTER TABLE is refused, nothing at all has changed.

BEGIN;

-- Step 1: ids from a sequence. Start above the ids that already exist, so it never collides
-- with them (ids are never deleted, so the highest number is the last one handed out).
CREATE SEQUENCE IF NOT EXISTS reservation_ids START 101;
SELECT setval('reservation_ids',
              GREATEST(101, (SELECT coalesce(max(substr(id, 2)::integer), 100) + 1 FROM reservations)),
              false);

-- Step 7: the rule itself. PostgreSQL checks the rows that are already there and refuses the
-- constraint while any room has two Confirmed reservations sharing a night:
--   ERROR:  could not create exclusion constraint "reservations_no_overlap"
-- Find them with db/find-double-bookings.sql, cancel one of each pair, and run this file again.
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE reservations
    ADD CONSTRAINT reservations_no_overlap
    EXCLUDE USING gist (
        room WITH =,
        daterange(check_in, check_out, '[)') WITH &&
    ) WHERE (status = 'Confirmed');

COMMIT;
