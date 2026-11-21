"""P09 Steps 1, 2, 5, 6 and 7 on a real PostgreSQL 16 server: concurrent psql sessions, timed.

    python3 -I practices/P09-protect-the-last-seat/evidence/postgres_repairs.py hotel-booking [--repeat 5]

The course runs these steps by hand in two psql terminals. Here each terminal is a ``psql``
process reading a script; the scripts start at fixed offsets (Maya at 0 s, Omar 0.1 s or 0.5 s
later) and ``pg_sleep`` holds a transaction open where the course says "now switch terminal", so
the interleaving is the one the sheet describes, every time. Every step prints a timestamp taken
by the *server* (``clock_timestamp()``), so the waits are measured by PostgreSQL, not guessed.

Each scenario runs on a fresh, empty ``hotel`` database with the schema it needs:

    ids-from-count        version 5's ids (count(*) + 101) with an uncommitted row: 23505, the P07 500
    ids-from-sequence     Step 1: nextval in two open transactions: two numbers, no wait, no reuse
    race-no-rule          Steps 1-2: init.sql WITHOUT the constraint: the 8-row trace, two Confirmed rows
    repeatable-read       the same race at REPEATABLE READ: still two rows (write skew, not a lost update)
    serializable          the same race at SERIALIZABLE: one transaction is aborted (40001)
    lock-the-reservations SELECT ... FOR UPDATE on the overlapping reservations: no row to lock, two rows
    guard-row             Step 5: FOR UPDATE on a guard row: Omar waits, then sees 1 and refuses
    optimistic-version    Step 6: version check: nobody waits, the loser's UPDATE matches 0 rows, retries, refuses
    trigger-in-postgres   SQLite's trigger, translated to PL/pgSQL: NOT enough here (many writers)
    exclusion-constraint  Step 7: Omar's INSERT waits for Maya's undecided row, then 23P01; savepoint; one row
    switch-on             Step 7.1: db/postgres/p09-upgrade.sql over version-5 data with a double booking:
                          refused; db/find-double-bookings.sql names the pair; cancel R102; accepted
    no-code-path          Step 7: a direct INSERT typed into psql is refused; without btree_gist no constraint

The output (stdout) is the evidence log: each scenario's server timeline, its final table and the
psql transcripts. The cluster is created in a temporary directory and deleted at the end.
"""
from __future__ import annotations

import argparse
import re
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pg_cluster import Cluster, throwaway_cluster  # noqa: E402

STAY = "check_in < '2026-11-14' AND '2026-11-12' < check_out"
OVERLAP = f"(SELECT count(*) FROM reservations WHERE room = 'R7' AND status = 'Confirmed' AND {STAY})"
COLUMNS = "(id, guest_name, guest_email, room, check_in, check_out, status)"
MARK_FUNCTION = """
CREATE FUNCTION mark(who text, what text) RETURNS text LANGUAGE sql VOLATILE AS
$$ SELECT '@@' || to_char(clock_timestamp(), 'HH24:MI:SS.US') || '|' || who || '|' || what $$;
"""
TABLE = "SELECT id, room, check_in, check_out, status FROM reservations ORDER BY id;"


def values(reservation_id: str, guest: str) -> str:
    return f"({reservation_id}, '{guest}', '{guest.lower()}@example.com', 'R7', '2026-11-12', '2026-11-14', 'Confirmed')"


# --------------------------------------------------------------------------- the two terminals' scripts


def booking(who: str, *, begin: str = "BEGIN;", gap: float = 1.0, hold: float = 1.0,
            new_id: str = "'R' || nextval('reservation_ids')", check: str = "plain") -> str:
    """One booking as the app makes it: BEGIN, overlap check, the slow step, INSERT (in a savepoint,
    like the store), the slow email, COMMIT. ``check`` = plain | for-update (lock what the check reads)."""
    check_sql = (f"SELECT mark('{who}', 'overlap check sees ' || {OVERLAP});" if check == "plain" else
                 f"SELECT mark('{who}', 'FOR UPDATE on overlapping reservations locked ' || count(*) || ' rows') FROM "
                 f"(SELECT id FROM reservations WHERE room = 'R7' AND status = 'Confirmed' AND {STAY} FOR UPDATE) AS locked;")
    return f"""
{begin}
SELECT mark('{who}', '{begin.rstrip(';')}');
{check_sql}
SELECT pg_sleep({gap});
SAVEPOINT reservation_insert;
SELECT mark('{who}', 'INSERT asked');
INSERT INTO reservations {COLUMNS} VALUES {values(new_id, who)} RETURNING mark('{who}', 'INSERT ' || id || ' done');
\\if :ERROR
  ROLLBACK TO SAVEPOINT reservation_insert;
  SELECT mark('{who}', 'INSERT refused: ' || :'LAST_ERROR_SQLSTATE' || ' ' || :'LAST_ERROR_MESSAGE');
\\else
  RELEASE SAVEPOINT reservation_insert;
  SELECT pg_sleep({hold});
\\endif
COMMIT;
\\if :ERROR
  SELECT mark('{who}', 'COMMIT failed: ' || :'LAST_ERROR_SQLSTATE' || ' ' || :'LAST_ERROR_MESSAGE');
\\else
  SELECT mark('{who}', 'COMMIT done');
\\endif
"""


