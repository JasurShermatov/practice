# Peer feedback and limits

## 1. Revision of the sold-out requirement (own check)

Method: read the requirement as someone who has not seen the plan and try to retell the start,
the action, the visible message and the saved-data result. Anything that cannot be retold is
unclear.

| | |
|---|---|
| **Before** | "When Friday is full, show Sold out." |
| **Problem found** | It does not say whether another booking is saved, what "full" means, or what the count should be afterwards — a reader could not decide whether the rule was broken. |
| **After** | "When Friday has 20 confirmed bookings for 20 tickets and Emma taps Book, show *Sold out*, save no new booking and keep the confirmed count at 20." |
| **Why it changed** | The new sentence names the starting count, the customer action, the visible result and the saved-data result, so two readers would agree on pass/fail. |
| **Evidence label** | **Observed** — this revision was actually made; it is a change to a plan, not a test of a booking app. |
| **Limit** | No application exists, so the requirement itself is still **Proposed**; the overlapping-request behaviour is specified but no protection mechanism exists yet. |

## 2. Classmate cross-check

| | |
|---|---|
| **What** | A classmate retells the revised sold-out requirement and the last-ticket example without help. |
| **Evidence label** | **Proposed** — not done yet. |
| **Record afterwards** | Reviewer's name, the exact phrase they found unclear, their suggestion and the sentence changed as a result. |

## 3. Second revision (own check)

| | |
|---|---|
| **Before** | "Show the booking after a timeout." |
| **After** | "If the reply is lost, show *Checking your booking…*, then show the saved booking from My bookings; never say *nothing was booked* just because no reply arrived." |
| **Reason** | A timeout only means the caller stopped waiting; it does not prove the booking failed (L01 §19, "Saved booking, lost reply"). |
| **Evidence label** | **Observed** — revision made to the plan. |
