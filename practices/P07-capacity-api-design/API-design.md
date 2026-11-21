# API design — hotel booking app (P07 studio)

The design behind [docs/openapi.yaml](../../hotel-booking/docs/openapi.yaml), with the choices,
the alternatives I rejected and why. L04 T11 gave the rules (resources, methods, status codes,
one error shape, pages, never break a client); this page applies them to the hotel and records
what the code actually does. Every statement about behaviour below is checked by a test (named
in brackets) — **Observed** unless marked otherwise.

## 1. Resources and operations

The hotel's API has two resources. Each BookingService method becomes exactly one operation;
the endpoint only translates HTTP in and out.

| Resource | Path | Method | Calls | Success | Errors |
|---|---|---|---|---|---|
| Availability of rooms for a stay (computed, read-only) | `/rooms/availability?checkIn&checkOut[&limit&after]` | GET | `find_free_rooms` | 200 page of rooms + `next` | 400 InvalidDates · 400 InvalidRequest |
| Reservations (collection) | `/reservations` | POST | `reserve` | 201 `{id, status, notificationFailed}` | 400 InvalidRequest · 400 InvalidDates · 400 UnknownRoom · 409 Unavailable |
| One reservation | `/reservations/{id}` | DELETE | `cancel` | 204, no body | 404 NotFound |
| The contract itself | `/openapi.yaml` | GET | — | 200 `application/yaml` | — |

Any path: 404 NotFound (no such path), 405 MethodNotAllowed with `Allow`, and on the three
booking operations 500 InternalError (the unit of work failed and was rolled back).

**Why `/rooms/availability` and not `/rooms?free=…`:** availability is not a property of a room
but of a room *for a stay*; the stay is required input. A separate sub-resource makes the two
required query parameters natural and keeps `/rooms` free for the catalog later.

**Why DELETE for cancel, although nothing is deleted:** for the client the reservation is gone
(the nights are free); the server keeps the row as Cancelled history. The alternative,
`PATCH /reservations/R101 {"status":"Cancelled"}`, exposes the status machine to clients and
invites `{"status":"Confirmed"}` (un-cancel), which the domain does not allow. Rejected.

## 2. Methods and repeating a request (idempotency)

| Method | Safe | Idempotent | What a repeat does here | Check |
|---|---|---|---|---|
| GET availability | yes | yes | the same answer, nothing changes | `test_get_is_safe_repeating_it_changes_nothing` |
| DELETE reservation | no | **yes** | 204, then 404 NotFound — the reservation is cancelled once, history kept | `test_delete_is_idempotent_the_repeat_answers_404_and_changes_nothing` |
| POST reservation | no | **no** | a retry after a lost answer gets **409 Unavailable for the guest's own stay**; no second reservation (the overlap rule stops it), but the client never learns its id | `test_post_is_not_idempotent_a_retry_answers_409_for_the_guests_own_stay` (pinned gap) |

The POST gap is accepted for P07 and fixed in **P11** with an `Idempotency-Key` header (the
server remembers key → answer and replays the same 201). Note the subtle part: in this domain a
naive retry does **not** double-book — but a retry with different dates would create a second
reservation, and the 409 for the first retry is a wrong answer from the guest's point of view.

## 3. Status codes

| Status | When | Why this code |
|---|---|---|
| 200 | search answered; contract served | a read that worked |
| 201 | booked | a new resource exists; the body names it (`id`) |
| 204 | cancelled | done, nothing to send back |
| 400 | the request itself is wrong: not JSON, a field missing/empty/not text, not a real date, no night, unknown room, limit out of range | the client must change the request before sending it again |
| 404 | no confirmed reservation with this id; unknown path | no such thing |
| 405 | the path exists, the method does not (`Allow` lists the right one) | HTTP semantics; helps the client fix its call |
| 409 | the stay shares a night with a Confirmed reservation | the request is valid but **conflicts with the current state** — it may succeed later (after a cancel) |
| 500 | the unit of work failed (e.g. the primary key refused a second R101 in the race) | the server's fault; the client may retry later |

