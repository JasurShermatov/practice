-- The hotel booking app's tables for SQLite (P09): the translation of db/postgres/init.sql.
-- main.py runs this file when it opens a database file that has no tables yet (the default wiring
-- and every test). A file made by version 5 gets the P09 parts from db/sqlite/p09-upgrade.sql.
--
-- Same tables, columns, CHECKs, index and rooms as the PostgreSQL file (tests/test_sql_store.py
-- compares them). Two PostgreSQL statements have no SQLite equivalent, so they are translated:
--
--   * EXCLUDE USING gist (the no-overlap rule) -> two triggers that refuse the row. A trigger's
--     "look, then write" is safe in SQLite and ONLY in SQLite-like engines: SQLite lets one
--     connection write at a time, and the trigger runs while its statement holds that write
--     lock, so no other transaction can insert between the trigger's look and the row going in.
--     The same trigger in PostgreSQL (many writers, Read Committed) would NOT be safe: two
--     transactions would each look, see nothing committed, and both insert. That was run on a
--     real PostgreSQL 16 in P09 (practices/P09-protect-the-last-seat/evidence) - hence the
--     exclusion constraint there.
--   * CREATE SEQUENCE -> a one-row table. UPDATE ... RETURNING takes the write lock, so two
--     requests cannot read the same number. Unlike nextval it rolls back with its transaction
--     (a rolled-back number is reused; it was never saved, so no id is ever given twice).
--
-- Dates are ISO text ('2026-11-12'): SQLite has no date type, and ISO text compares in date order,
-- so CHECK (check_out > check_in) and the overlap test mean the same as in PostgreSQL.

CREATE TABLE rooms (
    number text PRIMARY KEY,          -- R7, R8: no room twice
    type   text NOT NULL              -- catalog data (Standard, Deluxe ...), not a fixed list
);

CREATE TABLE reservations (
    id          text PRIMARY KEY,     -- R101, R102 ...: a second R101 is refused
    guest_name  text NOT NULL,
    guest_email text NOT NULL,
    room        text NOT NULL,        -- a room number; no foreign key (Rooms owns rooms)
    check_in    date NOT NULL,
    check_out   date NOT NULL,        -- half-open stay: the check-out night is not booked
    status      text NOT NULL CHECK (status IN ('Confirmed', 'Cancelled')),
    CHECK (check_out > check_in)      -- a stay has at least one night (the database's own safety net)
);

-- The search's overlap question, without reading the whole table (identical in PostgreSQL).
CREATE INDEX reservations_confirmed_room_stay
    ON reservations (room, check_in, check_out)
    WHERE status = 'Confirmed';

-- P09 Step 7, SQLite's version of the exclusion constraint reservations_no_overlap: a new or
-- changed Confirmed row may not share a night with another Confirmed row of the same room.
-- The message starts with the constraint's name: the store recognises exactly that refusal.
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

-- P09 Step 1, SQLite's version of CREATE SEQUENCE reservation_ids START 101: the last number
-- handed out. The CHECK keeps it to one row.
CREATE TABLE reservation_ids (
    only_row   integer PRIMARY KEY CHECK (only_row = 1),
    last_value integer NOT NULL
);
INSERT INTO reservation_ids (only_row, last_value) VALUES (1, 100);

INSERT INTO rooms (number, type) VALUES ('R7', 'Standard'), ('R8', 'Deluxe');
