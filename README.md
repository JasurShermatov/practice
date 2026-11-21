# Advanced Software Design & Architecture — practice portfolio

PDP University · Pearson BTEC Level 6 · Unit 3 (70727U)
Student: Jasur Shermatov · Group: 23-309 SW

This repository holds my practice work for the course. Every practice lives in its own folder
and builds on the same fictional project from the course brief: a small **concert ticket-booking
app** for organiser Claire (20 unnumbered tickets per concert, one ticket per customer, no
payment in version one).

From P03 on, the practices also grow one Python codebase, [hotel-booking/](hotel-booking), for a
separately introduced fictional hotel (rooms R7 and R8, one guest per room per night).

| Practice | Topic | Folder | Status |
|---|---|---|---|
| P01 | Course introduction workshop and project baseline | [practices/P01-project-baseline](practices/P01-project-baseline) | Done |
| P02 | OS introduction, kernels and process lifecycle | [practices/P02-os-process-lifecycle](practices/P02-os-process-lifecycle) | Done (Linux observed; macOS rerun, pair review and online submission to do) |
| P03 | Hotel booking domain and UML workshop (starts the [hotel-booking](hotel-booking) codebase) | [practices/P03-hotel-domain-uml](practices/P03-hotel-domain-uml) | Done (pair review and partner hand-over: to do by the student) |
| P04 | Refactor a reservation design (SOLID: storage and notification behind protocols; hotel-booking version 2, R6, SMS) | [practices/P04-refactor-reservation](practices/P04-refactor-reservation) | Done (8 unittest / 82 total tests observed; macOS rerun, pair work and partner hand-over: to do by the student) |
| P05 | Hotel domain and context boundaries (quality scenarios S1–S6, ubiquitous language, four bounded contexts, rule owners, context map, borders; design only, no code change) | [practices/P05-domain-context-boundaries](practices/P05-domain-context-boundaries) | Done (26 document checks observed; docs copied into hotel-booking/docs at the start of P06; pair work and partner hand-over: to do) |
| P06 | Modular-monolith architecture review (hotel-booking version 3: four modules with public contracts and internal code, `Confirmation` message, Payments contract, wiring in `main.py`; border contracts in `.importlinter` enforced by a stdlib `ast` test, broken on purpose and restored; ADR-001; "Modules" page; architecture review) | [practices/P06-modular-monolith-review](practices/P06-modular-monolith-review) | Done (8 unittest / 118 total tests, 3 contracts kept, red/green border demo observed; `lint-imports` on the Mac, draw.io check and pair work: to do by the student) |

## How to read the evidence

Evidence claims (checks, models and results) carry one of three labels, as agreed in L01/P01:

- **Proposed** — a plan or a check we intend to run. Nothing has been executed.
- **Simulated** — the result of a classroom model or thought experiment, not a running system.
- **Observed** — a result recorded after actually running something, with its environment.

Numeric quality targets that have not been agreed are written as **to agree**. A target is never
reported as met before a test has produced an observed result.
