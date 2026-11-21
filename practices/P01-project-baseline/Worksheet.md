# P01 · Student worksheet — Jasur Shermatov

Every field of the P01 worksheet, in the same order as the online worksheet. Longer versions
live in the linked files; the answers here are complete on their own so they can be copied into
the signed-in worksheet field by field.

Evidence labels: **Proposed** = planned, **Simulated** = classroom model, **Observed** = actually
run or done. Targets not yet agreed are **to agree**.

---

## 1. Programming example

A function I would write for this project (in Python, the language I use most): `is_available(concert_id)` — it counts the confirmed bookings
for a concert, compares the count with the concert's capacity and returns `True` if at least one
place is left. Its single job is to answer "is there space now?"; it does not save anything.

Object/class example:

```python
class Concert:
    def __init__(self, concert_id: str, capacity: int):
        self.concert_id = concert_id
        self.capacity = capacity
        self.confirmed: list[str] = []          # customer ids with a confirmed booking

    def has_space(self) -> bool:
        return len(self.confirmed) < self.capacity
```

The class keeps a concert's data (capacity, confirmed customers) together with the behaviour
that uses it (`has_space`). Note: this in-memory list disappears when the program stops, so it is
not a saved booking record.

## 2. SQL starting point

I would look Alex's booking up by customer and concert in a `bookings` table:

```sql
SELECT b.booking_ref, b.status, b.email_status, b.created_at
FROM   bookings  b
JOIN   customers c ON c.id = b.customer_id
WHERE  c.email      = 'alex@example.com'
  AND  b.concert_id = :friday_concert_id;
```

I would not filter on status here: Alex (or support) needs to see his booking whatever its
status, and in version one he can hold at most one booking per concert (rule R2).

Not sure yet: how this query should behave while another request is inserting a booking for
the same concert at the same moment.

## 3. Computer starting point

Unsaved working data lives in the process's memory (RAM). When the app closes or crashes, the
operating system frees that memory and the data is lost. Only data written to durable storage
(a file or a database that has committed the change) survives a restart — so a booking counts
only after it is saved, not when a number is held in a variable.

## 4. Personal learning goal

How can two overlapping requests that both read "19 of 20" be coordinated so that only one of
them saves the last ticket — and is a database transaction alone enough to guarantee that?

---

## 5. People, needs and first-version scope

- **Customer (Alex/Emma)** → opens a concert and taps Book → needs an honest *Confirmed* + reference or *Sold out* that matches what is saved.
- **Customer (Alex)** → reopens My bookings → needs to find the same saved booking; looking creates nothing.
- **Organiser Claire** → opens the Friday confirmed-booking list → needs a list that exactly matches the saved confirmed bookings, never above capacity.
- **Support worker Daniel** → looks up a reported reference (B17) → needs the saved booking and email status to explain an unclear result without creating another booking.

**Included now:** see availability, book one ticket, check a saved booking's status.
**Excluded from version one:** payment, cancellation, waiting list, numbered seats, more than one ticket per customer per concert.
Full version: [Scope.md](Scope.md).

## 6. Unresolved policies

- **U1** If cancellation is added, when does the freed ticket become available again? — Owner: **Claire**. Unresolved.
- **U2** If a waiting list is added, does the first person on the list get the freed ticket, or whoever books next? — Owner: **Claire**. Unresolved.
- **U3** Is one ticket per customer per concert permanent or only for version one? — Owner: **Claire**. Unresolved.
- **U4** Which booking details may support worker Daniel see? — Owner: **Claire**. Unresolved.

None of these is promised as a feature.

## 7. Three functional needs

| Need | Start | Action | Visible result | Saved data |
|---|---|---|---|---|
| **F1 Availability** | Friday: 18 confirmed / 20 | Emma opens Friday | "2 tickets available" | No change (18) — a snapshot, not a reservation |
| **F2 Book** | Friday: 19/20; Alex has no Friday booking | Alex taps Book | "Confirmed — B17 — Friday" | B17 (Alex, Friday, Confirmed) added; count 20 |
| **F3 Check status** | B17 saved, email status `pending` | Alex opens My bookings | "B17 — Friday — Confirmed — email on its way" | No change; no new booking |

## 8. Booking rules

- **R1 Capacity:** for each concert, confirmed bookings must never exceed that concert's capacity.
- **R2 One per customer:** a customer has at most one confirmed booking per concert; a repeat request returns the existing booking.