def guard_row(who: str, hold: float) -> str:
    """Step 5 (the course's terminals A and B): lock the room's guard row, check, insert only if free."""
    return f"""
BEGIN;
SELECT mark('{who}', 'BEGIN');
SELECT mark('{who}', 'SELECT ... FOR UPDATE asked');
SELECT version FROM room_booking_guard WHERE room = 'R7' FOR UPDATE;
SELECT mark('{who}', 'SELECT ... FOR UPDATE returned: holds the lock on R7');
SELECT ({OVERLAP} = 0) AS free \\gset
SELECT mark('{who}', 'overlap check sees ' || {OVERLAP});
SELECT pg_sleep({hold});
\\if :free
  INSERT INTO reservations {COLUMNS} VALUES {values("'R' || nextval('reservation_ids')", who)} RETURNING mark('{who}', 'INSERT ' || id);
\\else
  SELECT mark('{who}', 'refuses: Unavailable (nothing inserted)');
\\endif
COMMIT;
SELECT mark('{who}', 'COMMIT (lock released)');
"""


def optimistic(who: str, hold: float) -> str:
    """Step 6: read the version without a lock, check, claim the version; on 0 rows roll back and retry."""
    return f"""
BEGIN;
SELECT mark('{who}', 'BEGIN');
SELECT version AS seen FROM room_booking_guard WHERE room = 'R7' \\gset
SELECT mark('{who}', 'reads version = ' || :seen || ' (plain SELECT: no lock, no wait)');
SELECT mark('{who}', 'overlap check sees ' || {OVERLAP});
SELECT pg_sleep({hold});
UPDATE room_booking_guard SET version = version + 1 WHERE room = 'R7' AND version = :seen;
\\set updated :ROW_COUNT
SELECT (:updated = 1) AS claimed \\gset
SELECT mark('{who}', 'UPDATE ... WHERE version = ' || :seen || ' matched ' || :updated || ' row(s)');
\\if :claimed
  INSERT INTO reservations {COLUMNS} VALUES {values("'R' || nextval('reservation_ids')", who)} RETURNING mark('{who}', 'INSERT ' || id);
  COMMIT;
  SELECT mark('{who}', 'COMMIT');
\\else
  ROLLBACK;
  SELECT mark('{who}', 'ROLLBACK, then try again from the start');
  BEGIN;
  SELECT version AS seen FROM room_booking_guard WHERE room = 'R7' \\gset
  SELECT mark('{who}', 'reads version = ' || :seen);
  SELECT ({OVERLAP} = 0) AS free \\gset
  SELECT mark('{who}', 'overlap check sees ' || {OVERLAP});
  \\if :free
    SELECT mark('{who}', 'free after all (not expected here)');
  \\else
    SELECT mark('{who}', 'refuses: Unavailable');
  \\endif
  COMMIT;
\\endif
"""


# --------------------------------------------------------------------------- running two terminals at once


@dataclass
class Terminal:
    who: str
    start_after: float
    script: str
    output: str = ""


