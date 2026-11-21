-- The hotel booking app's tables (P07). PostgreSQL runs this file once, when the database is first
-- created (docker-compose.yml mounts it into /docker-entrypoint-initdb.d/).
--
-- Rooms owns the rooms table and Reservations owns the reservations table, so there is no foreign key
-- between them: each module keeps its own data (L03, P05 "rows are private").
--
-- Portable on purpose: the SQLite wiring (main.py, the default here and in every test) runs this SAME
-- file, so the two databases cannot drift apart. Differences worth knowing:
--   * date      PostgreSQL stores a real date. SQLite has no date type: the column gets NUMERIC
--               affinity and keeps the ISO text '2026-11-12'; ISO text compares in date order, so
--               check_in < check_out and the overlap query mean the same in both.
--   * CHECK     enforced by both (SQLite since 3.3).
--   * WHERE ... partial index: PostgreSQL and SQLite (since 3.8) both support it.
-- No PostgreSQL-only statement is used in P07. P09 adds one (an exclusion constraint or
-- SELECT ... FOR UPDATE) and documents its SQLite equivalent next to it.

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

-- The search asks "does a Confirmed reservation of this room share a night?" once per room
-- (docs/capacity.md: about 133 times a second at the peak). This index answers it without reading
-- the whole table; Cancelled rows are history and are left out of it.
CREATE INDEX reservations_confirmed_room_stay
    ON reservations (room, check_in, check_out)
    WHERE status = 'Confirmed';

INSERT INTO rooms (number, type) VALUES ('R7', 'Standard'), ('R8', 'Deluxe');
