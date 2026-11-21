# P01 — Course introduction workshop and project baseline

**Session:** Saturday 10 October 2026, 09:30–10:50 (Asia/Tashkent) · Practice · Group 23-309 SW
**Related lecture:** L01 — Course introduction: the subject, learning roadmap and expectations
**Type of work:** planning and review only. P01 requires no code and no installation.

## Goal

Turn the course brief into a readable **project baseline** for the fictional ticket app that
another pair can review: who needs the app, what it must do, which rules must always hold,
which qualities matter, who it talks to and what our words mean.

## Brief and classroom assumptions

Claire organises concerts and currently takes ticket requests through chat messages, so she
cannot keep an accurate list of who has a ticket. She needs an app where customers can see
availability, book a ticket and later check their saved result.

- 20 unnumbered tickets per concert
- one confirmed booking per customer per concert
- no payment, cancellation or waiting list in version one

These are classroom assumptions from the brief, not requirements confirmed by a real organiser.

## Contents

| Worksheet field | Where it is answered |
|---|---|
| Programming / SQL / Computer starting point, learning goal | [Worksheet.md](Worksheet.md) §1–4 |
| People, needs and first-version scope | [Scope.md](Scope.md) |
| Unresolved policies | [Scope.md](Scope.md#unresolved-policies) |
| Three functional needs | [Requirements.md](Requirements.md#three-functional-needs) |
| Booking rules (capacity, duplicate, sold-out example) | [Requirements.md](Requirements.md#booking-rules) |
| Three quality concerns | [Requirements.md](Requirements.md#three-quality-concerns) |
| Context sketch | [Context.md](Context.md) |
| Five business terms | [Glossary.md](Glossary.md) |
| Team responsibilities | [Team.md](Team.md) |
| Tool-access checklist | [Tool-access.md](Tool-access.md) |
| Peer feedback and limits | [Peer-review.md](Peer-review.md) |
| Evidence index | [evidence/Index.md](evidence/Index.md) |
| Optional design decision (ADR) | [decisions/ADR-001-one-app-three-modules.md](decisions/ADR-001-one-app-three-modules.md) |
| Individual reflection | [reflections/Jasur-Shermatov.md](reflections/Jasur-Shermatov.md) |

[Worksheet.md](Worksheet.md) also contains every worksheet answer in one file, in the same order
as the online P01 worksheet, so it can be copied into the signed-in worksheet field by field.

## Self-check before submission

- [x] Every functional need has start, action, visible result and saved-data result
- [x] Capacity and duplicate rules name the concert and can be checked against an example
- [x] Quality concerns name a condition, an outcome and a proposed check; numbers are "to agree"
- [x] Context sketch: every arrow has a direction and a message label
- [x] "Confirmed" means the same thing (a saved booking) in every file
- [x] Unresolved policies stay unresolved and name Claire as the decision owner
- [x] Evidence is labelled proposed / simulated / observed; nothing claims a tested app
- [ ] Classmate cross-check of the sold-out requirement (Peer-review.md §2) — to do by the student
- [ ] Submit answers in the online P01 worksheet — to do by the student
