"""docs/openapi.yaml and the implemented API must match exactly, in both directions (P07 Step 3).

The contract was written first; these checks keep code and contract from drifting apart:

1. Routes: every (method, path) the Starlette app serves is an operation in the contract, and
   every operation in the contract is served (HEAD, which Starlette adds to every GET, is implied).
2. Statuses and error titles, read from the code: ``hotel_booking/api.py`` is parsed with ``ast``.
   For each endpoint, every ``problem(<status>, "<Title>", ...)`` call, every ``status_code=<n>``
   and every call into the unit of work (which can end in 500 InternalError) is collected,
   following the module's helper functions (``to_http``). That set must equal the statuses and
   titles the contract documents for the operation (titles = the examples' ``title`` values).
3. Examples are executable: for every example answer in the contract there is a request below
   that makes the running app answer *exactly* that status, media type and body - and every probe
   answer validates against the contract's JSON schema (OpenAPI 3.1 schemas are JSON Schema 2020-12).
4. The contract is well formed: every ``$ref`` resolves, operationIds are unique, path parameters
   are declared, every response has a description, the Problem title list is exactly the set of
   titles the code can send, and the app serves this very file.

The contract was not loaded into the Swagger editor here (no browser/network in the build
environment); that check is in the P07 README as "to do by the student".

P08 change (deliberate): the contract is version 1.1.0 with GET /stats (operation getStats, schema
Stats) and the search's X-Cache header. The probe app now has the counters and an in-memory cache,
like the wiring; one new probe (two searches, then GET /stats) makes the getStats example real;
the operation list, the pydantic-model check and the header check (now also: the value is one the
contract allows) cover the new parts. Nothing else changed: the checks still run both directions.

P09 change (deliberate): the contract is version 1.2.0. The 409 answer of POST /reservations has a
second example, ``lostTheRace``, and its probe really runs the race: two simultaneous bookings for
R7 through the real wiring on SQLite (``main.build_api`` with a slow step), and the answer of the
request the database refused must be exactly that example. The 500 description no longer names the
duplicate-id case (it cannot happen any more). Everything else is unchanged, in both directions.

P10 change (deliberate): the contract is version 1.3.0. GET /stats has five *optional* counters
(``notificationsAccepted`` ... ``notificationsFailed``), present only when the app is wired with the
notification queue, so ``test_answer_fields_match_the_pydantic_models`` now compares the schema's
``required`` list with the model's fields that have no default (the optional ones are exactly the
fields that default to None). Two new examples are produced by the real wiring with a real queue
(``main.build_api`` + ``QueuedNotificationSender``, capacity 1, one worker held inside a send): the
third booking's 201 with ``notificationFailed: true`` (``confirmationRefused``) and the counters
after it (``withQueue``). The probe app without a queue still answers ``twoSearches`` without them.
"""
from __future__ import annotations

import ast
import inspect
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from starlette.routing import Route
from starlette.testclient import TestClient

import hotel_booking.api as api_module
from hotel_booking.api import DEFAULT_CONTRACT, create_app
from hotel_booking.api_cache import AvailabilityCache, InMemoryKeyValueStore
from hotel_booking.api_stats import CountingReservationStore, Stats
from hotel_booking.demo import HOTEL_ROOMS
from hotel_booking.notifications.internal import EmailNotificationSender
from hotel_booking.reservations import BookingService
from hotel_booking.reservations.internal import InMemoryReservationStore

yaml = pytest.importorskip("yaml")  # PyYAML (requirements.txt, dev)
jsonschema = pytest.importorskip("jsonschema")

CONTRACT: dict[str, Any] = yaml.safe_load(DEFAULT_CONTRACT.read_text(encoding="utf-8"))
METHODS = ("get", "put", "post", "delete", "patch", "options", "trace")
MAYA = {"guestName": "Maya", "guestEmail": "maya@example.com", "room": "R7", "checkIn": "2026-11-12", "checkOut": "2026-11-14"}
SEARCH = "/rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14"

Key = tuple[str, str]  # (METHOD, path)


# --------------------------------------------------------------------------- reading the contract


