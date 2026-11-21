# P02 individual worksheet — process evidence and runtime ADR

**Name:** Jasur Shermatov  **Date:** Session 2026-10-10 (timetable); evidence below recorded 2026-11-21  **Operating system:** Linux (Ubuntu 24.04.5 LTS container, kernel 6.18, x86_64). macOS rerun: steps ready in [macOS-rerun.md](macOS-rerun.md), **not yet observed**.

**Pair partner:** *to fill in by the student*  **First role:** *to fill in by the student (Operator / Observer)*  **Role swap completed:** *no — to do by the student with the partner*

Evidence labels used in this sheet: **Observed** = I ran it and copied the real output (files in [evidence/](evidence/Index.md));
**Supplied** = the course's illustrative sample (`Captured-output.md`), never used as my evidence; **Inferred** = reasoning
from the code and observations, not something a tool displayed. Every observed run used `Python 3.13.18` and the
supplied, unmodified lab files unless the run name says otherwise.

## 1. Before running

1. In one sentence, what is the kernel responsible for in this exercise?

   The kernel creates the child process and gives it a PID, shares the CPU between processes, blocks the child while
   it waits for terminal input and the parent while it waits for the child, performs the protected file write for
   `output/child-result.txt`, and keeps the child's exit status until the parent's `wait()` collects (reaps) it.

2. Which program is the parent and which is the child? What is each one's job?

   `starter/parent.py` is the parent: it asks the OS to start `child.py` with the same Python runtime
   (`subprocess.Popen([sys.executable, "-u", child.py])`), prints the child's PID, waits with `child.wait()` and
   reports the exit code (and cleans up only its own child on Ctrl+C). `starter/child.py` is the child: it prints its
   PID/PPID, does a bounded CPU loop for `CPU_SECONDS` (0.75 s), waits at an `input()` prompt, writes synthetic labels to
   `output/child-result.txt` and exits with `EXIT_CODE` (7, intentionally non-zero).

3. Prediction before the first run: What will `wait()` make the parent do?

   The parent will print "child PID is …" and then stop making progress — blocked inside `wait()` — for the whole time
   the child computes and waits for Enter. Only after the child has exited will `wait()` return 7 and the parent print
   "wait() returned; child exit code was 7." and finish with its own status 0.
   *Result:* confirmed in run1 — the parent's report always appears after "CHILD: exiting with code 7." and the
   parent sat in the kernel function `do_wait` while the child waited (Observed, [run1-baseline.txt](evidence/run1-baseline.txt)).

### My execution-boundary diagram

Diagram: [diagrams/boundary.mmd](diagrams/boundary.mmd) (rendered: [boundary.svg](diagrams/boundary.svg)). Short form, with the system calls I
actually saw under `strace` ([strace-excerpt.txt](evidence/strace-excerpt.txt), Observed):

```text
 USER MODE (child process, PID 714 in the strace run)              | KERNEL MODE (privileged)
 ------------------------------------------------------------------+--------------------------------------------
 [CPU + working RAM] bounded_cpu_work(0.75): loop on values in RAM |
   -> 0.75 s with NO system call at all (all-syscall trace);      |
      stays in user mode                                           |
 OUTPUT_FILE.write_text("P02 synthetic ...")  (text built in RAM)  |
   -> Python io layer -> C library wrapper  == OS interface ====>  | syscall entry: openat(".../output/child-result.txt",
                                                                   |   O_WRONLY|O_CREAT|O_TRUNC) = 3   (path + permission check)
                                                                   | write(3, 114 bytes) = 114  -> VFS/filesystem copies
                                                                   |   the bytes into the page cache
                                                                   | close(3) = 0
   <============================ return (same process, same PID) == |
 "CHILD: wrote synthetic data to output/child-result.txt"          |   ... later: writeback to the [stored file] on disk
 exit_group(7) -> process memory released                          |   (a successful write() does not prove this happened)
 AFTER EXIT: `cat output/child-result.txt` reopens the stored file -> the saved labels are still there.
```

