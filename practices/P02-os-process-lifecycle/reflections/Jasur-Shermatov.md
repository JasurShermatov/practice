# Individual reflection — Jasur Shermatov (P02)

**Four-sentence explanation of my run.** When I started `parent.py`, the kernel created a child process (PID 525)
for `child.py` and gave the parent a way to wait for it; one kernel job I saw directly was performing the protected
file write (`openat`/`write`/`close`) that the child requested through system calls. At the input prompt the child was
*blocked*, not merely *ready*: a free CPU would not have helped because a line of terminal input was missing, while
the parent was blocked in `wait()` for a different event — the child's exit. `fork` creates a new process as a copy of
the caller, while `exec` replaces the program inside an existing process, which is why PID 821 kept its number after
`execv` loaded `child.py`. The file `output/child-result.txt` survived the child's exit because it belongs to the
filesystem, whereas the child's working memory was released by the OS as soon as the process ended.

**Observation vs inference.** What I measured: PIDs, `S+`, `wait_woken` / `do_wait`, 0.75 s of user CPU and no system
call during the loop, a 4.2 s `read`, `vfork` + `execve` behind `Popen`. What I inferred: that the sleep was *for
terminal input*, and every ready ↔ running step — no tool here can show those short transitions.

**What surprised me.** `subprocess.Popen` on Linux did not call `fork()`; strace showed `vfork()` + `execve()`. And
pressing Ctrl+C in the real terminal made the supplied parent report "code None", because the terminal signals the
whole foreground process group, so the child had already exited on its own (finding in [evidence/Index.md](../evidence/Index.md)).

**Link to P01.** In P01 I asked how temporary working data (the "19 available" each request read) differs from a saved
booking. P02 answered the OS half: values in process memory vanish at exit, only what was written through the kernel
to a file (or a database) survives. It does not answer the coordination half — separate memory does not stop two
processes saving the same last seat; that remains for the later concurrency and database practices.

**Limits.** My evidence is from a Linux container. My own laptop is a Mac: the steps are ready in
[macOS-rerun.md](../macOS-rerun.md), but no macOS value is observed yet. Windows was not run.

**Next action.** Run the macOS steps on my laptop and fill the table; in P03 compare what "ready" means once several
cores and the scheduler's policy are involved.
