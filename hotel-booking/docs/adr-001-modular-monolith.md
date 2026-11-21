# ADR-001: Build the hotel booking app as a modular monolith

Status: Accepted — decided in L03, implemented and checked in P06 (hotel-booking version 3).

## Context

- One small team writes, tests and releases the whole app, on one release rhythm.
- P05 found four business areas with clear jobs: Rooms (what is on sale), Reservations (who has
  which room for which nights — owns the booking rule), Payments (deposits) and Notifications
  (telling the guest). Every arrow on the context map starts at Reservations.
- The quality scenarios that matter most ([quality-scenarios.md](quality-scenarios.md)):
  **S2** — never two Confirmed reservations for the same room-night, even when two guests click at
  the same moment; **S3** — a failed confirmation message keeps the booking (R6).
- No business area has a measured need for its own release schedule or its own scaling: the hotel
  has two rooms, and the app runs on one machine.

## Decision

One deployable program with four modules, one per context. Each module is a Python package whose
`__init__.py` is its **public contract** and whose `internal.py` holds the classes that keep it.
Reservations owns the booking rule and talks to the others only through their contracts
(`RoomCatalog`, `PaymentService`, `NotificationSender` + its own `Confirmation` message). Only
`main.py` (the wiring) and the tests may name internal classes.

The borders are **checked by the build**, not by good intentions: three forbidden-import contracts
in `.importlinter` (run with `lint-imports`), enforced on every test run by
`tests/test_architecture.py`, which reads the same file and parses the code with `ast`.

## Alternatives considered

1. **One package with no inner borders (the P04 shape).** Cheapest today, but nothing stops
   BookingService from creating the email sender or Notifications from reading reservation rows;
   the P05 design would exist only on paper. Rejected.
2. **Separate services for Payments and Notifications** (Reservations + Rooms in one service).
   Gains: independent releases and scaling, failure isolation for a slow mail or payment provider.
   Costs: every call becomes a network call that can time out, needs retries, idempotency and
   monitoring; two or three deployments instead of one; S3 then depends on a remote system's
   availability, and the team has no measurement that justifies paying this now. Rejected *for now*.
3. **Layers only (UI / service / data) without business modules.** Separates technical concerns but
   puts the rules of all four contexts into one service layer — the problem P05 started from.
   Rejected.

## Consequences

- \+ One build, one deployment, in-process method calls: no network failure modes between modules.
- \+ S2 stays checkable in one place: the overlap rule and the store live only in Reservations (P09
  fixes the known race there, and only there).
- \+ Changes stay local (P05 change-impact check, now observable): SMS or a queue → Notifications
  + wiring; out-of-service rooms or prices → Rooms; the deposit rule → Payments.
- \+ A module can later become a service along an existing, tested border, because its contract is
  already the only way in.
- − All modules are released together; a defect in any module blocks the release of all.
- − All modules share one process: a crash or a slow call in one affects all (accepted while the
  load is two rooms; revisit with numbers).
- − The borders hold only while the architecture checks run. Today: in `python -m pytest`
  (and `lint-imports` on a machine with import-linter); from P25 in CI on every push.
- − `typing.Protocol` contracts are checked by shape (mypy, tests), not by the runtime.

## Revisit when

A module needs its own release schedule or its own scaling, **measured, not guessed** — for
example Notifications' sending time or failure rate starts to delay bookings (S3 measure), or
Payments must meet a provider's separate compliance rules. L07/P13 makes that decision with real
numbers; until then this record stands.
