# P02 evidence index

Environment for every **Observed** item: Linux 6.18.44 x86_64, Ubuntu 24.04.5 LTS container, Python 3.13.18
(`/usr/local/bin/python3`), procps-ng `ps` 4.0.4, strace 6.8, tmux 3.4 as Terminal A (a real pseudo-terminal,
`/dev/pts/0`). Recorded 2026-11-21 (Asia/Tashkent, UTC+05:00). PIDs differ between runs because each run creates new processes.

Runs were driven by [capture_linux_run.sh](capture_linux_run.sh): it starts the command in a tmux session (Terminal A),
waits for the prompt, waits 3 s, inspects the child from a second shell (Terminal B), then presses Enter in
Terminal A and records the rest. Re-run with e.g. `bash evidence/capture_linux_run.sh run1-baseline "python3 starter/parent.py"`.

| ID | Label | Lab step / worksheet § | What was run | Key result | File |
| --- | --- | --- | --- | --- | --- |
| E1 | **Observed** | Steps 4–6 · §2, §3, §4 | `python3 starter/parent.py`, supplied code, inspected while waiting | child 525 / parent 521 / shell 515; `S+`, `wchan wait_woken` (child) and `do_wait` (parent); VSZ 37348 KiB, RSS 13764 KiB, NLWP 1; 0.75 s CPU (75 ticks); fds 0–2 → `/dev/pts/0`; parent reports 7, exits 0; PID gone afterwards | [run1-baseline.txt](run1-baseline.txt), [file](run1-baseline-child-result.txt) |
| E2 | **Observed** | Step 4 boundary · §1 | same command under `strace -f -tt -T -y` (filtered set) | `vfork()` + `execve(python3 -u child.py)`; `read(0)` blocked **4.203 s**; `openat(child-result.txt)=3`, `write(3,…,114)=114`, `close(3)=0`; `exit_group(7)`; parent `wait4` blocked 5.062 s and got status 7 | [strace-excerpt.txt](strace-excerpt.txt), [run](run-strace-syscalls.txt) |
| E3 | **Observed** | Step 4 boundary · §1 | child under `strace` with **all** syscalls | no system call during the 0.75 s CPU loop → user mode only | [strace-cpu-phase-all-syscalls.txt](strace-cpu-phase-all-syscalls.txt) |
| E4 | **Observed** | Step 6 · §3 comparison | `python3 starter/fork_exec_wait.py`, inspected while waiting | `parent PID=817` → `created PID=821`; child prints `PID=821 PPID=817` (same PID after exec); `waited for PID=821; exit code=7` | [run4-fork-exec-wait.txt](run4-fork-exec-wait.txt) |
| E5 | **Observed** | Step 6 · §3 comparison | fork demo under `strace` | `clone(…SIGCHLD)=919` (fork), `execve` in 919, `getpid()=919` after exec, `wait4(919)` → 7 | [strace-fork-excerpt.txt](strace-fork-excerpt.txt), [run](run-strace-fork.txt) |
| E6 | **Observed** | Step 8 · §5 change A | `EXIT_CODE = 0` ([patch](../lab/changes/01-exit-code-0.patch)) | `child exit code was 0`, no "intentional non-zero" line, parent status 0; file `requested_exit_code=0` | [run2-exit-code-0.txt](run2-exit-code-0.txt), [file](run2-exit-code-0-child-result.txt) |
| E7 | **Observed** | Step 8 · §5 change B | `CPU_SECONDS = 1.50` ([patch](../lab/changes/02-cpu-seconds-1.50.patch)) | `CPU phase for 1.5 seconds`, 149 ticks = 1.49 s CPU (vs 0.75 s), 14,815,955 iterations | [run3-cpu-seconds-1.50.txt](run3-cpu-seconds-1.50.txt), [file](run3-cpu-seconds-1.50-child-result.txt) |
| E8 | **Observed** | Step 8.5 restore | supplied values restored (sha256 of `child.py` equals the supplied file) and rerun | exit code 7 again; this run's file is the one kept in `lab/output/` | [run5-restored-original.txt](run5-restored-original.txt) |
| E9 | **Observed** (extra) | §3 "reaped" | throw-away parent delays `wait()` | exited child shows `STAT Z` (zombie) until `wait()` returns 0, then disappears | [extra-zombie-reaping.txt](extra-zombie-reaping.txt) |
| E10 | **Observed** (extra) | parent.py cleanup path | Ctrl+C in Terminal A while the child waits | both get SIGINT; child prints `KeyboardInterrupt` traceback; parent prints `child ended after interruption with code None.` — see finding below | [extra-ctrl-c.txt](extra-ctrl-c.txt) |
| E11 | **Observed** | all steps | `python3 -m pytest -q lab/tests` | 12 passed (baseline, PID relation, ordering, file, EOF, SIGINT, both changes, other non-zero, patches, restore, fork/exec) | [../lab/tests/test_p02_lab.py](../lab/tests/test_p02_lab.py) |
| E12 | **Supplied** | comparison only | course's `Captured-output.md` (invented PIDs 42190/42188) | used only to compare column names; never as my evidence | course ZIP |
| E13 | **Proposed** | macOS rerun | guide's macOS commands on my own laptop | **not yet observed** | [../macOS-rerun.md](../macOS-rerun.md) |
| E14 | not run | Windows | `Get-Process`, `Get-CimInstance`, Task Manager | not available here; Windows creation explained from course notes | — |

## Finding from E10 (supplied `parent.py`, not changed)

With a real terminal, Ctrl+C sends SIGINT to the whole foreground process group, so the child also receives it and
exits on its own. Python's `Popen.wait()` gives the child a short grace period after Ctrl+C and records its return
code, so in `parent.py`'s `finally` block `child.poll()` is no longer `None`, the cleanup branch is skipped, and the
local `exit_code` keeps the `None` set in the `except` branch. The parent therefore prints "code None" although the
code is known (`child.returncode`). It is harmless for the lab (the child is gone and reaped). A one-line fix would be
`exit_code = child.returncode` when `poll()` is not `None`. I did not change `parent.py` because the guide limits the
coding task to the named constants. The automated test signals only the parent, so it sees the cleanup path (`-15`).

## Limits

- `ps %CPU` is CPU time divided by elapsed lifetime, not an instantaneous reading; `TIME` is rounded to seconds, so
  the exact value came from `/proc/<PID>/stat` ticks.
- `S` means "sleeping"; that it was waiting for *terminal input* is inferred from the code, the prompt, `wchan` and the 4.2 s `read`.
- Ready ↔ running transitions were not observable with these tools; they are explained, not measured.
- strace slows the traced processes; the traced runs are evidence of *which* calls happen, not of timing performance.
- A container is not my macOS laptop; values (VSZ/RSS, process names, creation mechanism) can differ there.