**Sold-out example:** Start: Friday has 20 confirmed bookings for 20 tickets. Action: Emma taps Book. Result: show *Sold out*; save no new booking; the count stays 20.

**Last-ticket check:** Start 19/20; Alex and Emma send overlapping requests → exactly one *Confirmed*, one *Sold out*; final count 20 (never 21).

**Repeat check:** Alex already has B17; he taps Book again → shown "Confirmed — B17 — Friday"; no second Friday booking.

## 9. Three quality concerns

| Quality | Condition | Required outcome | Proposed check |
|---|---|---|---|
| Accessibility | Keyboard only | Choose Friday, activate Book, read the result; visible focus throughout | Complete the path with Tab/Enter when a UI exists; record blocked steps |
| Recovery | Reply lost or email fails after saving | Customer still finds the saved booking and email status; retries create no duplicate | Simulate lost reply + email failure later; inspect screen, saved bookings, email status |
| Response time | Agreed concurrent load in a stated environment | Result within an agreed time — load and target **to agree** | Measure request-to-result time; record load and environment |

No result has been measured.

## 10. Context sketch

```
Customer         -> Ticket app       : view availability / book / check my booking
Ticket app       -> Customer         : availability / Confirmed + ref / Sold out / Checking your booking
Organiser Claire -> Ticket app       : request confirmed-booking list for a concert
Ticket app       -> Organiser Claire : confirmed bookings for that concert
Support Daniel   -> Ticket app       : look up a reported booking ref (e.g. B17)
Ticket app       -> Support Daniel   : saved booking + email status (access policy U4 to agree)
Ticket app       -> Email provider   : send confirmation for a saved booking
Email provider   -> Ticket app       : delivery result: sent / failed
```

Diagram version: [Context.md](Context.md).

## 11. Five business terms

- **Capacity** — maximum confirmed bookings for one concert (Friday: 20).
- **Concert** — one event at a stated date/time with its own capacity and bookings.
- **Confirmed booking** — a saved record giving one customer entry to one concert; not the same as an email being delivered.
- **Sold out** — confirmed bookings have reached capacity; Book shows *Sold out* and saves nothing.
- **Cancellation** — a possible future action ending a booking entitlement; excluded from version one; release policy unresolved (U1, owner Claire).

## 12. Team responsibilities

I completed P01 individually, so I drafted and self-checked every part (scope, needs, rules,
quality concerns, context sketch, glossary, tool checklist, evidence index, ADR). A classmate
cross-check of the sold-out and last-ticket requirements is planned and will be recorded only
after it happens. The reflection is my own. Details: [Team.md](Team.md).

## 13. Tool-access checklist

| Tool | Status | Actually checked | Owner | Next action |
|---|---|---|---|---|
| Editor | Available | opened, edited, saved these files | Jasur | — |
| Git | Available | portfolio repository created, P01 committed | Jasur | confirm submission remote with teacher |
| macOS | Available | terminal runs commands | Jasur | process question for P02 |
| Linux | Not checked | no Linux machine/VM used yet | Jasur | ask if labs need it; set up a VM if so |
| Windows | Not checked | not used for this course | Jasur | ask if any lab requires it |
| Database (PostgreSQL) | Not checked | no connection attempted | Jasur | ask for lab version before installing |
| C#/.NET | Not checked | nothing installed; assumption only | Jasur | confirm course runtime |

## 14. Peer feedback and limits

- **Before:** "When Friday is full, show Sold out."
- **After:** "When Friday has 20 confirmed bookings for 20 tickets and Emma taps Book, show *Sold out*, save no new booking and keep the confirmed count at 20."
- **Why:** the original did not say whether a booking is saved or what the count should be, so a reader could not tell whether the rule was broken.
- **Label:** **Observed** — the revision was actually made (own check). A classmate cross-check is **Proposed** and not yet done ([Peer-review.md](Peer-review.md)).
- **Limit:** a revised plan, not a tested app; the last-ticket behaviour is specified but no protection mechanism exists yet.

## 15. Individual reflection

I drafted the scope, the three needs, the capacity and duplicate rules with their examples, the
quality concerns and the evidence index. The rule I can explain: a concert can never hold more
confirmed bookings than its capacity, so at 20/20 Book shows *Sold out* and saves nothing — and
when two requests both saw "1 available", only one may be saved. My uncertainty: which mechanism
keeps the check and the save together so the second request sees the new count. Next goal: in
P02, learn how a process holds temporary working data and why it differs from a saved booking.
