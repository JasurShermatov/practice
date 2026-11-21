# Pair work and peer review — to do by the student

Pair work, role swaps and the worksheet swap happen in class with a real partner. Nothing here has happened yet;
this file prepares it. Record results only after they happen (**Observed**), never in advance.

## Roles (lab guide "Materials and roles", Step 8)

| Item | Record |
| --- | --- |
| Partner name | *to fill in* |
| My first role (Operator / Observer) | *to fill in* |
| Swap after process inspection done? | *to fill in (yes/no)* |
| Step 8 swap: former Observer ran one command and explained what the parent waits for | *to fill in — expected explanation: "the parent is blocked in wait() until the child exits"* |

## Worksheet swap checklist (Step 8 / §37)

Check the partner's sheet (and ask them to check mine) for:

- [ ] platform and tool named; observed / supplied / simulated labels on every value
- [ ] an actual PID **and** PPID, matching the run (not the sample's 42190/42188)
- [ ] memory and CPU values with column names and units (VSZ/RSS KiB, %CPU vs CPU seconds)
- [ ] a complete boundary path: user mode → OS interface → kernel/filesystem → return; one user-mode calculation; what survives exit
- [ ] lifecycle with a named event on every arrow and **blocked → ready → running** (not blocked → running)
- [ ] fork / exec / wait vs CreateProcess, with the POSIX trace labelled if it was not run
- [ ] changed-code prediction written *before* the run, then the result and the file contents
- [ ] runtime ADR with limits (not "C# is faster because of this lab")

## Corrections

| Direction | Specific correction | Applied? |
| --- | --- | --- |
| I give my partner | *to fill in after reading their sheet* | |
| My partner gives me | *to fill in* | |

## My own pre-check (Observed — self-review of this folder)

- The first draft of my boundary diagram said "no system call during the CPU phase" based on a *filtered* strace.
  That did not prove it, so I reran strace with all system calls (E3) before keeping the claim.
- I first expected `Popen` to show `fork()`; the trace showed `vfork()` + `execve()`, so the worksheet now says
  "Popen is not always fork".