- **Calculation that stays in user mode:** the bounded loop (`count += 1` until the `perf_counter()` deadline) and
  building the text string. A trace of *all* system calls showed none during the 0.75 s CPU phase
  ([strace-cpu-phase-all-syscalls.txt](evidence/strace-cpu-phase-all-syscalls.txt)), and `/proc/<PID>/stat`
  showed `utime=75 ticks, stime=0` (0.75 s user CPU, 0 s kernel CPU) for the child in run1 (Observed).
  (Inferred: the clock read in `perf_counter()` is served in user space by the vDSO on Linux, which is why it does not appear as a system call.)
- **What survives process exit:** the stored file `output/child-result.txt` (and the exit status, until the parent
  reaps it). The child's working RAM — the `iterations` variable, the text it built, its stack — is released when it
  exits; the file is a separate object owned by the filesystem. Saving a file is not the same as preserving process memory.
- **Where the booking rule would belong:** not on this path. The kernel checks file permissions, not "no more than
  20 accepted bookings"; that rule belongs to the future application and database design.

## 2. Evidence while the child waited for input

All values: **Observed**, run1 ([evidence/run1-baseline.txt](evidence/run1-baseline.txt)), child waiting at
`CHILD: press Enter…`, Enter not yet pressed. Repeated in four further runs with the same pattern (Index: [evidence/Index.md](evidence/Index.md)).

