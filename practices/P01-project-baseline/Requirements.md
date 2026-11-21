# Ticket requirements and rules

All examples use the fictional Friday concert (capacity 20). Booking references such as B17 are
invented identifiers (not sequence numbers). Everything here is **Proposed**: it specifies the required result; no
application has been built or tested in P01.

## Three functional needs

Each need states the starting situation, the customer action, the visible result and what
happens to saved data.

### F1 — View availability

| | |
|---|---|
| **Start** | Friday has 18 confirmed bookings for 20 tickets. |
| **Action** | Emma opens the Friday concert. |
| **Visible result** | "2 tickets available". |
| **Saved data** | No change — still 18 confirmed bookings. |

Note: availability is information *at that moment*. It does not reserve a ticket for Emma, and
a later Book request may still receive *Sold out*.

### F2 — Book one ticket

| | |
|---|---|
| **Start** | Friday has 19 confirmed bookings for 20 tickets; Alex has no Friday booking. |
| **Action** | Alex taps **Book** for Friday. |
| **Visible result** | "Confirmed — B17 — Friday". |
| **Saved data** | One booking B17 (Alex, Friday, Confirmed) is added; the confirmed count becomes 20. |

### F3 — Check a saved booking

| | |
|---|---|
| **Start** | B17 is saved for Alex and Friday as Confirmed; its email status is `pending`. |
| **Action** | Alex opens **My bookings**. |
| **Visible result** | "B17 — Friday — Confirmed — email on its way". |
| **Saved data** | No change. Viewing never creates a booking; the count stays 20. |

## Booking rules

A rule (invariant) is a condition that must remain true every time a booking is accepted. The
rules state *what* must stay true; they do not yet choose a mechanism (lock, transaction, etc.).

### R1 — Capacity

> For each concert, the number of confirmed bookings must never exceed that concert's capacity.

The rule belongs to one concert: a Friday booking never uses Saturday's capacity, and if a
concert's capacity were 30 (hypothetical; the class assumes 20) the limit would be 30.

**Sold-out example (check for R1)**

| | |
|---|---|
| **Start** | Friday has 20 confirmed bookings for 20 tickets; Emma has no Friday booking. |
| **Action** | Emma taps **Book** for Friday. |
| **Visible result** | "Sold out". |
| **Saved data** | No new booking; the confirmed count stays 20. |

**Last-ticket example (check for R1 under overlapping requests)**

| | |
|---|---|
| **Start** | Friday has 19 confirmed bookings for 20 tickets; neither Alex nor Emma has a Friday booking. |
| **Action** | Alex and Emma tap **Book**; Emma's request arrives before Alex's has finished. |
| **Visible result** | Exactly one of them sees *Confirmed* with a reference; the other sees *Sold out*. |
| **Saved data** | Exactly one new confirmed booking; the final count is 20, never 21. |

### R2 — One booking per customer per concert

> A customer has at most one confirmed booking for a given concert (version-one policy, see U3).

**Repeat-request example (check for R2)**

| | |
|---|---|
| **Start** | Alex already has B17 (Friday, Confirmed). |
| **Action** | Alex taps **Book** for Friday again (double tap, second tab or retry). |
| **Visible result** | The existing booking: "Confirmed — B17 — Friday". |
| **Saved data** | No second Friday booking for Alex; the count is unchanged. |

R2 applies to any new request from the same customer for the same concert, not only to a
repeated click, because repeats can also come from a refresh, another tab or a network retry.

### R3 — Meaning of *Confirmed*

> *Confirmed* means a saved booking that gives one customer entry to one concert. It does not
> mean that an email was delivered; email delivery has its own status.

**Email-failure example (check for R3)**

| | |
|---|---|
| **Start** | B17 is saved as Confirmed with email status `pending`; the email provider is unavailable. |
| **Action** | The app sends the confirmation email; the provider returns *failed*. Alex opens **My bookings**. |
| **Visible result** | "B17 — Friday — Confirmed — email not sent yet, we will try again". |
| **Saved data** | B17 stays Confirmed; its email status changes `pending` → `failed`. A later retry sets it to `sent` or keeps `failed`; it never creates or removes a booking. |

**Lost-reply example (check for R2 and R3)**

| | |
|---|---|
| **Start** | Friday has 19 confirmed bookings; Alex has none. |
| **Action** | Alex taps **Book**; the server saves B17, but the reply never reaches his phone (timeout). |
| **Visible result** | "Checking your booking…", then "B17 — Friday — Confirmed" from **My bookings**. |
| **Saved data** | B17 exists once. A timeout does not prove the booking failed, so the app must not tell Alex "nothing was booked". |

## Three quality concerns

Each concern names the condition, the required outcome and a proposed check. Numeric targets
that have not been agreed are marked **to agree**; nothing here has been measured.

| # | Quality | Condition | Required outcome | Proposed check |
|---|---|---|---|---|
| Q1 | **Accessibility** | A customer uses only the keyboard (no mouse). | They can choose Friday, activate **Book** and read the result, with a visible focus indicator at every step. | When a UI exists, complete the path with Tab/Enter only and record any step that cannot be reached. |
| Q2 | **Recovery / honesty after failure** | The reply to a Book request is lost, or email delivery fails after the booking is saved. | The customer can still find the saved booking and its email status; no duplicate booking is created by retrying. | Later, simulate a lost reply and an email failure, then inspect the screen, the saved bookings and the email status. |
| Q3 | **Response time** | An agreed number of customers request status/booking at the same time in a stated test environment. | The result appears within an agreed time. Load and target: **to agree** with the teacher / Claire. | Measure request-to-result time under that load and record load, environment and results. |

Performance is listed as a concern, not as a claim: the app does not exist yet, so we cannot
say it is fast.

## Requirement → rule → check traceability

| Requirement / example | Rule protected | Quality touched |
|---|---|---|
| F2 Book | R1, R2 | Q1, Q2, Q3 |
| Sold-out example | R1 | — |
| Last-ticket example | R1 | Q3 |
| Repeat-request example | R2 | Q2 |
| Email-failure example | R3 | Q2 |
| Lost-reply example | R2, R3 | Q2 |
| F1, F3 | (read-only, no change) | Q1, Q3 |
