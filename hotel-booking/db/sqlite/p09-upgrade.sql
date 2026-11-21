-- P09: bring a SQLite file created by version 5 up to version 6 (the triggers and the id table of
-- db/sqlite/init.sql). main.py runs it by itself when it opens a version-5 file - but only after
-- db/find-double-bookings.sql has returned no row, because unlike PostgreSQL's ALTER TABLE a new
-- trigger does not look at the rows already there, and switching the rule on over a double booking
-- would leave the hotel believing a rule that its own data breaks.

CREATE TRIGGER reservations_no_overlap_insert
BEFORE INSERT ON reservations
WHEN NEW.status = 'Confirmed' AND EXISTS (
    SELECT 1 FROM reservations
    WHERE room = NEW.room AND status = 'Confirmed'
      AND check_in < NEW.check_out AND NEW.check_in < check_out)
BEGIN
    SELECT RAISE(ABORT, 'reservations_no_overlap: the room already has a Confirmed reservation for one of these nights');
END;

CREATE TRIGGER reservations_no_overlap_update
BEFORE UPDATE OF room, check_in, check_out, status ON reservations
WHEN NEW.status = 'Confirmed' AND EXISTS (
    SELECT 1 FROM reservations
    WHERE id <> NEW.id AND room = NEW.room AND status = 'Confirmed'
      AND check_in < NEW.check_out AND NEW.check_in < check_out)
BEGIN
    SELECT RAISE(ABORT, 'reservations_no_overlap: the room already has a Confirmed reservation for one of these nights');
END;

CREATE TABLE reservation_ids (
    only_row   integer PRIMARY KEY CHECK (only_row = 1),
    last_value integer NOT NULL
);
-- Start above the ids that already exist (ids are never deleted).
INSERT INTO reservation_ids (only_row, last_value)
SELECT 1, coalesce(max(CAST(substr(id, 2) AS integer)), 100) FROM reservations;
