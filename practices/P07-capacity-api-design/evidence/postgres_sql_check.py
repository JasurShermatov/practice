"""Run db/postgres/init.sql and every SQL statement of the SQL store on a real PostgreSQL server, via psql.

    python3 -I practices/P07-capacity-api-design/evidence/postgres_sql_check.py hotel-booking <psql connection args...>

Why: the build container has a PostgreSQL server and psql but no Python driver (psycopg cannot be
installed), so the Python path ``main.py --db postgres`` cannot run here. This script checks the
part that can differ between SQLite and PostgreSQL - the SQL text - on the real server:

1. the schema file docker-compose mounts (db/postgres/init.sql) runs on an empty database;
2. the two rules the database keeps by itself (activity sheet Step 2): a second R101 and a stay
   without a night are refused;
3. the store's statements are taken *from the code* (``hotel_booking.reservations.internal`` and
   ``hotel_booking.rooms.internal``), their ``?`` placeholders turned into PostgreSQL's ``$1..$n``,
   PREPAREd, and EXECUTEd in the order the store issues them for the seven requests of
   docs/api-check.md (search, book, refused booking, search, cancel, cancel again);
4. the overlap question can use the partial index.

psql prints every statement (-a) and its result; the output is the evidence.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def placeholders(sql: str) -> str:
    """'... = ? AND ? < ...' -> '... = $1 AND $2 < ...' (PREPARE's parameter syntax)."""
    parts = sql.split("?")
    return "".join(part + (f"${index}" if index < len(parts) else "") for index, part in enumerate(parts, start=1))


def script(project: Path) -> str:
    sys.path.insert(0, str(project))
    from hotel_booking.reservations import internal as reservations  # noqa: PLC0415
    from hotel_booking.rooms import internal as rooms  # noqa: PLC0415

    prepared = {
        "select_rooms": rooms.SELECT_ROOMS,
        "has_overlap": reservations.HAS_OVERLAP,
        "count_all": reservations.COUNT,
        "count_confirmed": reservations.COUNT_CONFIRMED,
        "insert_reservation": reservations.INSERT,
        "select_by_id": reservations.SELECT_BY_ID,
        "update_status": reservations.UPDATE_STATUS,
    }
    lines = [
        "\\echo '--- 1. the schema docker-compose mounts: db/postgres/init.sql'",
        f"\\i {project / 'db' / 'postgres' / 'init.sql'}",
        "\\d reservations",
        "\\echo '--- 2. the database refuses a wrong row by itself (activity sheet Step 2)'",
        "INSERT INTO reservations VALUES ('R101', 'Maya', 'maya@example.com', 'R7', '2026-11-12', '2026-11-14', 'Confirmed');",
        "INSERT INTO reservations VALUES ('R101', 'Omar', 'omar@example.com', 'R7', '2026-11-12', '2026-11-14', 'Confirmed');",
        "INSERT INTO reservations VALUES ('R102', 'Omar', 'omar@example.com', 'R8', '2026-11-15', '2026-11-15', 'Confirmed');",
        "INSERT INTO reservations VALUES ('R103', 'Omar', 'omar@example.com', 'R8', '2026-11-15', '2026-11-17', 'Pending');",
        "DELETE FROM reservations;",
        "\\echo '--- 3. the store statements, taken from the code, PREPAREd with $n placeholders'",
        *[f"PREPARE {name} AS {placeholders(sql)};" for name, sql in prepared.items()],
        "\\echo '--- request 1: search 12-14 Nov (one overlap question per room)'",
        "EXECUTE select_rooms;",
        "EXECUTE has_overlap('R7', '2026-11-14', '2026-11-12');",
        "EXECUTE has_overlap('R8', '2026-11-14', '2026-11-12');",
        "\\echo '--- request 2: Maya books R7 12-14 Nov (overlap, count for the id, INSERT, COMMIT)'",
        "BEGIN;",
        "EXECUTE has_overlap('R7', '2026-11-14', '2026-11-12');",
        "EXECUTE count_all;",
        "EXECUTE insert_reservation('R101', 'Maya', 'maya@example.com', 'R7', '2026-11-12', '2026-11-14', 'Confirmed');",
        "COMMIT;",
        "\\echo '--- request 3: Omar asks for R7 13-15 Nov -> the overlap question says true (409)'",
        "EXECUTE has_overlap('R7', '2026-11-15', '2026-11-13');",
        "\\echo '--- request 5: search 12-14 Nov again -> R7 true (booked), R8 false (free)'",
        "EXECUTE has_overlap('R7', '2026-11-14', '2026-11-12');",
        "EXECUTE has_overlap('R8', '2026-11-14', '2026-11-12');",
        "\\echo '--- half-open rule: Nora 14-16 Nov does not overlap Maya 12-14'",
        "EXECUTE has_overlap('R7', '2026-11-16', '2026-11-14');",
        "\\echo '--- request 6: cancel R101 (SELECT by id, then UPDATE at the end of the request, COMMIT)'",
        "BEGIN;",
        "EXECUTE select_by_id('R101');",
        "EXECUTE update_status('Cancelled', 'R101');",
        "COMMIT;",
        "\\echo '--- request 7: cancel R101 again -> the row is Cancelled, nothing is written (404)'",
        "EXECUTE select_by_id('R101');",
        "EXECUTE count_confirmed('R7', '2026-11-14', '2026-11-12');",
        "\\echo '--- request 8: Maya books again -> count gives 1, so the id is R102'",
        "EXECUTE count_all;",
        "EXECUTE insert_reservation('R102', 'Maya', 'maya@example.com', 'R7', '2026-11-12', '2026-11-14', 'Confirmed');",
        "SELECT id, guest_name, room, check_in, check_out, status FROM reservations ORDER BY id;",
        "\\echo '--- 4. the overlap question can use the partial index (seq scan disabled: the table is tiny)'",
        "SET enable_seqscan = off;",
        f"EXPLAIN (COSTS OFF) {placeholders(reservations.HAS_OVERLAP).replace('$1', quote('R7')).replace('$2', quote('2026-11-14') + '::date').replace('$3', quote('2026-11-12') + '::date')};",
    ]
    return "\n".join(lines) + "\n"


def quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def main(argv: list[str]) -> int:
    project = Path(argv[0]).resolve()
    psql = ["psql", "-X", "-a", "-v", "ON_ERROR_STOP=0", *argv[1:]]
    # One pipe for both streams, so each ERROR line appears right after the statement that caused it.
    result = subprocess.run(psql, input=script(project), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout.replace(str(project), "<project>"))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
