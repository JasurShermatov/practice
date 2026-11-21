# macOS rerun — steps for my own laptop

All lab evidence in this folder was **Observed on Linux** (container). My own laptop is a Mac, so these are the exact
steps from the classroom lab guide to repeat the run there. Every value in the table below is **not yet observed**
until I run it and paste the real output.

## 1. Setup (lab guide Steps 1–2)

```bash
cd ~/path/to/advanced-programming/practices/P02-os-process-lifecycle/lab   # or drag the lab folder into Terminal after "cd "
ls starter                      # expect: child.py  fork_exec_wait.py  parent.py
python3 --version               # needs 3.10 or newer
```

## 2. Run and inspect the waiting child (Steps 4–5)

Terminal A:

```bash
python3 starter/parent.py       # the explanation's variant also works: python3 -u ./starter/parent.py
```

Wait for `CHILD: press Enter…` and **do not** press Enter. Note the child PID. Terminal B (same folder):

```bash
date
ps -o pid,ppid,state,%cpu,vsz,rss,comm -p <PID>          # guide's macOS command
ps -o pid,ppid,state,time,etime,command -p <PID>,<PPID>  # cumulative CPU time + command lines
lsof -p <PID> | wc -l                                     # optional: number of open resources (do not paste private paths)
lsof -p <PID> | awk 'NR>1{print $5}' | sort | uniq -c     # optional: resource TYPE counts
```

Activity Monitor → search `Python` → select the row with the same PID → **Info** (threads, memory). macOS has no
Linux `/proc`, so `/proc/<PID>/fd`, `wchan` and `status` are **unavailable** on macOS — write "unavailable (no /proc on macOS)".

Then press Enter in Terminal A and run `cat output/child-result.txt`.

## 3. Optional POSIX demo (Step 6)

```bash
python3 starter/fork_exec_wait.py      # check: the PID printed by "parent created PID=" equals the child's PID=
```

## 4. Controlled change (Step 8)

```bash
patch -p1 < changes/01-exit-code-0.patch          # EXIT_CODE 7 -> 0 (or edit the line by hand)
python3 starter/parent.py                         # press Enter; expect "child exit code was 0"
cat output/child-result.txt                       # expect requested_exit_code=0
patch -p1 < changes/02-cpu-seconds-1.50.patch     # optional: CPU_SECONDS 0.75 -> 1.50
python3 starter/parent.py
patch -R -p1 < changes/02-cpu-seconds-1.50.patch && patch -R -p1 < changes/01-exit-code-0.patch   # restore
```

Automated check (no typing at the prompt needed): `python3 -m pytest -q tests` from the same `lab` folder
(needs pytest; without it, the interactive steps above are enough).

## 5. Table to fill on macOS — not yet observed

| Field | macOS value |
| --- | --- |
| macOS + Python versions, time | not yet observed |
| Observed / supplied / simulated | not yet observed |
| Command/tool used | `ps -o pid,ppid,state,%cpu,vsz,rss,comm`, Activity Monitor, `lsof` |
| Child PID / PPID | not yet observed |
| Process name | not yet observed (expected `Python` or `python3`) |
| CPU value (unit) | not yet observed |
| Virtual size (VSZ, KiB) | not yet observed |
| RSS (KiB) | not yet observed |
| Threads (Activity Monitor) | not yet observed |
| Open resources (lsof count/types) | not yet observed |
| State label (`ps` STATE) | not yet observed (expected a sleeping snapshot such as `S`) |
| `fork_exec_wait.py`: PID kept through exec? | not yet observed |
| `EXIT_CODE = 0` run: parent report + file | not yet observed |

Comparison rule: record the exact column names and units; do not rank Linux against macOS from one sample —
VSZ/RSS accounting differs between the two kernels.