def resolve(node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        target: Any = CONTRACT
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


def operations() -> dict[Key, dict[str, Any]]:
    return {(method.upper(), path): operation
            for path, item in CONTRACT["paths"].items()
            for method, operation in item.items() if method in METHODS}


def responses_of(operation: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """(status, response) pairs; ``x-...`` keys are OpenAPI extensions, not answers."""
    return [(status, response) for status, response in operation["responses"].items() if not str(status).startswith("x-")]


def documented_examples(response: dict[str, Any]) -> Iterator[tuple[str, str, Any]]:
    """(media type, example name, value) of one response object."""
    for media_type, content in resolve(response).get("content", {}).items():
        for name, example in content.get("examples", {}).items():
            yield media_type, name, example["value"]


def documented_answers(operation: dict[str, Any]) -> dict[int, set[str | None]]:
    """Status -> titles (None for a success answer) the contract documents for one operation."""
    found: dict[int, set[str | None]] = {}
    for status, response in responses_of(operation):
        titles = {value.get("title") for _, _, value in documented_examples(response)
                  if isinstance(value, dict) and "title" in value}
        found[int(status)] = titles if titles else {None}
    return found


# --------------------------------------------------------------------------- reading the code


def api_tree() -> ast.Module:
    return ast.parse(inspect.getsource(api_module))


def module_functions(tree: ast.Module) -> dict[str, ast.AST]:
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)}


def endpoint_functions(tree: ast.Module) -> dict[str, ast.AST]:
    create = module_functions(tree)["create_app"]
    return {node.name: node for node in ast.walk(create) if isinstance(node, ast.AsyncFunctionDef)}


def answers_in_code(function: ast.AST, helpers: dict[str, ast.AST], seen: frozenset[str] = frozenset()) -> dict[int, set[str | None]]:
    found: dict[int, set[str | None]] = {}

    def add(status: int, title: str | None) -> None:
        found.setdefault(status, set()).add(title)

    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if name == "problem":
            status, title = node.args[0], node.args[1]
            assert isinstance(status, ast.Constant) and isinstance(title, ast.Constant), ast.dump(node)
            add(int(status.value), str(title.value))
            continue
        for keyword in node.keywords:
            if keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant):
                add(int(keyword.value.value), None)
        if name == "in_unit_of_work":
            add(500, "InternalError")  # the unit of work may fail; the error handler answers 500
        elif name in helpers and name not in seen | {"problem", "answer"}:
            for status, titles in answers_in_code(helpers[name], helpers, seen | {name}).items():
                found.setdefault(status, set()).update(titles)
    return found


def every_title_in_code() -> set[str]:
    return {str(node.args[1].value) for node in ast.walk(api_tree())
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "problem"
            and isinstance(node.args[1], ast.Constant)}


# --------------------------------------------------------------------------- the app


def new_client(broken: bool = False) -> TestClient:
    stats = Stats()
    service = BookingService(HOTEL_ROOMS, CountingReservationStore(InMemoryReservationStore(), stats),
                             EmailNotificationSender())

    @contextmanager
    def unit_of_work() -> Iterator[BookingService]:
        if broken:
            raise RuntimeError("database down")
        yield service

    cache = AvailabilityCache(InMemoryKeyValueStore())
    return TestClient(create_app(HOTEL_ROOMS, unit_of_work, stats, cache), raise_server_exceptions=False)


APP_ROUTES = [route for route in new_client().app.routes if isinstance(route, Route)]  # type: ignore[attr-defined]


def implemented_routes() -> dict[Key, str]:
    """(METHOD, path) -> endpoint function name."""
    return {(method, route.path): route.endpoint.__name__
            for route in APP_ROUTES for method in (route.methods or set()) - {"HEAD"}}


# --------------------------------------------------------------------------- 1 + 2: routes and statuses


def test_every_route_is_in_the_contract_and_every_operation_is_served() -> None:
    assert set(implemented_routes()) == set(operations())


def test_the_api_has_the_three_course_operations_and_the_contract_route() -> None:
    assert {operation["operationId"] for operation in operations().values()} == {
        "findFreeRooms", "reserve", "cancel", "getContract", "getStats"}


