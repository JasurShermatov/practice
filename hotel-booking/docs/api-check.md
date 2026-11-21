# API check: the seven requests, the restart, and every error path

The answers the running app must give, request by request. Expected bodies are exactly the
contract's examples ([openapi.yaml](openapi.yaml)). On macOS and Linux the command is `curl`; on
Windows type `curl.exe`. `-s` hides the progress bar and `-w` prints the status code after the
body (a 204 has no body: an empty line, then 204).

Start from an empty database, then start the app in a second terminal, in the `hotel-booking` folder:

```text
SQLite (default):     rm -f hotel.sqlite3 && python main.py
PostgreSQL (Docker):  docker compose down -v && docker compose up -d && python main.py --db postgres
```

Write ✓ after a request when the answer is exactly the expected one. The SQLite column was filled
by running this file with `practices/P07-capacity-api-design/evidence/api_check.py`, which starts
`python main.py` (uvicorn), runs every command below with `curl` and compares the output with the
Expected block (**Observed**, log: `practices/P07-capacity-api-design/evidence/logs/api-check-sqlite.txt`).
The PostgreSQL column is **to do by the student** on the Mac (Docker and psycopg).

## 1. Search 12–14 Nov: R7 and R8 are free

```text
curl -s -w "\n%{http_code}\n" "http://localhost:5080/rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14"
```

Expected:

```text
{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R7","type":"Standard"},{"number":"R8","type":"Deluxe"}],"next":null}
200
```

SQLite: ✓ · PostgreSQL: ☐

## 2. Maya books R7 for 12–14 Nov

```text
curl -s -w "\n%{http_code}\n" -X POST -H "Content-Type: application/json" --data "@docs/requests/maya-r7.json" http://localhost:5080/reservations
```

Expected:

```text
{"id":"R101","status":"Confirmed","notificationFailed":false}
201
```

SQLite: ✓ · PostgreSQL: ☐

## 3. Omar asks for R7 for 13–15 Nov: the night of the 13th is Maya’s

```text
curl -s -w "\n%{http_code}\n" -X POST -H "Content-Type: application/json" --data "@docs/requests/omar-r7.json" http://localhost:5080/reservations
```

Expected:

```text
{"title":"Unavailable","status":409,"detail":"The room is booked for at least one night of this stay."}
409
```

SQLite: ✓ · PostgreSQL: ☐

## 4. Omar asks for R8 for 15–15 Nov: no night at all

```text
curl -s -w "\n%{http_code}\n" -X POST -H "Content-Type: application/json" --data "@docs/requests/omar-r8.json" http://localhost:5080/reservations
```

Expected:

```text
{"title":"InvalidDates","status":400,"detail":"checkOut must be after checkIn."}
400
```

SQLite: ✓ · PostgreSQL: ☐

## 5. Search 12–14 Nov again: only R8 is free

```text
curl -s -w "\n%{http_code}\n" "http://localhost:5080/rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14"
```

Expected:

```text
{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R8","type":"Deluxe"}],"next":null}
200
```

SQLite: ✓ · PostgreSQL: ☐

## 6. Cancel R101

```text
curl -s -w "\n%{http_code}\n" -X DELETE http://localhost:5080/reservations/R101
```

Expected:

```text

204
```

SQLite: ✓ · PostgreSQL: ☐

## 7. Cancel R101 a second time

```text
curl -s -w "\n%{http_code}\n" -X DELETE http://localhost:5080/reservations/R101
```

Expected:

```text
{"title":"NotFound","status":404,"detail":"There is no confirmed reservation R101."}
404
```

SQLite: ✓ · PostgreSQL: ☐

## Restart check: the booking survives

## 8. Maya books R7 for 12–14 Nov again

```text
curl -s -w "\n%{http_code}\n" -X POST -H "Content-Type: application/json" --data "@docs/requests/maya-r7.json" http://localhost:5080/reservations
```

Expected:

```text
{"id":"R102","status":"Confirmed","notificationFailed":false}
201
```

SQLite: ✓ · PostgreSQL: ☐

## 9. Stop the app (Ctrl+C in its terminal) and start it again

Same command as at the start, without deleting the database.

## 10. After the restart, search 12–14 Nov: R7 is still booked

```text
curl -s -w "\n%{http_code}\n" "http://localhost:5080/rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14"
```

Expected:

```text
{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R8","type":"Deluxe"}],"next":null}
200
```

SQLite: ✓ · PostgreSQL: ☐

R7 is still booked after the restart: the reservation lives in the database, not in the app's memory.

## 11. The reservations table

```text
python3 -c "import sqlite3; [print(*row, sep=' | ') for row in sqlite3.connect('hotel.sqlite3').execute('SELECT id, guest_name, room, check_in, check_out, status FROM reservations ORDER BY id')]"
```

Expected:

