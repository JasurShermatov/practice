# Ticket-app project scope

## Problem in our words

Claire runs concerts and receives booking requests as chat messages. Because every reply is
written by hand, she cannot be sure who actually holds a ticket, and customers cannot check
their result without asking her again. We are planning a small ticket app in which a customer
can see whether tickets remain, book one ticket and later find the same saved booking, while
Claire sees an accurate list of confirmed bookings for each concert.

## People and needs

Each line names a person, the action they take and the result they need.

| Person | Action | Result they need |
|---|---|---|
| **Customer** (Alex, Emma) | opens a concert and taps **Book** | an honest answer — *Confirmed* with a booking reference, or *Sold out* — that matches what is saved |
| **Customer** (Alex) | reopens **My bookings** later, or after a lost reply | the same saved booking (e.g. B17) with its status; looking does not create a new booking |
| **Organiser** (Claire) | opens the confirmed-booking list for Friday | a list that matches the saved confirmed bookings exactly, never more than capacity |
| **Support worker** (Daniel) | looks up a booking reference a customer reports | the saved booking and its email status, so he can explain an unclear result without creating another booking |

## First-version scope

**Included in version one**

1. See a concert and its current availability (a snapshot, not a promise).
2. Book one ticket and receive a clear result: "Confirmed" + reference, or "Sold out".
3. Check the status of a saved booking in **My bookings**.

**Excluded from version one** (later decisions, not silently included)

- payment
- cancellation and refunds
- waiting list for sold-out concerts
- numbered seats
- more than one ticket per customer per concert

## Unresolved policies

These are business decisions. A tool or a developer cannot answer them; **Claire** (the
fictional organiser) owns them. Each stays *unresolved* until she answers.

| # | Question | Why it matters | Owner | Status |
|---|---|---|---|---|
| U1 | If cancellations are added later, when does a cancelled ticket return to availability — immediately, or after Claire approves it? | The capacity rule needs to know when the confirmed count goes down. | Claire | Unresolved |
| U2 | If a waiting list is added, who gets a freed ticket first — the earliest person on the list, or whoever books next? | Decides whether a freed ticket is offered or simply becomes available. | Claire | Unresolved |
| U3 | Is "one ticket per customer per concert" permanent, or only for version one? | A multi-ticket policy would change the duplicate rule and the meaning of a repeat request. | Claire | Unresolved |
| U4 | What may support worker Daniel see about a customer's booking (name, email, status)? | Access to personal data needs an agreed policy before it is designed. | Claire | Unresolved |
