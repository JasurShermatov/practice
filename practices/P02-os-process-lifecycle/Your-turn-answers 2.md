# P02 "Your turn" prompts and short cases — my answers

Answers to every "Your turn" prompt in the P02 explanation (numbers = section numbers), plus the lifecycle
simulator sequence. Where my lab run gives evidence, it is cited (labels as in [evidence/Index.md](evidence/Index.md)).

| § | Prompt | My answer |
| --- | --- | --- |
| 1 | When you double-click an app, what might it need from the computer? | CPU time to run its instructions, RAM for working values, files read from storage (its program and settings), the display/keyboard for I/O, maybe the network — all granted and shared by the OS. |
| 2 | Which parts of your worksheet come from observing, which explain? | Observed: terminal transcript, PIDs, `ps`/`/proc` values, strace lines, file contents. Explanation: lifecycle states and transitions, "blocked on input", Windows behaviour, the ADR. |
| 3 | Which resources are involved when you open a saved text file? | Storage device (via filesystem and driver), RAM (buffers/page cache and the app's copy), CPU (to run the app and kernel code), display for output. |
| 4 | Does seeing three open apps prove all three execute at the same instant? | No. Open ≠ running; on one core they take turns (concurrency); only with several cores can some run in parallel, and most open apps are usually sleeping. |
| 5 | Why should an app not decide by itself that it owns all the RAM? | Other processes and the OS need memory too; the OS must allocate and protect memory so one app cannot starve or overwrite others. |
| 6 | Does the kernel know our rule "no more than 20 accepted bookings"? | No. It checks privileges and resources, not business rules — the capacity rule belongs to the application and database. |
| 7 | Where does the supplied Python script run? | Inside a Python interpreter process (`python3`) in user mode, started by the shell; the kernel only provides services to it. |
| 8 | One child.py file, two started copies: how many files and processes? | **One file and two processes.** |
| 9 | Why is "I saw Python" incomplete evidence? | Several Python processes can exist; without the PID (and PPID, time, command line) you cannot prove it was the lab child. My `ps` showed two `python3` processes (521 and 525). |
| 10 | Does separate memory alone stop two processes saving bookings for the same final seat? | No. Isolation protects private memory; coordinating writes to shared storage needs application/database mechanisms (transactions, constraints, locks). |
| 11 | Does calculating 2 + 3 necessarily require a system call? | No — it runs in user mode on values in memory. My child's 0.75 s loop made no system call at all (E3). |
| 12 | Does entering the kernel always mean a different process is scheduled? | No. A system call is a mode change and usually returns to the same process (e.g. my `write(3, …) = 114`). Only if it must wait (like `read(0)`) may another process be scheduled. |
| 13 | A key arrives while a process waits for input. Must it instantly run? | No. It becomes ready; it runs when the scheduler dispatches it. |
| 14 | Does "hybrid" mean half Windows and half Linux? | No. It describes a kernel design mixing monolithic and microkernel ideas (Windows NT, macOS XNU), not mixing products. |
| 15 | Child asked for keyboard input, none available — which state? | **Blocked**, because input has not arrived (my snapshot: `S+`, `wait_woken`). |
| 16 | After an I/O event completes, why draw blocked → ready before running? | The event only removes the reason to wait; the process still needs the scheduler to give it a CPU, which may be busy. |
| 17 | Does a context switch automatically save an unsaved document to disk? | No. It saves CPU registers/execution context in kernel memory so execution can resume; a document is saved only by an explicit file write. |
| 18 | At the input prompt, what is each process waiting for? | Child: a line of terminal input (Enter). Parent: the child's termination (`wait()`, `do_wait`). |
| 19 | Which extra event is needed after input arrives? | A scheduler **dispatch** (ready → running). |
| 20 | Where does "reject the 21st accepted booking" belong on this path? | Not in the OS path at all: in the application's booking logic and the database (constraint/transaction), before anything is written. |
| 21 | Large virtual size and smaller resident figure — is the tool wrong? | No. Virtual size counts mapped/reserved address space; resident counts pages currently in RAM (mine: VSZ 37348 KiB vs RSS 13764 KiB). |
| 22 | Can Windows handle 12 and Linux fd 12 be treated as equivalent? | No. Both are process-local identifiers with different APIs and contracts; the numbers are meaningless outside their process and OS. |
| 23 | Why keep the child at its prompt during inspection? | So the process still exists (and is in a stable waiting state) while I look it up; after Enter it exits within milliseconds and the PID is gone. |
| 24 | What should you write if your tool exposes no virtual-size column? | "unavailable" plus the reason (e.g. "Task Manager Details has no VSZ column by default"), never an invented number. |
| 25 | Can a Linux PID from WSL2 be looked up as the same Windows PID in Task Manager? | No. WSL2 runs a separate Linux kernel in a VM; its PIDs are a different namespace from Windows PIDs. |
| 26 | If fork returns 0, are you in the parent or child? | In the **child** (the parent gets the child's PID). |
| 27 | Parent 4100 forks child 4101, which execs a new program. New program's PID? | **4101** — exec replaces the program, not the process (observed: PID 821 stayed 821, E4). |
| 28 | Does a waiting parent imply its child must also be waiting? | No. The child can be running (my child ran its CPU loop while the parent was already in `wait4`). |
| 29 | Can you run os.fork unchanged on Windows because Python is cross-platform? | No. `os.fork` does not exist on Windows; Python is cross-platform only where it offers portable APIs such as `subprocess`. |
| 30 | What proves the parent's final report follows the child's termination? | `wait()` cannot return before the child ends: strace shows `+++ exited with 7 +++` before `wait4 … = 714`, then the parent's print (E2). |
| 31 | Process has all its input but another task uses the only core: ready or blocked? | **Ready**. |
| 32 | Must the parent's first print appear before the child's first print? | No. Only explicit dependencies (like `wait`) order events; separate prints can interleave differently between runs. |
| 33 | What should the arrow blocked → ready say for the parent? | "child terminated (exit status available)" — the event that completes its `wait()`. |
| 34 | What evidence is still missing before selecting a production runtime? | A skeleton backend running on every team laptop, the deployment target's supported runtime, lecturer agreement (for Java), DB/tooling support, and later load/concurrency evidence — see ADR-002. |
| 35 | What should the parent report after changing the exit code to 0? | "child exit code was 0" and nothing about non-zero; the file is still written (observed, E6). |
| 36 | Which distinction was hardest to explain without another unfamiliar term? | Ready vs blocked: it is easy to say "waiting" for both. I now ask: is a CPU missing (ready) or an event missing (blocked)? |
| 37 | One specific correction for a partner | *To do with my partner.* Prepared check: "your lifecycle arrow goes blocked → running; add ready and label the dispatch" (see [Peer-review.md](Peer-review.md)). |
| 38 | Four-sentence explanation using the lab | See [reflections/Jasur-Shermatov.md](reflections/Jasur-Shermatov.md) and Worksheet Appendix A §8. |

## Lifecycle simulator (§19) — Simulated

The interactive simulator is in the online presentation; *running it is to do by the student*. The sequence I will enter:
create → (new → ready) · dispatch → (ready → running) · request input → (running → blocked) · deliver input →
(blocked → ready) · dispatch → (ready → running) · exit → (running → terminated). Expected rejection: "deliver input"
while the process is **ready** is invalid, because only a blocked process is waiting for input. This is a model of one
execution path, not an observation of my laptop.

## Presentation quiz (Step 8)

*To do by the student* in the interactive presentation. The short-case answers above (§8, 15, 26, 27, 31) are my prepared reasoning.