def run_terminals(cluster: Cluster, terminals: list[Terminal]) -> None:
    """Start each psql at its offset, all reading their scripts at the same time; wait for all."""
    def run(terminal: Terminal) -> None:
        time.sleep(terminal.start_after)
        done = subprocess.run([*cluster.psql_args, "-q", "-t", "-A", "-a", "-v", "VERBOSITY=terse"],
                              input=terminal.script, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        terminal.output = done.stdout

    threads = [threading.Thread(target=run, args=(terminal,)) for terminal in terminals]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def marks(terminals: list[Terminal]) -> list[tuple[datetime, str, str]]:
    found = []
    for terminal in terminals:
        for line in terminal.output.splitlines():
            if line.startswith("@@"):
                stamp, who, what = line[2:].split("|", 2)
                found.append((datetime.strptime(stamp, "%H:%M:%S.%f"), who, what))
    return sorted(found)


def timeline(terminals: list[Terminal]) -> list[str]:
    found = marks(terminals)
    zero = found[0][0]
    return [f"{(stamp - zero).total_seconds():6.2f}s  {who:5}  {what}" for stamp, who, what in found]


def seconds_between(terminals: list[Terminal], who: str, first: str, then: str) -> float:
    found = [(stamp, what) for stamp, name, what in marks(terminals) if name == who]
    start = next(stamp for stamp, what in found if what.startswith(first))
    end = next(stamp for stamp, what in found if what.startswith(then) and stamp >= start)
    return (end - start).total_seconds()


def table(cluster: Cluster, sql: str = TABLE) -> str:
    return cluster.psql("-c", sql).stdout.rstrip()


# --------------------------------------------------------------------------- schemas


def schema(project: Path, variant: str) -> str:
    """The CREATE statements a scenario starts from."""
    v6 = (project / "db" / "postgres" / "init.sql").read_text(encoding="utf-8")
    without_rule = re.sub(r",\s*(--[^\n]*\n\s*)*CONSTRAINT reservations_no_overlap EXCLUDE USING gist \(.*?\) WHERE \(status = 'Confirmed'\)",
                          "", v6, flags=re.DOTALL)
    without_rule = without_rule.replace("CREATE EXTENSION IF NOT EXISTS btree_gist;", "")  # added with the rule
    assert "EXCLUDE" not in without_rule.split("CREATE INDEX")[0].split("CREATE TABLE reservations")[1]
    if variant == "v6":
        return v6
    if variant == "no-rule":  # the course's state after Step 1 and before Step 7: the sequence, no constraint
        return without_rule
    if variant == "v5":       # what P07/P08 created: no sequence, no constraint
        return re.sub(r"CREATE SEQUENCE reservation_ids START 101;", "", without_rule)
    raise ValueError(variant)


def fresh(cluster: Cluster, project: Path, variant: str, extra: str = "") -> None:
    cluster.recreate_database()
    done = cluster.psql("-q", "-v", "ON_ERROR_STOP=1", input_text=schema(project, variant) + MARK_FUNCTION + extra)
    if done.returncode != 0:
        raise RuntimeError(done.stdout + done.stderr)


GUARD = """
-- P09 Step 5: one row per room for the Reservations module to lock (Reservations owns this table).
CREATE TABLE room_booking_guard (room text PRIMARY KEY, version integer NOT NULL DEFAULT 0);
INSERT INTO room_booking_guard (room) VALUES ('R7'), ('R8');
"""

PLPGSQL_TRIGGER = """
-- SQLite's reservations_no_overlap_insert trigger, translated to PL/pgSQL (for this experiment only).
CREATE FUNCTION refuse_overlap() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status = 'Confirmed' AND EXISTS (
        SELECT 1 FROM reservations WHERE room = NEW.room AND status = 'Confirmed'
          AND check_in < NEW.check_out AND NEW.check_in < check_out) THEN
        RAISE EXCEPTION 'reservations_no_overlap: the room already has a Confirmed reservation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER reservations_no_overlap_insert BEFORE INSERT ON reservations
    FOR EACH ROW EXECUTE FUNCTION refuse_overlap();
"""


# --------------------------------------------------------------------------- the scenarios


def header(title: str) -> None:
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")


def show(terminals: list[Terminal], cluster: Cluster, transcript: bool = True) -> None:
    print("\nBoth terminals, in time order (server clock_timestamp(), relative to the first step):")
    print("\n".join(timeline(terminals)))
    print("\nThe table afterwards:")
    print(table(cluster))
    if transcript:
        for terminal in terminals:
            print(f"\n--- psql transcript: {terminal.who} (statements echoed, results unaligned) ---")
            print("\n".join(line for line in terminal.output.splitlines() if line.strip()))


def race(cluster: Cluster, maya: str, omar: str, omar_after: float = 0.5) -> list[Terminal]:
    terminals = [Terminal("Maya", 0.0, maya), Terminal("Omar", omar_after, omar)]
    run_terminals(cluster, terminals)
    return terminals


def confirmed(cluster: Cluster) -> int:
    return int(cluster.psql("-t", "-A", "-c", "SELECT count(*) FROM reservations WHERE status = 'Confirmed'").stdout)


def run_all(project: Path, cluster: Cluster, repeat: int) -> dict[str, object]:
    results: dict[str, object] = {}
    print(cluster.psql("-t", "-A", "-c", "SELECT version();").stdout.strip())

    header("ids-from-count - version 5's ids (count(*) + 101) while Maya's INSERT is not committed yet")
    fresh(cluster, project, "v5")
    count_id = "'R' || (101 + (SELECT count(*) FROM reservations))"
    terminals = race(cluster, booking("Maya", new_id=count_id), booking("Omar", new_id=count_id))
    show(terminals, cluster)
    results["ids-from-count"] = confirmed(cluster)

    header("ids-from-sequence - Step 1: nextval in two open transactions")
    fresh(cluster, project, "v6")
    seq = [Terminal("Maya", 0.0, "BEGIN;\nSELECT mark('Maya', 'nextval -> ' || nextval('reservation_ids'));\n"
                                 "SELECT pg_sleep(1);\nROLLBACK;\nSELECT mark('Maya', 'ROLLBACK');\n"),
           Terminal("Omar", 0.3, "BEGIN;\nSELECT mark('Omar', 'nextval -> ' || nextval('reservation_ids') || ' (Maya has not committed)');\n"
                                 "COMMIT;\nSELECT pg_sleep(1);\n"
                                 "SELECT mark('Omar', 'after Maya''s ROLLBACK: nextval -> ' || nextval('reservation_ids') || ' (101 is not reused)');\n")]
    run_terminals(cluster, seq)
    print("\n".join(timeline(seq)))

    for title, key, begin, check, extra in (
        ("race-no-rule - Steps 1-2: the app's statements, no rule in the database (init.sql without the constraint)",
         "race-no-rule", "BEGIN;", "plain", ""),
        ("repeatable-read - the same race at REPEATABLE READ", "repeatable-read",
         "BEGIN ISOLATION LEVEL REPEATABLE READ;", "plain", ""),
        ("serializable - the same race at SERIALIZABLE", "serializable", "BEGIN ISOLATION LEVEL SERIALIZABLE;", "plain", ""),
        ("lock-the-reservations - SELECT ... FOR UPDATE on the overlapping reservations (the first repair everybody tries)",
         "lock-the-reservations", "BEGIN;", "for-update", ""),
        ("trigger-in-postgres - SQLite's trigger translated to PL/pgSQL, Read Committed: is a trigger enough here?",
         "trigger-in-postgres", "BEGIN;", "plain", PLPGSQL_TRIGGER),
    ):
        header(title)
        fresh(cluster, project, "no-rule", extra)
        terminals = race(cluster, booking("Maya", begin=begin, check=check), booking("Omar", begin=begin, check=check))
        show(terminals, cluster)
        results[key] = confirmed(cluster)

    header(f"guard-row - Step 5: SELECT ... FOR UPDATE on the room's guard row (Maya holds it 1 s; {repeat} runs)")
    waits = []
    for run in range(repeat):
        fresh(cluster, project, "no-rule", GUARD)
        terminals = race(cluster, guard_row("Maya", 1.0), guard_row("Omar", 0.0), omar_after=0.1)
        waits.append(seconds_between(terminals, "Omar", "SELECT ... FOR UPDATE asked", "SELECT ... FOR UPDATE returned"))
        assert confirmed(cluster) == 1
        if run == 0:
            show(terminals, cluster)
    print(f"\nOmar's wait at FOR UPDATE, {repeat} runs (s): {', '.join(f'{w:.2f}' for w in waits)}; "
          f"median {statistics.median(waits):.2f} s. Confirmed reservations for R7 every run: 1")
    results["guard-row waits"] = waits

    header(f"optimistic-version - Step 6: version check on the guard row, no lock ({repeat} runs)")
    redo = []
    for run in range(repeat):
        fresh(cluster, project, "no-rule", GUARD)
        terminals = race(cluster, optimistic("Maya", 1.0), optimistic("Omar", 0.0), omar_after=0.1)
        assert confirmed(cluster) == 1
        first = seconds_between(terminals, "Maya", "BEGIN", "ROLLBACK")
        redo.append(first)
        if run == 0:
            show(terminals, cluster)
    print(f"\nNobody waited for a lock. Maya's lost attempt took (s, BEGIN -> ROLLBACK, all of it work to redo): "
          f"{', '.join(f'{w:.2f}' for w in redo)}; then she started again. Confirmed reservations for R7 every run: 1")
    results["optimistic redo"] = redo

    header(f"exclusion-constraint - Step 7: the same race as race-no-rule against db/postgres/init.sql ({repeat} runs)")
    constraint_waits = []
    for run in range(repeat):
        fresh(cluster, project, "v6")
        terminals = race(cluster, booking("Maya"), booking("Omar"))
        constraint_waits.append(seconds_between(terminals, "Omar", "INSERT asked", "INSERT refused"))
        assert confirmed(cluster) == 1
        if run == 0:
            show(terminals, cluster)
    print(f"\nOmar's INSERT waited for Maya's undecided row, then was refused (s): "
          f"{', '.join(f'{w:.2f}' for w in constraint_waits)}. Confirmed reservations for R7 every run: 1")
    results["constraint waits"] = constraint_waits

    header("switch-on - Step 7.1: db/postgres/p09-upgrade.sql over version-5 data that holds a double booking")
    fresh(cluster, project, "v5")
    cluster.psql("-q", "-c", f"INSERT INTO reservations {COLUMNS} VALUES {values(chr(39) + 'R101' + chr(39), 'Maya')}, "
                             f"{values(chr(39) + 'R102' + chr(39), 'Omar')};", check=True)
    upgrade, find = "db/postgres/p09-upgrade.sql", "db/find-double-bookings.sql"  # psql runs in the project folder
    for label, args in (
        ("$ psql -f db/find-double-bookings.sql", ["-f", find]),
        ("$ psql -v ON_ERROR_STOP=1 -f db/postgres/p09-upgrade.sql", ["-v", "ON_ERROR_STOP=1", "-f", upgrade]),
        ("$ psql -c \"\\ds\"   # the upgrade ran in one transaction: no sequence was left behind", ["-c", "\\ds"]),
        ("$ psql -c \"UPDATE reservations SET status = 'Cancelled' WHERE id = 'R102';\"   # Step 7.2: a person decides",
         ["-c", "UPDATE reservations SET status = 'Cancelled' WHERE id = 'R102';"]),
        ("$ psql -f db/find-double-bookings.sql", ["-f", find]),
        ("$ psql -v ON_ERROR_STOP=1 -f db/postgres/p09-upgrade.sql", ["-v", "ON_ERROR_STOP=1", "-f", upgrade]),
        ("$ psql -c \"SELECT nextval('reservation_ids');\"   # starts above the ids already used",
         ["-c", "SELECT nextval('reservation_ids');"]),
    ):
        done = cluster.psql(*args, cwd=project)
        print(f"\n{label}\n{(done.stdout + done.stderr).rstrip()}")

    header("no-code-path - Step 7: an INSERT typed straight into psql; and the constraint without btree_gist")
    fresh(cluster, project, "v6")
    cluster.psql("-q", "-c", f"INSERT INTO reservations {COLUMNS} VALUES {values(chr(39) + 'R101' + chr(39), 'Maya')};", check=True)
    for label, sql in (
        ("a direct INSERT for 13-15 Nov", "INSERT INTO reservations (id, guest_name, guest_email, room, check_in, check_out, status) "
         "VALUES ('R999', 'Direct Insert', 'direct@example.com', 'R7', '2026-11-13', '2026-11-15', 'Confirmed');"),
        ("the same stay as Cancelled (blocks nothing)", "INSERT INTO reservations VALUES "
         "('R998', 'Direct Insert', 'direct@example.com', 'R7', '2026-11-13', '2026-11-15', 'Cancelled');"),
        ("turning it back to Confirmed", "UPDATE reservations SET status = 'Confirmed' WHERE id = 'R998';"),
        ("the adjacent stay 14-16 Nov", "INSERT INTO reservations VALUES "
         "('R997', 'Nora', 'nora@example.com', 'R7', '2026-11-14', '2026-11-16', 'Confirmed');"),
    ):
        done = cluster.psql("-v", "VERBOSITY=verbose", "-c", sql)
        print(f"\n-- {label}\n{sql}\n{(done.stdout + done.stderr).rstrip()}")
    print("\n" + table(cluster))
    cluster.recreate_database()
    done = cluster.psql("-c", "CREATE TABLE t (room text, check_in date, check_out date, "
                              "EXCLUDE USING gist (room WITH =, daterange(check_in, check_out, '[)') WITH &&));")
    print(f"\n-- the same constraint in a database without btree_gist\n{(done.stdout + done.stderr).rstrip()}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("--port", type=int, default=55432)
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()
    project = args.project.resolve()
    with throwaway_cluster(args.port) as cluster:
        results = run_all(project, cluster, args.repeat)
    header("summary (confirmed reservations for R7 after each race scenario; waits in seconds)")
    for key, value in results.items():
        print(f"{key:24} {value}")


if __name__ == "__main__":
    main()