| Field | Your observation or "unavailable" |
| --- | --- |
| OS and Python versions, observation time | Linux 6.18.44 x86_64, Ubuntu 24.04.5 LTS (container), Python 3.13.18 (`/usr/local/bin/python3`); 2026-11-21T11:07:04+05:00 |
| Observed / supplied / simulated | **Observed** (my run; Terminal A = tmux pseudo-terminal, Terminal B = second shell). macOS values: not yet observed |
| Command/tool used | `ps -o pid,ppid,stat,%cpu,vsz,rss,nlwp,comm -p 525`; `ps -o pid,ppid,stat,time,etime,args`; `ps --forest`; `/proc/525/status`, `/proc/525/stat`, `/proc/525/wchan`, `ls -l /proc/525/fd`; `lsof -p 525` (counts only) |
| Child PID | **525** (printed by the parent and by the child itself) |
| Parent PID or PPID | PPID **521** = the `parent.py` process; its parent is the shell, 515 (`ps --forest`: bash 515 → python3 521 → python3 525) |
| Process name | `python3` (command line: `/usr/local/bin/python3 -u …/lab/starter/child.py`) — the tool shows the interpreter, not `child.py` |
| CPU value shown (with unit if shown) | `%CPU 19.5` (ps: CPU time ÷ elapsed time since start, so it falls while waiting: 15.2 one second later); `TIME 00:00:00` (rounded to whole seconds); exact: `utime 75 + stime 0` clock ticks at `CLK_TCK=100` = **0.75 s** cumulative CPU |
| Virtual memory value, if your tool exposes it | `VSZ 37348` KiB (= `VmSize: 37348 kB`) |
| Working set/RSS (resident memory), if exposed | `RSS 13764` KiB (= `VmRSS: 13764 kB`) |
| Thread count, if exposed | `NLWP 1` (= `Threads: 1`) |
| Handles/open resources, if exposed | File descriptors 0, 1, 2 → `/dev/pts/0` (stdin/stdout/stderr inherited from the parent's terminal). `lsof`: 15 entries — 3 CHR (the terminal), 2 DIR (cwd, root), 10 REG (python3 binary and shared libraries, memory-mapped). Paths not copied |
| State/snapshot label, if exposed | `STAT S+` = interruptible sleep, in the foreground process group; `/proc` `State: S (sleeping)`; `wchan` = `wait_woken` (kernel function the child sleeps in). Parent 521: `S+`, `wchan do_wait` |
| Why the child could not continue | It called `input()`, which issues `read(0, …)` on the terminal; no line had been typed, so the kernel put it to sleep until terminal input arrives. In the strace run this single `read` lasted **4.203 s** (until I pressed Enter) |

**Observed vs inferred:** I *observed* a sampled `S+` / `wait_woken` snapshot, PID 525 with PPID 521, and a `read(0)`
that took 4.2 s to return; I *infer* from the code (`input()`) and those observations that the child was blocked
waiting for terminal input — the `S` label alone means "sleeping" and does not say which event it waits for or prove
every ready/running transition.

## 3. Lifecycle for this run

Diagrams: state diagram [diagrams/lifecycle.mmd](diagrams/lifecycle.mmd) ([svg](diagrams/lifecycle.svg)) and timeline
[diagrams/sequence.mmd](diagrams/sequence.mmd) ([svg](diagrams/sequence.svg)).

```text
new --Popen (vfork+execve)--> runnable/running --CPU phase 0.75 s, then input() finds no line--> waiting for terminal input
    --Enter pressed: input arrives--> runnable (ready) --scheduler dispatch--> running (write file)
    --return EXIT_CODE = 7 / exit_group(7)--> exited (zombie until collected) --parent wait() / wait4--> reaped by parent
```

The same line with the child's three explained transitions (Task 4):

| From | Event (label on the arrow) | To | Evidence type |
| --- | --- | --- | --- |
| new | `Popen` created it, PID 525 assigned, admitted | ready | Observed (PID printed; strace shows `vfork` + `execve`) |
| ready ↔ running | scheduler dispatch / timer preemption (can repeat many times during the 0.75 s loop) | running ↔ ready | Inferred — not visible in my tools |
| running | `input()` → `read(0)` with no line available | blocked (waiting) | Observed snapshot `S+`, `wait_woken`; read lasted 4.2 s |
| blocked | Enter pressed → terminal input arrives | ready | Inferred (the interval is too short to sample) |
| ready | scheduler dispatch | running | Inferred; next syscall `openat` at 11:07:45.347 shows it ran again |
| running | `return EXIT_CODE` → `SystemExit(7)` → `exit_group(7)` | exited | Observed (strace `+++ exited with 7 +++`) |
| exited | parent's `wait()` (`wait4`) collects status 7 | reaped | Observed (`wait4 … WEXITSTATUS(s) == 7`; PID gone from `ps` afterwards) |

The **parent's** separate story: running → blocked when it calls `wait()` (`wait4(525)`, `wchan do_wait`, 5.06 s in the
strace run) → ready when the child exits (event: child termination) → running → it prints the report and exits 0.
A waiting parent does not mean the child waits: the child was running its CPU loop while the parent was already blocked.

- Creation evidence (`Popen` or `fork`): parent printed `child PID is 525`; the child printed `PID=525 PPID=521`; `ps --forest`
  shows python3 521 → python3 525. Under strace, `Popen` appeared as `vfork()` = 714 followed by `execve("/usr/local/bin/python3", ["…", "-u", "…/child.py"])` in the new process — not a plain `fork()`.
- Event that made the child wait: `input("CHILD: press Enter…")` → `read(0</dev/pts/0>, …)` with no line typed yet.
- Event that let the child continue: I pressed Enter in Terminal A; `read` returned `"\n"` (1 byte) and the child became runnable again.
- Exit result reported by parent: `PARENT: wait() returned; child exit code was 7.` + `non-zero is intentional in this lab…`; the parent's own exit status was 0 (`echo $?` → 0).
- What "reaped by parent" means here: after `exit_group(7)` the child's memory is freed but the kernel keeps a small
  exit record (PID + status 7) — on POSIX a *zombie*. The parent's `wait()` (`wait4`) reads that status and lets the kernel
  delete the record, so PID 525 disappears (`ps -p 525` → no such process). I also observed a zombie directly in an
  extra run: a child that had exited before its parent called `wait()` showed `STAT Z`, and vanished after `wait()`
  ([extra-zombie-reaping.txt](evidence/extra-zombie-reaping.txt), Observed).

