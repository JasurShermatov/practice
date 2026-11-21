# ADR-001 — Start with one application containing three modules

**Status:** Proposed · Optional in P01

## Problem and requirement

Version one needs booking (R1, R2), a lasting saved record (F3, R3) and confirmation emails
(R3). A small team must keep these jobs clear so that a failure in one part has an obvious
meaning for the others — for example, an email failure must never remove a confirmed booking.

## Options considered

1. **One application, no internal structure** — simplest to start, but booking, storage and
   email logic mix together and the email-failure rule becomes hard to see.
2. **One application with three modules** — Booking decides capacity and duplicates; Storage
   keeps bookings and statuses; Notification delivers email and records delivery status.
3. **Separate services** (booking service + email service) — independent releases, but adds
   network calls, new failure cases (lost messages, retries) and more to operate and monitor.

## Choice and reasons

Option 2. The team is small and can release everything together; three modules make each
responsibility explicit (Booking owns the capacity decision, Notification never decides who
gets a ticket) without the operating cost of separate services.

## What it makes harder

All modules are released together: a change to email ships with the booking code. One
process failure affects every job at once.

## Evidence and limitations

Based on the brief and classroom reasoning only — no benchmark, load test or operating data.
Label: **Proposed**.

## When to reconsider

If a demonstrated need appears for releasing or scaling email independently of booking
(compared later in L04/P04 and L08/P15–P16), compare option 3 against its communication and
recovery costs before changing.