@pytest.mark.parametrize("key", sorted(operations()), ids=lambda key: f"{key[0]} {key[1]}")
def test_statuses_and_titles_in_the_code_equal_the_contract(key: Key) -> None:
    tree = api_tree()
    endpoint = endpoint_functions(tree)[implemented_routes()[key]]
    assert answers_in_code(endpoint, module_functions(tree)) == documented_answers(operations()[key])


def test_the_problem_title_list_is_exactly_what_the_code_can_send() -> None:
    enum = CONTRACT["components"]["schemas"]["Problem"]["properties"]["title"]["enum"]
    assert len(enum) == len(set(enum))
    assert set(enum) == every_title_in_code()


def test_the_five_course_titles_belong_to_the_operations() -> None:
    by_operations = {title for operation in operations().values()
                     for titles in documented_answers(operation).values() for title in titles if title}
    assert {"Unavailable", "InvalidDates", "UnknownRoom", "InvalidRequest", "NotFound"} <= by_operations


# --------------------------------------------------------------------------- 3: examples are executable


Probe = Callable[[], Any]

PROBES: dict[tuple[str, str], Probe] = {
    # (operation or component response, example name) -> the request that must produce it
    ("findFreeRooms 200", "allFree"): lambda: new_client().get(SEARCH),
    ("findFreeRooms 200", "firstPage"): lambda: new_client().get(f"{SEARCH}&limit=1"),
    ("findFreeRooms 400", "notADate"): lambda: new_client().get("/rooms/availability?checkIn=12.11.2026&checkOut=2026-11-14"),
    ("findFreeRooms 400", "wrongOrder"): lambda: new_client().get("/rooms/availability?checkIn=2026-11-14&checkOut=2026-11-12"),
    ("findFreeRooms 400", "badLimit"): lambda: new_client().get(f"{SEARCH}&limit=0"),
    ("findFreeRooms 500", "serverFailed"): lambda: new_client(broken=True).get(SEARCH),
    ("reserve 201", "booked"): lambda: new_client().post("/reservations", json=MAYA),
    ("reserve 201", "confirmationRefused"): lambda: queue_full()[0],
    ("reserve 400", "notJson"): lambda: new_client().post("/reservations", content="Maya, R7", headers={"content-type": "text/plain"}),
    ("reserve 400", "notADate"): lambda: new_client().post("/reservations", json={**MAYA, "checkIn": "12.11.2026"}),
    ("reserve 400", "noNight"): lambda: new_client().post("/reservations", json={**MAYA, "checkOut": "2026-11-12"}),
    ("reserve 400", "unknownRoom"): lambda: new_client().post("/reservations", json={**MAYA, "room": "R99"}),
    ("reserve 409", "sharedNight"): lambda: twice(lambda client: client.post("/reservations", json=MAYA)),
    ("reserve 409", "lostTheRace"): lambda: race_loser(),
    ("reserve 500", "serverFailed"): lambda: new_client(broken=True).post("/reservations", json=MAYA),
    ("cancel 204", "-"): lambda: after_booking(lambda client: client.delete("/reservations/R101")),
    ("cancel 404", "notConfirmed"): lambda: new_client().delete("/reservations/R101"),
    ("cancel 500", "serverFailed"): lambda: new_client(broken=True).delete("/reservations/R101"),
    ("getContract 200", "-"): lambda: new_client().get("/openapi.yaml"),
    ("getStats 200", "twoSearches"): lambda: twice(lambda client: client.get(SEARCH), then="/stats"),
    ("getStats 200", "withQueue"): lambda: queue_full()[1],
    ("UnknownPath", "noSuchPath"): lambda: new_client().get("/bookings"),
    ("MethodNotAllowed", "wrongMethod"): lambda: new_client().put("/reservations"),
}


