# ADR-002 — Provisional backend runtime for the lab-seat enrollment project

**Status:** Proposed (provisional) · Practice P02 · Evidence label: **Proposed** — nothing in this decision has been
built or measured.

## Context and requirement

The course's fictional enrollment system lets students reserve lab seats while the registrar needs accepted bookings
to stay within capacity. The requirement for *this* decision is narrow: **every team member must be able to build,
run and inspect the backend locally on their own laptop**, and the laptops are mixed — Windows, macOS (Intel and Apple
Silicon) and Linux.

P02 showed why this matters: one portable Python call (`subprocess.Popen` + `wait`) became `vfork` + `execve` +
`wait4` on Linux, would be `fork`/`posix_spawn` variants on macOS, and `CreateProcess` + handle waits on Windows. A
runtime that hides those differences behind one library — and a toolchain that installs the same way on all three
systems — reduces "works on my machine" problems.

## Options considered

1. **C#/.NET** (current LTS SDK) — the course's current provisional route.
2. **Java** (current LTS JDK, e.g. with Maven or Gradle) — acceptable only if the lecturer agrees.

Python (my strongest language, used for this lab) is *not* an option in this decision: the lab used it as an
experiment tool, not as the enrollment backend.

## Decision

Provisionally choose **C#/.NET**, the course's current planning route. Java remains the documented alternative.

## Reasons

- One cross-platform SDK and CLI (`dotnet new / build / test / run`) with the same project file on Windows, macOS
  and Linux — the same commands can go into the team README for every laptop.
- Alignment with the course: examples, teacher support and marking follow the provisional C#/.NET route.
- The standard library covers what the future backend needs (HTTP APIs, async I/O, process and file APIs that
  abstract the OS differences seen today, data access).

## Evidence and what it does not show

| Evidence | Label | Limit |
| --- | --- | --- |
| Course context: C#/.NET is the provisional route | Supplied (course materials) | Planning statement, not a test on our laptops |
| Vendors publish .NET SDKs and Java JDKs for Windows, macOS and Linux | Proposed (to re-verify for the exact versions we would pin) | Availability ≠ every team laptop can install it |
| P02 lab: process creation differs per OS | Observed (Linux) | A tiny Python process is **not** a benchmark of either runtime |
| Linux container used for P02 had OpenJDK 21 and no .NET SDK | Observed | The container is not a team laptop; irrelevant to the choice |

## Unknowns to check before committing

1. Each team member installs the pinned SDK and runs a "hello API" skeleton on their own OS (macOS Apple Silicon,
   Windows, Linux) — record the result as Observed per laptop.
2. Target deployment environment (university server, container host, OS) and which runtime it supports.
3. Lecturer agreement and course support if the team prefers Java.
4. Database driver, migration and test tooling for the enrollment storage on all three OSes.
5. IDE/debugger per OS (Visual Studio is Windows-only; Rider and VS Code are cross-platform) and the team's experience.

## Consequences

- **Easier:** identical build/test commands on every laptop; course-aligned examples; one dependency manager (NuGet).
- **Harder / trade-off:** members whose main language is not C# (I mainly use Python) must learn it; tooling is
  strongest on Windows, so macOS/Linux members depend on the CLI or cross-platform IDEs; the choice stays unproven
  until the skeleton runs everywhere.
- Capacity correctness ("never more than 20 accepted bookings") is **not** decided by the runtime; it needs later
  concurrency and database evidence.

## When to reconsider

If any team laptop or the deployment target cannot run the pinned .NET SDK, if the lecturer agrees Java fits the
team better, or if the skeleton check in "Unknowns" fails.

## Supporting mini decision — the parent waits synchronously

`parent.py` calls `child.wait()` before reporting, because the value it reports (the exit code) only exists after the
child has terminated; the blocking wait also reaps the child so no zombie is left. Trade-off: the parent can do nothing
else while it waits — fine for one helper child, not for a server that must keep answering requests.
