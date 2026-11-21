# Quality scenarios

Hotel booking app (rooms R7 Standard and R8 Deluxe; guests Maya, Omar, Nora). P05 Step 1.
Destination in the project: `hotel-booking/docs/quality-scenarios.md` (copied here unchanged at the
start of P06; the P05 original stays in `practices/P05-domain-context-boundaries/docs/`).

A scenario turns a wish ("fast", "reliable") into a situation that can be tested, with a number.
Each one has the same seven lines: Source, Stimulus, Environment, Artifact, Response, Measure and
the practice that checks it. The numbers are the course's targets for this project; a target is
**Proposed** until the practice in "Checked in" has produced an **Observed** result.

## Stakeholders

| Who | What they care about |
|---|---|
| Guest | Finds a free room quickly; never loses a booking |
| Receptionist | Never promises one room twice; can cancel at the desk |
| Hotel manager (domain expert) | Knows the rules; wants deposits and SMS soon |
| Development team | Can change one area without breaking the others |
| Email/SMS and payment providers | Outside systems that can be slow or down |

## Summary

| Scenario | Quality | Measure (number) | Checked in | Status today |
|---|---|---|---|---|
| S1 | Performance | p95 search response ≤ 1 second, 0 wrong answers | P08, P23 | Proposed |
| S2 | Data integrity | 0 double bookings in 100 simultaneous pairs | P09 | Proposed; known to fail today (P03 race: 2 Confirmed for R7) |
| S3 | Availability | 0 lost bookings while email is down; 100% of failures counted | P04, P10 | Observed for one booking (P04 R6 test) |
| S4 | Security | 0 of 100 attempts show another guest's reservation | P21 | Proposed; no access control exists yet |
| S5 | Modifiability | 0 lines changed in BookingService; ≤ 2 files changed | P04 | Observed in P04 (SMS sender added) |
| S6 | Sustainability | ≥ 20% fewer Wh per 1,000 completed searches | P08, P24 | Proposed |

## S3 · Availability: a failed message keeps the booking

| Part | S3 |
|---|---|
| Source | The email provider |
| Stimulus | It stops answering |
| Environment | For 10 minutes, during normal bookings |
| Artifact | BookingService.reserve and the notification sender |
| Response | Every valid booking is still Accepted and saved; the failed message is reported |
| Measure | 0 lost bookings; every failed message is counted (100% of failures reported) |
| Checked in | P04 (R6 test, done) and P10 |

Today's proof is P04's test `a failed confirmation keeps the booking` (one booking, a fake sender
that raises): the result is `Accepted R101`, `notification_failed` is true and the store holds 1
reservation. P10 repeats it for ten minutes of failures with a queue and counts every failure.

## S1 · Performance

| Part | S1 |
|---|---|
| Source | 200 guests, on the website and through the reception desk |
| Stimulus | They search free rooms for 12–14 Nov |
| Environment | All 200 searches arrive within one minute, during normal operation |
| Artifact | The free-room search: BookingService.find_free_rooms (Reservations, asking Rooms for the room list) |
| Response | Every guest gets the correct free rooms for 12–14 Nov |
| Measure | p95 response ≤ 1 second over the 200 searches; 0 wrong answers |
| Checked in | P08 (cache) and P23 (load test) |

p95: sort the 200 response times; the 190th is the p95. 0.8 s meets the target; 1.4 s fails it
even if the average is 0.3 s.

## S2 · Data integrity

| Part | S2 |
|---|---|
| Source | 100 pairs of guests (website and reception desk) |
| Stimulus | Both guests of each pair book the same room for the same nights at the same moment |
| Environment | Concurrent requests during normal operation; from P07 several app processes share one database |
| Artifact | BookingService.reserve and the reservation store (Reservations) |
| Response | Exactly one Confirmed reservation per pair; the other guest gets Unavailable |
| Measure | 100 Confirmed and 100 Unavailable; 0 double bookings |
| Checked in | P09 |

Status: the P03 race demo (`python main.py --race`) produces 2 Confirmed reservations for R7 on
12–14 Nov, so S2 is **not met** today. This is a known, pinned defect, fixed in P09.

## S4 · Security

| Part | S4 |
|---|---|
| Source | A signed-in guest trying to read someone else's booking |
| Stimulus | 100 requests for reservations that belong to another guest (for example guessed ids R101, R102 …) |
| Environment | Normal operation, through the public API (from P07) with sign-in (P21) |
| Artifact | The "view a booking" use case (R5) in Reservations |
| Response | Every request is refused without showing whether the id exists; the attempts are logged |
| Measure | 0 of 100 reservations shown to the wrong guest |
| Checked in | P21 |

Note for P21: ids are sequential (R101, R102 …), so guessing is trivial; the owner check must not
rely on ids being secret.

## S5 · Modifiability

| Part | S5 |
|---|---|
| Source | The hotel manager |
| Stimulus | Asks for SMS confirmations as well as email |
| Environment | Development time, while the app is in use |
| Artifact | The notification sender (Notifications) and the wiring in main.py |
| Response | SMS is a new sender class; BookingService is not edited; all tests stay green |
| Measure | 0 lines changed in BookingService; at most 2 files change |
| Checked in | P04 (SMS sender, done) |

## S6 · Sustainability

| Part | S6 |
|---|---|
| Source | The development team, changing the search (for example adding a cache) |
| Stimulus | The same 1,000 searches are run before and after the change |
| Environment | Same server, same data, same workload; energy measured on the server |
| Artifact | The free-room search path (Reservations and Rooms; later the cache and database) |
| Response | Same correct answers, using less energy for the same useful work |
| Measure | At least 20% fewer watt-hours per 1,000 completed searches (example: 50 Wh → 38 Wh = 24% less) |
| Checked in | P08 and P24 |

Energy is counted per *completed* search, so a change that answers fewer searches cannot look
greener by doing less work.

## Which context each scenario presses on

Used in [contexts.md](contexts.md) and in the P06 module split.

| Scenario | Context(s) it stresses | Why |
|---|---|---|
| S1 | Reservations, Rooms | The search reads Reservations' rows and Rooms' room list |
| S2 | Reservations | It owns the booking rule (card 1); the fix must live there |
| S3 | Notifications border | A failed message must stay on the Notifications side (card 8, R6) |
| S4 | Reservations | It keeps reservations and must decide who may see one |
| S5 | Notifications | A new channel is a new sender inside Notifications |
| S6 | Reservations, Rooms | Same path as S1 |
