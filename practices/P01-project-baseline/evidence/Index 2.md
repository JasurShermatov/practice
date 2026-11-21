# Evidence index

| ID | Label | Requirement | Action | Expected outcome | Actual outcome | Environment | Limitation |
|---|---|---|---|---|---|---|---|
| E1 | **Proposed** | R1 sold-out | Start at 20/20, Emma taps Book | "Sold out"; no new booking; count 20 | Not run | Not applicable yet | A plan cannot show that an implementation works. |
| E2 | **Proposed** | R1 last ticket | Start at 19/20, Alex and Emma send overlapping Book requests | One "Confirmed", one "Sold out"; final count 20 | Not run | Not applicable yet | No protection mechanism chosen; investigated in later practices (P09–P12). |
| E3 | **Proposed** | R2 repeat | Alex (has B17) taps Book again | B17 returned; no second booking | Not run | Not applicable yet | Repeats from retries/other tabs need a server-side check, not only a disabled button. |
| E4 | **Proposed** | R3 email failure | Email provider returns *failed* after B17 is saved | B17 stays Confirmed; email status `failed`; screen shows "email not sent yet"; retry creates no booking | Not run | Not applicable yet | Retry policy (how often, how long) not decided. |
| E5 | **Simulated** | R1 (why protection is needed) | Classroom unsafe model: start 19; Alex reads 19; Emma reads 19; Alex saves; Emma saves | Required: count must stay ≤ 20 | Model reaches **21** for 20 tickets — R1 broken | Paper model from L01/P01 | A simplified model, not an observation of a real database. |
| E6 | **Observed** | Sold-out requirement wording | Own check: retell start/action/visible/saved result | Every part retellable | Sentence rewritten to include saved result and final count (Peer-review.md §1) | Document revision | Change to a plan only; no app behaviour observed. |
| E7 | **Proposed** | Sold-out + last-ticket wording | Classmate cross-check (Peer-review.md §2) | Classmate retells both without help | Not done yet | Document review | Will be recorded only after it happens. |

No executable booking application or concurrency test exists in this baseline.
