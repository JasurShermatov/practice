-- The hotel booking app's tables (P07, P09). PostgreSQL runs this file once, when the database is
-- first created (docker-compose.yml mounts it into /docker-entrypoint-initdb.d/). A database that
-- already exists gets the P09 changes from db/postgres/p09-upgrade.sql instead.
--
-- Rooms owns the rooms table and Reservations owns the reservations table, so there is no foreign key
-- between them: each module keeps its own data (L03, P05 "rows are private").
--
-- P07 kept this file portable and SQLite ran it too. P09 adds two statements SQLite does not have
-- (an exclusion constraint and a sequence), so SQLite now runs its own translation,
-- db/sqlite/init.sql. tests/test_sql_store.py checks that the two files declare the same tables,
-- columns, CHECKs, index and rooms, and that each PostgreSQL-only statement has its SQLite
-- counterpart:
--
--   PostgreSQL (this file)                          SQLite (db/sqlite/init.sql)
--   ----------------------------------------------  -------------------------------------------------
--   EXCLUDE USING gist ... reservations_no_overlap   BEFORE INSERT / BEFORE UPDATE triggers named
--     (checked by the index as the row goes in,        reservations_no_overlap_* that RAISE(ABORT);
--     whatever the other transactions are doing)       atomic only because SQLite has ONE writer at a time
--   CREATE SEQUENCE reservation_ids                  a one-row table reservation_ids(last_value),
--     nextval: never the same number twice, does       UPDATE ... RETURNING under the write lock;
--     not wait, does not roll back                     rolls back with its transaction
--   date                                             ISO text '2026-11-12' (compares in date order)

-- P09 Step 7: the overlap rule, enforced by PostgreSQL itself.
-- btree_gist lets one GiST index hold plain equality (room WITH =) next to a range test
-- (daterange WITH &&). Without it PostgreSQL refuses the constraint:
--   ERROR: data type text has no default operator class for access method "gist"
CREATE EXTENSION IF NOT EXISTS btree_gist;

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
    CHECK (check_out > check_in),     -- a stay has at least one night (the database's own safety net)

    -- R3, kept by the database (P09, docs/adr-003-booking-concurrency.md): no two Confirmed
    -- reservations of the same room may share a night. '[)' = half-open, like DateRange: a stay
    -- ending on the 14th and one starting on the 14th do not overlap. Cancelled rows are history
    -- and block nothing (the WHERE). Named on purpose: the store recognises exactly this name.
    CONSTRAINT reservations_no_overlap EXCLUDE USING gist (
        room WITH =,
        daterange(check_in, check_out, '[)') WITH &&
    ) WHERE (status = 'Confirmed')
);

-- The search asks "does a Confirmed reservation of this room share a night?" once per room
-- (docs/capacity.md: about 133 times a second at the peak). This index answers it without reading
-- the whole table; Cancelled rows are history and are left out of it.
CREATE INDEX reservations_confirmed_room_stay
    ON reservations (room, check_in, check_out)
    WHERE status = 'Confirmed';

-- P09 Step 1: reservation ids come from here, not from counting the rows.
-- nextval never returns the same number twice, even to two transactions running at the same moment.
CREATE SEQUENCE reservation_ids START 101;

INSERT INTO rooms (number, type) VALUES ('R7', 'Standard'), ('R8', 'Deluxe');