```text
R101 | Maya | R7 | 2026-11-12 | 2026-11-14 | Cancelled
R102 | Maya | R7 | 2026-11-12 | 2026-11-14 | Confirmed
```

SQLite: ✓ · PostgreSQL: ☐ — on PostgreSQL the same question is
`docker compose exec db psql -U hotel -d hotel -c "SELECT id, guest_name, room, check_in, check_out, status FROM reservations ORDER BY id;"`
(two rows: R101 Cancelled, R102 Confirmed).

## Every other error path

## 12. A room the hotel does not have

```text
curl -s -w "\n%{http_code}\n" -X POST -H "Content-Type: application/json" --data "@docs/requests/nora-r99.json" http://localhost:5080/reservations
```

Expected:

```text
{"title":"UnknownRoom","status":400,"detail":"There is no room R99."}
400
```

SQLite: ✓ · PostgreSQL: ☐

## 13. A body without guestEmail

```text
curl -s -w "\n%{http_code}\n" -X POST -H "Content-Type: application/json" --data "@docs/requests/maya-no-email.json" http://localhost:5080/reservations
```

Expected:

```text
{"title":"InvalidRequest","status":400,"detail":"The body must be JSON with guestName, guestEmail, room, checkIn and checkOut."}
400
```

SQLite: ✓ · PostgreSQL: ☐

## 14. The right body, not sent as JSON

```text
curl -s -w "\n%{http_code}\n" -X POST -H "Content-Type: text/plain" --data "@docs/requests/maya-r7.json" http://localhost:5080/reservations
```

Expected:

```text
{"title":"InvalidRequest","status":400,"detail":"The body must be JSON with guestName, guestEmail, room, checkIn and checkOut."}
400
```

SQLite: ✓ · PostgreSQL: ☐

## 15. Dates written the wrong way

```text
curl -s -w "\n%{http_code}\n" -X POST -H "Content-Type: application/json" --data "@docs/requests/maya-bad-date.json" http://localhost:5080/reservations
```

Expected:

```text
{"title":"InvalidDates","status":400,"detail":"checkIn and checkOut must be dates such as 2026-11-12."}
400
```

SQLite: ✓ · PostgreSQL: ☐

## 16. A search without a check-out date

```text
curl -s -w "\n%{http_code}\n" "http://localhost:5080/rooms/availability?checkIn=2026-11-12"
```

Expected:

```text
{"title":"InvalidDates","status":400,"detail":"checkIn and checkOut must be dates such as 2026-11-12."}
400
```

SQLite: ✓ · PostgreSQL: ☐

## 17. Pages of one room (20–22 Nov, both rooms free): limit=1 gives R7 and "next":"R7"

```text
curl -s -w "\n%{http_code}\n" "http://localhost:5080/rooms/availability?checkIn=2026-11-20&checkOut=2026-11-22&limit=1"
```

Expected:

```text
{"checkIn":"2026-11-20","checkOut":"2026-11-22","rooms":[{"number":"R7","type":"Standard"}],"next":"R7"}
200
```

SQLite: ✓ · PostgreSQL: ☐

## 18. The next page: after=R7

```text
curl -s -w "\n%{http_code}\n" "http://localhost:5080/rooms/availability?checkIn=2026-11-20&checkOut=2026-11-22&limit=1&after=R7"
```

Expected:

```text
{"checkIn":"2026-11-20","checkOut":"2026-11-22","rooms":[{"number":"R8","type":"Deluxe"}],"next":null}
200
```

SQLite: ✓ · PostgreSQL: ☐

## 19. A limit outside 1–100

```text
curl -s -w "\n%{http_code}\n" "http://localhost:5080/rooms/availability?checkIn=2026-11-20&checkOut=2026-11-22&limit=0"
```

Expected:

```text
{"title":"InvalidRequest","status":400,"detail":"limit must be a whole number from 1 to 100."}
400
```

SQLite: ✓ · PostgreSQL: ☐

## 20. A path the API does not have

```text
curl -s -w "\n%{http_code}\n" http://localhost:5080/bookings
```

Expected:

```text
{"title":"NotFound","status":404,"detail":"There is no resource at /bookings."}
404
```

SQLite: ✓ · PostgreSQL: ☐

## 21. A method the path does not support (the Allow header names the right one)

```text
curl -s -D - -o /dev/null -X PUT http://localhost:5080/reservations | grep -i -E "^(HTTP|allow|content-type)" | tr -d "\r"
```

Expected:

```text
HTTP/1.1 405 Method Not Allowed
allow: POST
content-type: application/problem+json
```

SQLite: ✓ · PostgreSQL: ☐

## 22. The contract, from the running app

```text
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" http://localhost:5080/openapi.yaml
```

Expected:

```text
200 application/yaml
```

SQLite: ✓ · PostgreSQL: ☐
