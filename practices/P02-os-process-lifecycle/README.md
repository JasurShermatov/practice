# P02 — OS introduction, kernels and process lifecycle

**Session:** Saturday 10 October 2026, 11:00–12:20 (Asia/Tashkent) · Practice · Group 23-309 SW · Room 231
**Type of work:** an 80-minute lab — run the supplied parent/child Python programs, inspect the waiting child with OS
tools, explain the user/kernel boundary and the process lifecycle, change one named constant, and record a
provisional runtime ADR. P02 does not touch `hotel-booking/`.

## Goal

Follow one program into a process, across an OS request and through waiting to completion — with real evidence:
which PID the OS gave the child, what the kernel was doing while the child waited for Enter, which system calls saved
the synthetic file, and what changed when I changed `EXIT_CODE` and `CPU_SECONDS`.

> Fictional classroom scenario (course brief): a university enrollment system will let students reserve lab seats.
> The parent/child programs are a small OS helper experiment for that future project; they touch no student records.

## Contents

| Lab guide step / worksheet field | Where it is answered |
|---|---|
| Steps 1–3: lab files, Python check, read the code | [lab/starter/](lab/starter) (supplied files, copied unchanged — sha256 checked); code-operation mapping in [Worksheet.md Appendix B](Worksheet.md#appendix-b--step-3-code-reading-operation--line--what-i-saw) |
| Step 4 + Task 1: boundary trace (user/kernel, CPU, RAM, file) | [Worksheet.md §1](Worksheet.md#my-execution-boundary-diagram), [diagrams/boundary.mmd](diagrams/boundary.mmd) ([svg](diagrams/boundary.svg)), evidence E2–E3 |
| Step 5 + Task 2: run and inspect the waiting child | [Worksheet.md §2](Worksheet.md#2-evidence-while-the-child-waited-for-input), [evidence/run1-baseline.txt](evidence/run1-baseline.txt) |
| Step 6 + Task 3: finish the run, view the file, Windows/POSIX comparison, `fork_exec_wait.py` | [Worksheet.md §3–4](Worksheet.md#windows-and-posix-comparison), [diagrams/creation-comparison.mmd](diagrams/creation-comparison.mmd), evidence E4–E5 |
| Step 7 + Task 4: lifecycle with labelled arrows | [Worksheet.md §3](Worksheet.md#3-lifecycle-for-this-run), [diagrams/lifecycle.mmd](diagrams/lifecycle.mmd), [diagrams/sequence.mmd](diagrams/sequence.mmd) |
| Step 7: provisional runtime ADR + supporting mini decision | [Worksheet.md §6](Worksheet.md#6-runtime-adr--provisional-project-runtime), [decisions/ADR-002-provisional-backend-runtime.md](decisions/ADR-002-provisional-backend-runtime.md) |
| Step 8: controlled change, prediction, result | [Worksheet.md §5](Worksheet.md#5-controlled-change), [lab/changes/](lab/changes), evidence E6–E8, [lab/tests/](lab/tests/test_p02_lab.py) |
| Step 8–9: quiz, role swap, worksheet swap, online submission | [Peer-review.md](Peer-review.md), [Your-turn-answers.md](Your-turn-answers.md) — *to do by the student* |
| Step 9: eight online answer sections | [Worksheet.md Appendix A](Worksheet.md#appendix-a--online-worksheet-the-eight-answer-sections-copy-ready) |
| "Your turn" prompts, short cases, simulator sequence | [Your-turn-answers.md](Your-turn-answers.md) |
| Exit reflection | [reflections/Jasur-Shermatov.md](reflections/Jasur-Shermatov.md), [Worksheet.md §7](Worksheet.md#7-exit-check) |
| macOS commands to rerun on my laptop | [macOS-rerun.md](macOS-rerun.md) — **not yet observed** |
| Evidence index, findings, limits | [evidence/Index.md](evidence/Index.md) |
| Saved synthetic output from my own run | [lab/output/child-result.txt](lab/output/child-result.txt) |

## Folder layout

```text
P02-os-process-lifecycle/
├── README.md                 this file (map + requirements checklist)
├── Worksheet.md              all worksheet answers, course headings and order + the 8 online sections
├── Your-turn-answers.md      every "Your turn" prompt / short case
├── macOS-rerun.md            guide's macOS steps + empty table (not yet observed)
├── Peer-review.md            pair roles, worksheet swap (to do by the student)
├── decisions/ADR-002-provisional-backend-runtime.md
├── diagrams/                 boundary, lifecycle, sequence, creation-comparison (.mmd + rendered .svg)
├── evidence/                 Index.md, real terminal transcripts, ps//proc output, strace excerpts, capture script
├── reflections/Jasur-Shermatov.md
└── lab/
    ├── starter/              child.py, parent.py, fork_exec_wait.py — the course files, unchanged
    ├── changes/              my Step 8 modifications as patches (EXIT_CODE 7→0, CPU_SECONDS 0.75→1.50)
    ├── output/child-result.txt   synthetic file from my final run (restored original code)
    └── tests/test_p02_lab.py automated checks of the supplied behaviour and of my changes
```

## How to rerun

From this practice folder (Linux or macOS, Python 3.10+):

```bash
cd lab
python3 starter/parent.py                 # press Enter at the prompt; inspect from a 2nd terminal first
python3 starter/fork_exec_wait.py         # POSIX only
patch -p1 < changes/01-exit-code-0.patch  # Step 8 change; undo with: patch -R -p1 < changes/01-exit-code-0.patch
cd ..
python3 -m pytest -q lab/tests            # automated checks (copies the lab to a temp folder; needs pytest)
bash evidence/capture_linux_run.sh run1-baseline "python3 starter/parent.py"   # Linux + tmux: re-record a run
```

**Test result (Observed, Linux container, Python 3.13.18, pytest 9.1.1):** `python3 -m pytest -q lab/tests` → `12 passed in 9.4 s`.

## Evidence labels and environment

**Observed** = I ran it in a Linux container (Ubuntu 24.04.5 LTS, kernel 6.18.44 x86_64, Python 3.13.18) on
2026-11-21 and copied the real output. **Supplied** = the course's illustrative sample (invented PIDs) — used only to
compare column names. **Simulated / Proposed** = model or plan, nothing ran. macOS (my laptop) and Windows: **not yet observed**.

## Notes on tooling (what differs from the course setup)

- The course expects two terminal windows. Here, Terminal A is a `tmux` session (a real pseudo-terminal, so `input()`
  reads from `/dev/pts/0` exactly as in a desktop terminal) and Terminal B is a second shell; the script
  [evidence/capture_linux_run.sh](evidence/capture_linux_run.sh) records both. Pressing Enter is done by `tmux send-keys`.
- Extra tools beyond the guide's Linux commands: `strace` (to see the system calls behind the boundary diagram and
  behind `Popen`), `ps --forest`, `/proc/<PID>/wchan` and `/proc/<PID>/stat` (exact CPU ticks). They support, not replace, the guide's `ps` and `/proc/<PID>/fd` evidence.
- The worksheet's code change was made by editing `child.py` in place, running, and then restoring the supplied value
  (the guide's "restore the original value"); the edits are kept as patches, and the tests apply them to a temporary copy.

## Findings worth noting

1. `subprocess.Popen` on this Linux/Python 3.13 system used **`vfork()` + `execve()`**, not `fork()` (E2) — the guide's
   warning "do not describe it as always fork" is confirmed.
2. The supplied `parent.py` reports **"code None"** after Ctrl+C in a real terminal, because the terminal also
   interrupts the child, which exits during `Popen.wait()`'s Ctrl+C grace period (E10). Not changed — outside the
   lab's coding task; explanation and one-line fix in [evidence/Index.md](evidence/Index.md#finding-from-e10-supplied-parentpy-not-changed).

## Limits

- One container run is not my Mac: process names, VSZ/RSS accounting and the creation mechanism may differ on macOS.
- Ready ↔ running transitions and the exact scheduling order are explained, not observed.
- The runtime ADR is provisional and has no runtime evidence; this Python lab does not benchmark .NET or Java.
- Pair roles, worksheet swap, quiz, simulator, and the signed-in submission can only be done by me in person.

## Requirements checklist

| # | Requirement (source) | Where satisfied | Status |
|---|---|---|---|
| 1 | Extract lab; starter files `child.py`, `parent.py`, `fork_exec_wait.py` present (guide Step 1) | [lab/starter/](lab/starter); identical to the lab-guide appendix (diff checked) | Done |
| 2 | Python 3.10+ checked, no packages (Step 2) | Python 3.13.18 recorded in every evidence file | Done (Observed) |
| 3 | Read the code; match operations to lines (Step 3) | Worksheet §1 Q2, §3 creation evidence | Done |
| 4 | Run parent, press Enter; visible result: child PID, exit 7, parent finishes normally (Step 4) | E1, Worksheet §1 Q3 | Done (Observed) |
| 5 | Boundary trace: user mode, OS interface, kernel/filesystem, return; CPU, RAM, stored file; user-mode calculation; buffering ≠ durability; file vs process memory (Step 4, Task 1, worksheet §1) | Worksheet §1, [diagrams/boundary.mmd](diagrams/boundary.mmd), E2, E3 | Done |
| 6 | Inspect the waiting child with the OS tool (Linux `ps -o pid,ppid,stat,%cpu,vsz,rss,nlwp,comm`, optional `/proc/<PID>/fd`) and record every table field (Step 5, worksheet §2) | Worksheet §2 table, E1 | Done (Observed, Linux) |
| 7 | macOS commands (`ps -o pid,ppid,state,…`, `lsof -p`, Activity Monitor) | [macOS-rerun.md](macOS-rerun.md) | Prepared — **not yet observed** (my Mac) |
| 8 | Windows commands (`Get-Process`, `Get-CimInstance`, Task Manager) | Worksheet §2/§3 mark Windows as not run | Unavailable here — marked honestly |
| 9 | Distinguish observed from inferred; don't equate a display label with a full state (worksheet §2) | Worksheet §2 sentence, §3 table "Evidence type" column | Done |
| 10 | Finish the run, view `output/child-result.txt` (Step 6, worksheet §4) | Worksheet §4, [lab/output/child-result.txt](lab/output/child-result.txt), `evidence/*-child-result.txt` | Done (Observed) |
| 11 | Run `fork_exec_wait.py` on Linux/macOS; compare fork/exec/wait with CreateProcess; label supplied trace (Step 6, worksheet §3) | Worksheet §3 comparison, [diagrams/creation-comparison.mmd](diagrams/creation-comparison.mmd), E4, E5 | Done (Linux observed; Windows reasoned) |
| 12 | Lifecycle new → running → waiting → running → exited → reaped with labelled arrows (Popen, CPU phase, input, Enter, return EXIT_CODE, wait); ready vs running vs blocked (Step 7, worksheet §3, Task 4) | Worksheet §3, [diagrams/lifecycle.mmd](diagrams/lifecycle.mmd), [diagrams/sequence.mmd](diagrams/sequence.mmd), E9 | Done |
| 13 | Parent's own wait state story (Task 4) | Worksheet §3 "parent's separate story" | Done |
| 14 | Provisional runtime ADR: decision, evidence, unknowns, consequence, trade-off; mini decision on wait (Step 7, worksheet §6) | Worksheet §6, [ADR-002](decisions/ADR-002-provisional-backend-runtime.md) | Done (Proposed) |
| 15 | Change `EXIT_CODE` 7 → 0; predict; run; verify in terminal and file (Step 8, worksheet §5) | Worksheet §5, [patch](lab/changes/01-exit-code-0.patch), E6, tests | Done (Observed) |
| 16 | Early-finisher: `CPU_SECONDS` 0.75 → 1.50 (Step 8) | Worksheet §5 change B, [patch](lab/changes/02-cpu-seconds-1.50.patch), E7, tests | Done (Observed) |
| 17 | Restore original value if asked (Step 8.5) | `lab/starter/child.py` restored (sha256 = supplied), E8, test `test_supplied_child_is_restored_to_the_original_values` | Done |
| 18 | Diagrams asked for (boundary, lifecycle; creation comparison) | [diagrams/](diagrams) — 4 Mermaid sources, all rendered with `mmdc` to SVG without errors | Done |
| 19 | Exit check items + ready vs blocked + why saved output survives (worksheet §7, §38) | Worksheet §7, reflection | Done (last box = submission, see #22) |
| 20 | "Your turn" prompts, short cases, simulator sequence (§1–38) | [Your-turn-answers.md](Your-turn-answers.md) | Done; interactive simulator/quiz *to do by the student* |
| 21 | Pair roles, role swap, worksheet swap with one correction (Steps 5, 8) | [Peer-review.md](Peer-review.md) | **To do by the student** |
| 22 | Fill the eight online answer sections, check Saved, Submit to my teacher (Step 9) | Copy-ready text in [Worksheet.md Appendix A](Worksheet.md#appendix-a--online-worksheet-the-eight-answer-sections-copy-ready) | **To do by the student** |
| 23 | Keep worksheet + synthetic output file locally (Step 9) | This folder | Done |
| 24 | Evidence honesty: name system, mark unavailable tools, label every sample (Step 7 check, explanation §2) | Worksheet header + labels, [evidence/Index.md](evidence/Index.md) | Done |
| 25 | Automated tests for the practised behaviour (portfolio convention) | [lab/tests/test_p02_lab.py](lab/tests/test_p02_lab.py) — 12 passed | Done (Observed) |
| 26 | Reflection and limits (portfolio convention) | [reflections/Jasur-Shermatov.md](reflections/Jasur-Shermatov.md), Limits above | Done |