def race_loser() -> Any:
    """P09: two bookings for R7 at the same moment through the real SQLite wiring; the refused one's answer."""
    import main  # the wiring: SQLite file, unit of work, the store whose INSERT the trigger refuses

    with tempfile.TemporaryDirectory() as folder:
        app, _ = main.build_api(main.sqlite_connector(Path(folder) / "hotel.sqlite3"), slow_step_seconds=0.3)
        client = TestClient(app, raise_server_exceptions=False)
        answers: list[Any] = []
        guests = [MAYA, {**MAYA, "guestName": "Omar", "guestEmail": "omar@example.com"}]
        threads = [threading.Thread(target=lambda body=body: answers.append(client.post("/reservations", json=body)))
                   for body in guests]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert sorted(answer.status_code for answer in answers) == [201, 409]
    return next(answer for answer in answers if answer.status_code == 409)


def queue_full() -> tuple[Any, Any]:
    """P10: three bookings through the real wiring with a queue of 1 and one worker held inside a send.

    Booking 1 is taken by the worker (and stays in flight), booking 2 waits in the one place,
    booking 3 finds the queue full: 201 with notificationFailed true. Returns that answer and GET /stats.
    """
    import main  # the wiring: SQLite file, unit of work, HeldConfirmations over the queue

    from hotel_booking.notifications import DeliveryStatus
    from hotel_booking.notifications.internal import QueuedNotificationSender

    release = threading.Event()

    class HeldSender:
        def send_confirmation(self, confirmation: Any) -> None:
            release.wait(5)

    queue = QueuedNotificationSender(HeldSender(), capacity=1, workers=1)
    try:
        with tempfile.TemporaryDirectory() as folder:
            app, _ = main.build_api(main.sqlite_connector(Path(folder) / "hotel.sqlite3"), notifications=queue)
            client = TestClient(app, raise_server_exceptions=False)
            assert client.post("/reservations", json=MAYA).json()["id"] == "R101"
            for _ in range(200):  # wait until the worker has taken R101 (it stays inside the send)
                if queue.status_of("R101") is DeliveryStatus.SENDING:
                    break
                threading.Event().wait(0.01)
            client.post("/reservations", json={**MAYA, "room": "R8"})
            refused = client.post("/reservations", json={**MAYA, "checkIn": "2026-12-01", "checkOut": "2026-12-03"})
            return refused, client.get("/stats")
    finally:
        release.set()
        queue.close(drain=True, timeout=5)


def twice(request: Callable[[TestClient], Any], then: str | None = None) -> Any:
    client = new_client()
    request(client)
    second = request(client)
    return second if then is None else client.get(then)


def after_booking(request: Callable[[TestClient], Any]) -> Any:
    client = new_client()
    client.post("/reservations", json=MAYA)
    return request(client)


def documented_responses() -> dict[tuple[str, str], tuple[int, dict[str, Any], str | None, Any]]:
    """(label, example name) -> (status, response object, media type, example value)."""
    found: dict[tuple[str, str], tuple[int, dict[str, Any], str | None, Any]] = {}
    for operation in operations().values():
        for status, response in responses_of(operation):
            label = f"{operation['operationId']} {status}"
            examples = list(documented_examples(response))
            if not examples:
                media = next(iter(resolve(response).get("content", {})), None)
                found[(label, "-")] = (int(status), resolve(response), media, None)
            for media, name, value in examples:
                found[(label, name)] = (int(status), resolve(response), media, value)
    for name in ("UnknownPath", "MethodNotAllowed"):
        response = CONTRACT["components"]["responses"][name]
        for media, example, value in documented_examples(response):
            status = value["status"]
            found[(name, example)] = (status, response, media, value)
    return found


def test_there_is_one_probe_for_every_documented_answer() -> None:
    assert set(PROBES) == set(documented_responses())


@pytest.mark.parametrize("key", sorted(PROBES), ids=lambda key: f"{key[0]}:{key[1]}")
def test_the_app_answers_exactly_the_documented_example(key: tuple[str, str]) -> None:
    status, response_object, media_type, example = documented_responses()[key]
    response = PROBES[key]()
    assert response.status_code == status
    if media_type is None:
        assert response.content == b""
        return
    assert response.headers["content-type"].split(";")[0] == media_type
    if media_type == "application/yaml":
        assert response.text == DEFAULT_CONTRACT.read_text(encoding="utf-8")
        return
    body = response.json()
    if example is not None:
        assert body == example
    validate(body, response_object["content"][media_type]["schema"])
    for header, declared in response_object.get("headers", {}).items():
        assert header.lower() in response.headers
        validate(response.headers[header], declared["schema"])


