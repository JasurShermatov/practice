"""The HTTP API (P07): three endpoints that turn HTTP requests into BookingService calls and back.

    GET    /rooms/availability?checkIn=&checkOut=[&limit=&after=]  -> find_free_rooms   200 | 400
    POST   /reservations           (JSON body, five text fields)     -> reserve           201 | 400 | 409
    DELETE /reservations/{id}                                         -> cancel            204 | 404
    GET    /openapi.yaml           the contract itself (docs/openapi.yaml, written first, by hand)

The API is an *edge*, not a module: it lives outside the four module folders and uses only their
public contracts (``.importlinter`` rule "The HTTP API uses only the public contracts of the
modules"); no module imports it. It does not know which store is used: the wiring (``main.py``)
hands it a *unit of work* - "``with unit_of_work() as service:``" gives one request a
``BookingService`` and saves whatever changed when the block ends (or rolls back on an error).

Each endpoint does four things, in this order (P07 Step 5):

1. read   - the query, the path or the JSON body (validated with pydantic);
2. check  - only what BookingService cannot know: the shape of the request, real dates, a known room;
3. call   - exactly one BookingService method, inside the unit of work, in a worker thread
            (database I/O must not block the event loop);
4. answer - ``to_http`` turns the booking answer into a status code and a body.

The booking rule itself (dates in order, no shared night) stays in Reservations. Every error,
including an unknown path, a wrong method and an unexpected failure, has the one shape of
RFC 9457 problem details: ``{"title", "status", "detail"}`` as ``application/problem+json``.
Clients compare ``title``; ``detail`` is a sentence for people and may change.

Framework: Starlette (the ASGI toolkit FastAPI is built on) + pydantic; served by uvicorn.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError
from pydantic.alias_generators import to_camel
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from hotel_booking.reservations import BookingOutcome, BookingResult, BookingService, DateRange, Guest
from hotel_booking.rooms import Room

logger = logging.getLogger(__name__)

# One request's work: "with unit_of_work() as service:" gives the endpoint a BookingService,
# and whatever changed is saved when the with-block ends (main.py decides the store).
UnitOfWork = Callable[[], AbstractContextManager[BookingService]]

DEFAULT_CONTRACT = Path(__file__).resolve().parents[1] / "docs" / "openapi.yaml"

PROBLEM_MEDIA_TYPE = "application/problem+json"
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

BODY_DETAIL = "The body must be JSON with guestName, guestEmail, room, checkIn and checkOut."
DATE_DETAIL = "checkIn and checkOut must be dates such as 2026-11-12."
ORDER_DETAIL = "checkOut must be after checkIn."
LIMIT_DETAIL = f"limit must be a whole number from 1 to {MAX_LIMIT}."
UNAVAILABLE_DETAIL = "The room is booked for at least one night of this stay."
SERVER_DETAIL = "The server could not complete the request. Try again later."

ISO_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
WHOLE_NUMBER = re.compile(r"[0-9]{1,3}")

T = TypeVar("T")


# --------------------------------------------------------------------------- the JSON shapes (pydantic)


class ReservationRequest(BaseModel):
    """The body of POST /reservations. Five non-empty JSON strings; unknown fields are ignored.

    Strict on purpose: ``"room": 7`` is not quietly turned into ``"7"``. Dates stay text here and
    are checked by ``parse_date``, because a wrong date has its own title (InvalidDates).
    """

    model_config = ConfigDict(alias_generator=to_camel, validate_by_alias=True, validate_by_name=False,
                              extra="ignore", frozen=True)

    guest_name: Annotated[StrictStr, Field(min_length=1)]
    guest_email: Annotated[StrictStr, Field(min_length=1)]
    room: Annotated[StrictStr, Field(min_length=1)]
    check_in: Annotated[StrictStr, Field(min_length=1)]
    check_out: Annotated[StrictStr, Field(min_length=1)]


class AnswerModel(BaseModel):
    """Base of every JSON answer: camelCase on the wire, snake_case in Python, immutable."""

    model_config = ConfigDict(alias_generator=to_camel, serialize_by_alias=True, validate_by_name=True,
                              frozen=True)


class RoomView(AnswerModel):
    number: str
    type: str


class Availability(AnswerModel):
    check_in: str
    check_out: str
    rooms: list[RoomView]
    next: str | None


class ReservationCreated(AnswerModel):
    id: str
    status: Literal["Confirmed"]
    notification_failed: bool


class Problem(AnswerModel):
    """RFC 9457 problem details with the three keys the contract promises."""

    title: str
    status: int
    detail: str


# --------------------------------------------------------------------------- small helpers


def answer(model: AnswerModel, status_code: int) -> JSONResponse:
    return JSONResponse(model.model_dump(mode="json"), status_code=status_code)


def problem(status: int, title: str, detail: str, headers: Mapping[str, str] | None = None) -> JSONResponse:
    """Problem details (RFC 9457): every error has the same three keys."""
    body = Problem(title=title, status=status, detail=detail).model_dump(mode="json")
    return JSONResponse(body, status_code=status, headers=headers, media_type=PROBLEM_MEDIA_TYPE)


def parse_date(text: str | None) -> date | None:
    """A real calendar date written exactly like 2026-11-12, otherwise None."""
    if text is None or not ISO_DAY.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:  # 2026-02-30
        return None


def to_http(result: BookingResult) -> JSONResponse:
    """Turns a booking answer into an HTTP status code and a JSON body (L04 ``toHttp``)."""
    match result.outcome:
        case BookingOutcome.ACCEPTED:
            assert result.reservation_id is not None
            created = ReservationCreated(id=result.reservation_id, status="Confirmed",
                                         notification_failed=result.notification_failed)
            return answer(created, status_code=201)
        case BookingOutcome.UNAVAILABLE:
            return problem(409, "Unavailable", UNAVAILABLE_DETAIL)
        case BookingOutcome.INVALID_DATES:
            return problem(400, "InvalidDates", ORDER_DETAIL)


async def in_unit_of_work(unit_of_work: UnitOfWork, work: Callable[[BookingService], T]) -> T:
    """Run one request's booking work inside the unit of work, in a worker thread.

    A failure inside ``work`` leaves the with-block with an exception, so the wiring rolls back
    and the error handler answers 500 InternalError.
    """
    def run() -> T:
        with unit_of_work() as service:
            return work(service)

    return await run_in_threadpool(run)


async def read_json(request: Request) -> object | None:
    """The decoded JSON body, or None when it is not sent as application/json or is not JSON."""
    media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media_type != "application/json":
        return None
    try:
        decoded: object = json.loads(await request.body())
    except ValueError:  # JSONDecodeError and UnicodeDecodeError are both ValueErrors
        return None
    return decoded


# --------------------------------------------------------------------------- the app


def create_app(rooms: Iterable[Room], unit_of_work: UnitOfWork, contract: Path = DEFAULT_CONTRACT) -> Starlette:
    """The web app over the rooms on sale and the unit of work the wiring chose."""
    rooms_by_number = {room.number: room for room in rooms}
    contract_text = contract.read_text(encoding="utf-8")  # fail at start-up, not at the first request

    async def serve_contract(request: Request) -> Response:
        # docs/openapi.yaml is the contract; the app serves that file and generates none of its own.
        return Response(contract_text, media_type="application/yaml", status_code=200)

    async def find_free_rooms(request: Request) -> Response:
        query = request.query_params
        check_in, check_out = parse_date(query.get("checkIn")), parse_date(query.get("checkOut"))
        if check_in is None or check_out is None:
            return problem(400, "InvalidDates", DATE_DETAIL)
        stay = DateRange(check_in, check_out)
        if not stay.is_valid():
            return problem(400, "InvalidDates", ORDER_DETAIL)
        limit = query.get("limit", str(DEFAULT_LIMIT))
        if not WHOLE_NUMBER.fullmatch(limit) or not 1 <= int(limit) <= MAX_LIMIT:
            return problem(400, "InvalidRequest", LIMIT_DETAIL)
        after = query.get("after", "")

        free = await in_unit_of_work(unit_of_work, lambda service: service.find_free_rooms(stay))
        # Cursor pagination (L04): the rooms after the last one the client has seen, in text order.
        rest = sorted((room for room in free if room.number > after), key=lambda room: room.number)
        page = rest[:int(limit)]
        body = Availability(
            check_in=check_in.isoformat(), check_out=check_out.isoformat(),
            rooms=[RoomView(number=room.number, type=room.type) for room in page],
            next=page[-1].number if len(rest) > len(page) else None,
        )
        return answer(body, status_code=200)

    async def reserve(request: Request) -> Response:
        try:
            body = ReservationRequest.model_validate(await read_json(request))
        except ValidationError:
            return problem(400, "InvalidRequest", BODY_DETAIL)
        check_in, check_out = parse_date(body.check_in), parse_date(body.check_out)
        if check_in is None or check_out is None:
            return problem(400, "InvalidDates", DATE_DETAIL)
        room = rooms_by_number.get(body.room)
        if room is None:
            return problem(400, "UnknownRoom", f"There is no room {body.room}.")

        guest, stay = Guest(body.guest_name, body.guest_email), DateRange(check_in, check_out)
        result = await in_unit_of_work(unit_of_work, lambda service: service.reserve(guest, room, stay))
        return to_http(result)

    async def cancel(request: Request) -> Response:
        reservation_id: str = request.path_params["id"]
        cancelled = await in_unit_of_work(unit_of_work, lambda service: service.cancel(reservation_id))
        if not cancelled:
            return problem(404, "NotFound", f"There is no confirmed reservation {reservation_id}.")
        return Response(status_code=204)

    async def http_error(request: Request, error: Exception) -> Response:
        """Starlette's own 404 (no such path) and 405 (method not allowed), as problem details."""
        assert isinstance(error, HTTPException)
        if error.status_code == 405:
            return problem(405, "MethodNotAllowed", f"{request.method} is not allowed on {request.url.path}.",
                           headers=error.headers)
        return problem(404, "NotFound", f"There is no resource at {request.url.path}.")

    async def server_error(request: Request, error: Exception) -> Response:
        """Any unexpected failure (for example the database refusing a row): 500, no internals leaked."""
        logger.error("%s %s failed", request.method, request.url.path, exc_info=error)
        return problem(500, "InternalError", SERVER_DETAIL)

    return Starlette(
        routes=[
            Route("/openapi.yaml", serve_contract, methods=["GET"]),
            Route("/rooms/availability", find_free_rooms, methods=["GET"]),
            Route("/reservations", reserve, methods=["POST"]),
            Route("/reservations/{id}", cancel, methods=["DELETE"]),
        ],
        exception_handlers={HTTPException: http_error, Exception: server_error},
    )