**400 vs 422 for validation errors:** FastAPI's default is 422; the course contract uses 400 for
every malformed request, which is the RFC 9110 meaning ("the server cannot process the request due
to a client error"). One code for all request errors keeps clients simple; `title` says which.

**Why UnknownRoom is 400, not 404:** the *resource addressed* (`/reservations`) exists; R99 is a
bad value inside the body. 404 would suggest the URL is wrong.

**Why "no night" (15–15 Nov) is decided by BookingService and still 400:** the order of the dates
is the booking rule's job (`DateRange.is_valid`), so the endpoint lets it through and `to_http`
maps `InvalidDates` to 400. A date that is not a date (`12.11.2026`) is a request-shape problem the
endpoint rejects before calling anything (`test_booking_without_a_night_is_invalid_dates_decided_by_booking_service`
shows the first opens a unit of work, `test_booking_dates_that_are_not_real_dates_are_invalid_dates` that the second does not).

## 4. One error format: problem details (RFC 9457)

```json
{"title":"Unavailable","status":409,"detail":"The room is booked for at least one night of this stay."}
```

- Content-Type `application/problem+json`, so a client knows it is an error without parsing.
- Exactly three keys (the schema says `additionalProperties: false`). RFC 9457 also allows `type`
  and `instance`; the course keeps three keys and so do I — `title` is the stable identifier.
- **Clients compare `title`**; `detail` is for people and may change. Seven titles exist: the
  course's five (Unavailable, InvalidDates, UnknownRoom, InvalidRequest, NotFound) belong to the
  operations; MethodNotAllowed and InternalError can come from any path. The contract's enum is
  exactly the set the code can send (`test_the_problem_title_list_is_exactly_what_the_code_can_send`).
- Starlette's own 404/405 and any unexpected exception are converted too, so **no** answer of
  this API is a plain-text error (`test_unknown_path_is_404_problem_details`,
  `test_wrong_method_is_405_problem_details_with_allow`,
  `test_a_failure_behind_the_api_is_500_problem_details_without_internals` — the 500 body does
  not leak the exception text).

## 5. Validation order — "check what BookingService cannot know, then call it once"

`POST /reservations` (diagram: [book-request-flow](diagrams/book-request-flow.svg)):

1. **Read** the body: `Content-Type: application/json` (charset allowed), valid UTF-8 JSON, an
   object; pydantic `ReservationRequest` requires the five camelCase fields as **strict** non-empty
   strings (`7` is not quietly turned into `"7"`), ignores unknown fields (tolerant reader) →
   otherwise 400 InvalidRequest.
2. **Check** the dates are real calendar dates written `YYYY-MM-DD` (regex + `date.fromisoformat`,
   so `2026-02-30` and `20261112` are refused) → 400 InvalidDates; the room is in the catalog →
   400 UnknownRoom.
3. **Call** `BookingService.reserve` once, inside the unit of work, in a worker thread.
4. **Answer** with `to_http`: Accepted → 201, Unavailable → 409, InvalidDates → 400.

A request refused in steps 1–2 never opens a unit of work, i.e. never touches the database
(`units_of_work == []` in `tests/test_api_http.py`).

## 6. Pages: cursor pagination

`limit` (1–100, default 20) and `after` (the last room number of the previous page); the answer's
`next` is the value to pass as `after`, `null` on the last page. Free rooms come in **text order**
of the room number (R10 before R7), and `after` compares text too, so paging never skips or
repeats a room (`test_search_pages_follow_text_order_and_the_cursor`: R7, R10, R8, R9 with
limit 3 → `[R10, R7, R8]`, `[R9]`).

**Cursor vs offset:** with `offset=20` a room that becomes free or booked between two page
requests shifts every later page; the cursor names the last item seen and is stable. At 40 rooms
it hardly matters; the contract is right for when it does, at no cost.

## 7. Never break a client

- Answers may gain fields; existing fields are never renamed or removed in version 1
  (`info.description`). The tests pin the exact JSON of every documented answer, so an accidental
  rename fails a test (mutation 5 in [break_the_contract](evidence/logs/break-the-contract.txt)).
- Requests: unknown fields are ignored, so a newer client still works
  (`test_booking_accepts_a_charset_and_ignores_unknown_fields`).
- A breaking change would get `/v2/...` next to the old paths (L04). Not needed now.
- The room `type` is open catalog data, not an enum — a new room type is not an API change.

## 8. Contract first, and kept true

`docs/openapi.yaml` (OpenAPI 3.1) was written before the endpoints; the app serves the file itself
at `GET /openapi.yaml` and generates no other description. `tests/test_openapi_contract.py` keeps
the two equal **in both directions**:

| Direction | How |
|---|---|
| every route the app serves is in the contract, and every operation in the contract is served | compares Starlette's route table with `paths` |
| every status and error title the code can send is documented, and nothing undocumented | reads `api.py` with `ast`: `problem(<status>, "<Title>")`, `status_code=`, calls into the unit of work (→ 500), following helpers such as `to_http` |
| every documented example is what the app really answers | one probe request per example; status, media type and the **exact** body are compared, and the body is validated against the schema with `jsonschema` (2020-12) |
| the request and answer shapes are the pydantic models | field aliases of `ReservationRequest`, `Availability`, `RoomView`, `ReservationCreated`, `Problem` == schema properties |

Breaking it on purpose (six mutations on copies — code ahead of the contract and contract ahead of
the code) was caught every time: [logs/break-the-contract.txt](evidence/logs/break-the-contract.txt).

## 9. What is deliberately not in version 1

| Not there | Why | When |
|---|---|---|
| `GET /reservations/{id}` (and so no `Location` header on 201) | the course's three operations; a `Location` pointing at a 405 would mislead | when a client needs it |
| Authentication / authorisation | anyone on the port could cancel any reservation — acceptable on a laptop only | S4, P21 |
| `Idempotency-Key` on POST | see §2 | P11 |
| Cache headers (`Cache-Control`, `ETag`) on the search | the cache is P08's experiment; the estimate says the search is the hot path | P08 |
| Rate limiting | 3.33 searches/s at the estimated peak; no need yet | — |

## 10. How the API meets the capacity estimate

[capacity.md](../../hotel-booking/docs/capacity.md): 3.33 searches a second at the peak, 133
database questions a second (one per room per search), about 3 requests in flight. The API keeps
the search cheap where it can without changing the rule: the partial index
`reservations_confirmed_room_stay` answers each overlap question; the blocking database work runs
in Starlette's thread pool so the event loop keeps accepting requests; pages are capped at 100 rooms.
The remaining cost (N queries per search) is P08's job — measure first, then cache.