def validate(instance: Any, schema: dict[str, Any]) -> None:
    root = {"components": CONTRACT["components"], **schema}
    jsonschema.Draft202012Validator(root, format_checker=jsonschema.FormatChecker()).validate(instance)


# --------------------------------------------------------------------------- 4: a well-formed contract


def every_ref(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref":
                yield value
            else:
                yield from every_ref(value)
    elif isinstance(node, list):
        for item in node:
            yield from every_ref(item)


def test_header_and_every_ref_resolves() -> None:
    assert CONTRACT["openapi"].startswith("3.1")
    assert CONTRACT["info"]["title"] and CONTRACT["info"]["version"]
    for ref in every_ref(CONTRACT):
        assert ref.startswith("#/"), ref
        resolve({"$ref": ref})  # raises KeyError when it points nowhere


def test_operation_ids_unique_and_every_response_described() -> None:
    ids = [operation["operationId"] for operation in operations().values()]
    assert len(ids) == len(set(ids))
    for operation in operations().values():
        for response in operation["responses"].values():
            assert resolve(response).get("description"), operation["operationId"]


def test_path_parameters_are_declared() -> None:
    for (method, path), operation in operations().items():
        in_path = {part[1:-1] for part in path.split("/") if part.startswith("{")}
        declared = {p["name"] for p in operation.get("parameters", []) if p["in"] == "path"}
        assert in_path == declared, f"{method} {path}"
        assert all(p["required"] for p in operation.get("parameters", []) if p["in"] == "path")


def test_every_schema_example_validates() -> None:
    for operation in operations().values():
        body = operation.get("requestBody")
        if body:
            for content in body["content"].values():
                validate(content["example"], content["schema"])
        for response in operation["responses"].values():
            for media, _, value in documented_examples(response):
                validate(value, resolve(response)["content"][media]["schema"])


def test_query_parameters_match_what_the_search_reads() -> None:
    documented = {p["name"] for p in operations()[("GET", "/rooms/availability")]["parameters"]}
    source = inspect.getsource(api_module)
    read = set(__import__("re").findall(r'query\.get\("(\w+)"', source))
    assert documented == read == {"checkIn", "checkOut", "limit", "after"}


def test_every_header_the_code_sets_is_documented() -> None:
    """P08: the other direction for headers - a header the code adds must be in the contract."""
    documented = {name for operation in operations().values() for _, response in responses_of(operation)
                  for name in resolve(response).get("headers", {})}
    set_by_code = {node.slice.id for node in ast.walk(api_tree())
                   if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store)
                   and ast.unparse(node.value).endswith(".headers") and isinstance(node.slice, ast.Name)}
    assert set_by_code == {"CACHE_HEADER"}
    assert {getattr(api_module, name) for name in set_by_code} <= documented


def test_request_body_fields_match_the_pydantic_model() -> None:
    schema = CONTRACT["components"]["schemas"]["ReservationRequest"]
    aliases = {field.alias for field in api_module.ReservationRequest.model_fields.values()}
    assert set(schema["properties"]) == set(schema["required"]) == aliases


def test_answer_fields_match_the_pydantic_models() -> None:
    schemas = CONTRACT["components"]["schemas"]
    for model, name in [(api_module.Availability, "Availability"), (api_module.RoomView, "Room"),
                        (api_module.ReservationCreated, "Reservation"), (api_module.Problem, "Problem"),
                        (api_module.StatsView, "Stats")]:
        aliases = [field.alias for field in model.model_fields.values()]
        assert aliases == list(schemas[name]["properties"]), name
        always = {field.alias for field in model.model_fields.values() if field.is_required()}
        assert set(schemas[name]["required"]) == always, name  # P10: optional = defaults to None