Terminal order caveat: printed order shows what reached my terminal; it does not prove the kernel's scheduling order.
The one ordering I can rely on is the explicit dependency: the parent's report comes after the child's termination
because `wait()` cannot return earlier.

### Windows and POSIX comparison

Diagram: [diagrams/creation-comparison.mmd](diagrams/creation-comparison.mmd) ([svg](diagrams/creation-comparison.svg)).

- **fork creates** a new child process that is a copy of the caller (separate address space, copy-on-write pages,
  inherited file descriptors) and both continue from the same call: the parent gets the child's PID, the child gets 0.
  **Observed** with `python3 starter/fork_exec_wait.py` ([run4-fork-exec-wait.txt](evidence/run4-fork-exec-wait.txt)):
  `parent PID=817 is about to fork` → `parent created PID=821`; under strace `clone(… SIGCHLD) = 919` (glibc's fork).
- **exec replaces** the program image inside that same process: PID 821 began as a copy of `fork_exec_wait.py`, then
  `os.execv` loaded `python3 -u child.py`. Evidence: the child printed `PID=821 PPID=817` — the PID created by fork, not a third one;
  in the trace `getpid()` returned 919 after `execve` in process 919. A successful exec does not return.
- **wait observes** the child's termination: `os.waitpid(821, 0)` blocked until the child exited and returned status 7
  (`FORK-DEMO: waited for PID=821; exit code=7`; `wait4` blocked 5.10 s in the traced run), and it reaped the zombie.
- **Windows `CreateProcess`** differs: there is no duplicate-and-continue step. The caller names the program and
  command line; Windows builds a *new* process from that executable together with its initial thread and returns
  process and thread **handles** plus IDs. The parent waits on the process handle (e.g. `WaitForSingleObject`), reads the
  code with `GetExitCodeProcess`, then closes its handles — Windows has no POSIX zombie/reaping vocabulary; the
  process object lives while handles to it are open. Python's portable `subprocess.Popen` uses `CreateProcess` on
  Windows, and on POSIX it chooses `fork`/`vfork`/`posix_spawn` internally (my Linux run showed `vfork` + `execve`), so
  `Popen` must not be described as "always fork". Windows has no `os.fork`, so `fork_exec_wait.py` exits early there.
- Label: the POSIX part is **Observed** on Linux (not macOS). The Windows part is **reasoned from the course notes**;
  I did not run Windows. On macOS the same `fork_exec_wait.py` can be rerun ([macOS-rerun.md](macOS-rerun.md)) — **not yet observed**.

## 4. Saved synthetic output

- Path you viewed: `lab/output/child-result.txt` (inside the lab folder; viewed with `cat output/child-result.txt` from `lab/`).
  Kept from my final run with the restored original code: [lab/output/child-result.txt](lab/output/child-result.txt); a copy of every run's file is in `evidence/*-child-result.txt`.
- List two labels/values in the file: run1 — `child_pid=525`, `parent_pid=521`, `requested_exit_code=7`
  (also `platform=Linux`, `cpu_iterations=8051900`). The PIDs match what `ps` showed, which ties the file to that run.
- Why is this safe for the classroom lab? It contains only synthetic, run-generated values (two PIDs, the OS name, a
  loop counter and the requested exit code) — no personal data, no student records, no typed input (`input()`'s
  text is discarded). It is written only inside the extracted lab folder, needs no administrator rights, and is
  overwritten on every run.

## 5. Controlled change

My change is recorded as patches: [lab/changes/01-exit-code-0.patch](lab/changes/01-exit-code-0.patch) and
[lab/changes/02-cpu-seconds-1.50.patch](lab/changes/02-cpu-seconds-1.50.patch). Afterwards I restored the supplied
values (7 and 0.75) and reran (run5) so the lab folder is back in its supplied state.

**Change A (required)**

- I changed: `EXIT_CODE`
- New value: `0` (was `7`)
- My prediction: the parent will report `child exit code was 0`, it will **not** print the "non-zero is intentional"
  line, its own status stays 0, and the output file will still be written — now with `requested_exit_code=0`. The
  file will not disappear: the exit code is a separate result from the file write that happens before it.
- Visible result (**Observed**, [run2-exit-code-0.txt](evidence/run2-exit-code-0.txt), child PID 1177, parent 1173):
  `CHILD: exiting with code 0.` → `PARENT: wait() returned; child exit code was 0.` and nothing else from the parent;
  `parent exit status: 0`. Prediction confirmed.
- Did the output file agree with the result? Yes: `child_pid=1177`, `parent_pid=1173`, `requested_exit_code=0`.

**Change B (early-finisher extension)**

- I changed: `CPU_SECONDS` (keeping `EXIT_CODE = 0`)
- New value: `1.50` (was `0.75`)
- My prediction: the CPU phase line says 1.5 seconds, the pause before the prompt doubles, the child's CPU time is
  about 1.5 s instead of 0.75 s, and `cpu_iterations` is roughly double; exit code still 0.
- Visible result (**Observed**, [run3-cpu-seconds-1.50.txt](evidence/run3-cpu-seconds-1.50.txt), child PID 1422):
  `CHILD: CPU phase for 1.5 seconds...` (Python prints `1.50` as `1.5`), `14815955 loop iterations`; while waiting,
  `/proc/1422/stat` showed `utime=149` ticks = **1.49 s** CPU (baseline: 75 ticks = 0.75 s). Parent: `child exit code was 0`.
- Did the output file agree with the result? Yes: `cpu_iterations=14815955`, `requested_exit_code=0`.
  Note: the iteration count varied between unchanged runs (6.3–8.1 million for 0.75 s), so the loop count is a rough
  indicator; the CPU-tick measurement is the better evidence that the CPU phase doubled.

Automated re-check of both changes and of the supplied behaviour: `python3 -m pytest -q lab/tests` → **12 passed**
(Observed; see [README.md](README.md#how-to-rerun)).

## 6. Runtime ADR — provisional project runtime

**Title:** Runtime choice for the future lab-seat enrollment project — full record: [decisions/ADR-002-provisional-backend-runtime.md](decisions/ADR-002-provisional-backend-runtime.md)

- **Decision.** Provisional choice: **C#/.NET** (current LTS SDK), consistent with the course's current planning. Lecturer-agreed Java stays the named alternative.

  For a team on mixed laptops (Windows, macOS incl. Apple Silicon, Linux) the backend must build and run the same way
  everywhere from one command; .NET offers one cross-platform SDK (`dotnet` CLI) with the same project file and test
  runner on all three systems, so it meets the requirement without the course changing direction. Status: **Proposed**.

- **Context and evidence.** How do mixed developer laptops affect this? What toolchain/support/portability evidence do you have?

  Mixed laptops mean the toolchain, the build, file paths and process behaviour must not depend on one OS — today's
  lab showed that even "start a child and wait" goes through different OS mechanisms (vfork/execve on Linux,
  `CreateProcess` on Windows), so portable runtime libraries matter. Evidence I have: course context (C#/.NET is the
  provisional course route); both .NET and Java publish SDKs/JDKs for Windows, macOS and Linux (vendor documentation, to
  re-verify for the exact versions). Evidence I do **not** have: no backend in either runtime has been built, run or
  measured on our laptops. This Python lab is not a benchmark of either runtime. (Side note: the Linux container I
  used had OpenJDK 21 and no .NET SDK — that container is not a team laptop and says nothing about the team's setup.)

- **Unknowns to check before committing:**

  (1) Can every team member install the chosen SDK version on their own laptop (macOS Apple Silicon, Windows, Linux),
  without admin restrictions? (2) Which runtime does the target deployment environment support (university server,
  container host, OS)? (3) Lecturer agreement and course support (examples, marking) for Java if we switch. (4) Database
  driver and test tooling for the future enrollment storage on all three OSes. (5) IDE/debugger availability per OS
  (Visual Studio is Windows-only; Rider/VS Code are cross-platform) and the team's existing experience.

- **Consequence and trade-off of the provisional choice:**

  Easier: one SDK and CLI for build/test/run on every laptop, alignment with course material and teacher support, a
  strong standard library for HTTP APIs, async I/O and data access. Trade-off: team members (including me — my main
  language is Python) must learn C#; some .NET tooling is best on Windows, so macOS/Linux members rely on the CLI or
  cross-platform IDEs; and the choice is unproven until a small skeleton runs on every laptop. **Reconsider** if any team
  laptop or the deployment target cannot run the chosen SDK, or the lecturer agrees Java fits the team better.

- **Supporting mini decision:** Why does this parent wait for its child before reporting the synthetic result?

  Because the result it reports (the exit code) only exists after the child has terminated: a synchronous `wait()`
  guarantees "child finished → parent reports", collects the status and reaps the child, so no zombie is left behind;
  the cost is that the parent can do nothing else meanwhile, which is acceptable for a one-child helper experiment.

## 7. Exit check

Tick each item you can show the teacher:

- [x] I identified a PID and the parent/child relationship. (§2: child 525, parent 521, shell 515; `ps --forest`)
- [x] I explained why `input()` causes the child to wait. (§2 last row, §3 table; `read(0)` blocked 4.2 s)
- [x] I used an observation or honestly marked a tool unavailable. (Linux observed; macOS and Windows marked not observed)
- [x] I identified the intentional exit code and synthetic output file. (§4, exit code 7, `output/child-result.txt`)
- [x] I completed the boundary diagram, lifecycle, Windows/POSIX comparison and ADR. (§1, §3, §6, `diagrams/`, `decisions/`)
- [x] I explained ready versus blocked and why saved output survives exit. (below and §1)
- [ ] I saved this worksheet in the location the teacher specified. — *to do by the student: paste into My lesson work (P02), check Saved, Submit to my teacher.*

**Ready versus blocked (my words):** a *ready* process has everything it needs except a CPU — it waits for the
scheduler to dispatch it; a *blocked* process cannot use a CPU even if one is free, because an event is missing (for
my child: a line of terminal input; for my parent: the child's termination). When the event arrives the process
becomes ready first, and only a dispatch makes it running again.

---

## Appendix A — Online worksheet: the eight answer sections (copy-ready)

The course website's P02 worksheet has eight answer sections (the "Record in your worksheet" prompts). Short
copy-ready answers; the details are above.

1. **My environment.** Linux 6.18.44 x86_64, Ubuntu 24.04.5 LTS (container), Python 3.13.18, bash + tmux as Terminal A,
   a second shell as Terminal B; runs on 2026-11-21. All lab evidence **Observed** on Linux. macOS (my own laptop):
   commands prepared, **not yet observed**. Windows: not run (reasoned comparison only).
2. **My execution path.** child in user mode: synthetic text in RAM → `write_text` → Python io / C library (OS interface)
   → system calls `openat(child-result.txt)=3`, `write(3, 114 bytes)=114`, `close(3)=0` → kernel VFS/filesystem (page
   cache, later disk) → return to the same process → "wrote synthetic data". The 0.75 s loop stayed in user mode (no
   syscall; `utime 75 ticks, stime 0`). The file survives exit; the process's RAM does not; a successful write does not prove power-loss durability.
3. **My process observation.** Child PID 525, PPID 521 (parent), shell 515; `python3`; `STAT S+` (sleeping, foreground);
   `wchan wait_woken`; `%CPU 19.5` (lifetime average) and 0.75 s cumulative CPU; `VSZ 37348 KiB`, `RSS 13764 KiB`; `NLWP 1`;
   fds 0/1/2 → `/dev/pts/0`, lsof 15 entries (3 CHR, 2 DIR, 10 REG). Observed: sleeping snapshot; inferred: blocked on terminal input.
4. **My parent/child timeline.** parent starts → `Popen` (vfork+execve) → child PID 525 → parent blocks in `wait()` (`do_wait`)
   → child CPU phase 0.75 s → child `input()` → blocked → I press Enter → ready → running → writes file → `exit_group(7)` →
   exited (zombie) → parent's `wait4` returns 7, child reaped → parent prints code 7, exits 0.
5. **Windows and POSIX comparison.** fork copies the caller into a new process (parent gets child PID, child gets 0);
   exec replaces the program inside that process (PID 821 stayed 821); waitpid blocks until exit and reaps the status (7).
   Windows `CreateProcess` builds a new process + initial thread from a named program and returns handles; the parent waits
   on the handle and reads `GetExitCodeProcess`. POSIX part Observed on Linux; Windows reasoned, not run.
6. **My changed-code experiment.** `EXIT_CODE` 7 → 0. Predicted: parent reports 0, no "intentional non-zero" line, file still
   written with `requested_exit_code=0`. Observed exactly that (child 1177). Extension `CPU_SECONDS` 0.75 → 1.50: CPU 1.49 s vs 0.75 s,
   iterations 14.8 M vs ~7–8 M. Values restored afterwards.
7. **My runtime decision.** Provisional C#/.NET (course route) for the enrollment backend on mixed laptops; Java is the
   lecturer-agreed alternative. Unknowns: SDK install on every laptop, deployment target, DB driver/tooling. Trade-off:
   learning C#, uneven IDE support off Windows. Mini decision: the parent waits because its report needs the child's final status and it must reap the child.
8. **My individual exit answer.** The kernel created my child process (PID 525), switched the CPU between processes,
   and performed the protected file write when the child asked through a system call. The child was *blocked* — not
   just *ready* — at the prompt because terminal input was missing, while the parent was blocked in `wait()` for a
   different event, the child's exit. `fork` makes a new process and `exec` swaps the program inside it, so the PID
   stays the same. The saved file survived the child's exit because it lives in the filesystem, while the child's
   working memory was released by the OS.

## Appendix B — Step 3 code reading: operation → line → what I saw

| Code operation | Line | What it means | What my Linux run showed |
| --- | --- | --- | --- |
| `subprocess.Popen(command)` | `parent.py:14` | parent asks the OS to create and start the child | `vfork()` + `execve()` in strace (E2) |
| `sys.executable` | `parent.py:12` | same Python runtime as the parent, no hard-coded path | `/usr/local/bin/python3` printed and in the child's command line |
| `child.pid` | `parent.py:15` | PID the OS assigned to the child | `child PID is 525` = the child's own `PID=525` |
| `child.wait()` | `parent.py:18` (and `:32` in cleanup) | parent blocks until the child ends, gets its status | parent `S+`, `wchan do_wait`; `wait4` returned status 7 after 5.06 s |
| `os.getpid()` / `os.getppid()` | `child.py:28`, `:43–44` | child reports its own and its parent's PID | `PID=525 PPID=521`, same values in the file |
| bounded loop `bounded_cpu_work(CPU_SECONDS)` | `child.py:17`, `:31` | short CPU work that ends after a fixed time | 0.75 s user CPU, no system call (E3) |
| `input(...)` | `child.py:35` | waits for terminal input — blocked until it arrives | `read(0</dev/pts/0>)` blocked 4.2 s; `S+`, `wait_woken` |
| `write_text(...)` | `child.py:41` | writes only synthetic values to `output/child-result.txt` | `openat` → `write(3, 114 bytes)` → `close` |
| `return EXIT_CODE` (7) | `child.py:52`, `:11` | intentional non-zero result, turned into the process exit code by `SystemExit(main())` (`:56`) | `exit_group(7)`; parent reports 7 |
