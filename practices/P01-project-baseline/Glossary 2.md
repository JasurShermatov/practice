# Business glossary

One meaning per word, used the same way in Scope, Requirements, Context and the ADR.

| Term | Meaning in this project | Where it is used |
|---|---|---|
| **Capacity** | The maximum number of confirmed bookings allowed for one specific concert. Friday's capacity in our examples is 20. | Rule R1 |
| **Concert** | One event at a stated date and time. Each concert has its own capacity and its own bookings; Friday and Saturday never share tickets. | R1, R2 |
| **Confirmed booking** | A saved record that gives one customer entry to one concert, identified by a reference such as B17. It does **not** mean an email arrived — email delivery is a separate status. | R2, R3, F2, F3 |
| **Sold out** | The confirmed bookings for a concert have reached its capacity. A Book request then shows *Sold out* and saves no new booking. | R1, sold-out example |
| **Cancellation** | A possible future action that would end a customer's booking entitlement. **Excluded from version one**; when the ticket returns to availability is unresolved (policy U1, owner Claire). | Scope, U1 |

Supporting words used in the plan (not part of the required five):

- **Email status** — a separate field on a confirmed booking with exactly three values. It never changes whether the booking is Confirmed:

  | Value | Meaning | Customer sees |
  |---|---|---|
  | `pending` | not sent yet (first attempt not finished) | "email on its way" |
  | `sent` | the provider accepted the email | "email sent" |
  | `failed` | the last attempt failed; it will be retried | "email not sent yet, we will try again" |
- **Booking reference** — the identifier shown to the customer (B17) that support can look up.
- **Availability** — the number of tickets free *at the moment of viewing*; it is not a reservation.
