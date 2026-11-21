#!/usr/bin/env bash
# Reproducible "Terminal A + Terminal B" capture for the P02 lab on Linux.
#
# Terminal A = a tmux session (a real pseudo-terminal) that runs the lab command.
# Terminal B = this script, which inspects the waiting child with ps and /proc,
#              then presses Enter in Terminal A and records the rest of the run.
#
# Usage (from the practice folder):
#   bash evidence/capture_linux_run.sh <label> "<command run in lab/>"
# Example:
#   bash evidence/capture_linux_run.sh run1-baseline "python3 starter/parent.py"
#
# Output: evidence/<label>.txt (terminal A transcript + inspection), and a copy of
# lab/output/child-result.txt as evidence/<label>-child-result.txt.
set -euo pipefail

label="$1"
cmd="$2"
here="$(cd "$(dirname "$0")/.." && pwd)"
lab="$here/lab"
out="$here/evidence/$label.txt"
session="p02-${label//[^A-Za-z0-9_-]/_}"   # tmux treats "." and ":" as target separators

wait_for() {  # wait_for <regex> <timeout-seconds>
  local pattern="$1" limit="$2" waited=0
  until tmux capture-pane -p -t "$session" | grep -Eq "$pattern"; do
    sleep 0.2; waited=$((waited + 1))
    if (( waited > limit * 5 )); then echo "timeout waiting for: $pattern" >&2; return 1; fi
  done
}

tmux kill-session -t "$session" 2>/dev/null || true
tmux new-session -d -s "$session" -x 220 -y 60 -c "$lab" "bash --norc --noprofile"
tmux send-keys -t "$session" "PS1='lab\$ '; clear" Enter
sleep 0.5
tmux send-keys -t "$session" "$cmd" Enter
wait_for "press Enter" 30

child_pid="$(tmux capture-pane -p -t "$session" | sed -nE 's/^CHILD: PID=([0-9]+) PPID=([0-9]+).*/\1/p' | tail -1)"
parent_pid="$(tmux capture-pane -p -t "$session" | sed -nE 's/^CHILD: PID=([0-9]+) PPID=([0-9]+).*/\2/p' | tail -1)"

sleep 3   # like a person switching to Terminal B; the child keeps waiting

{
  echo "=== P02 capture: $label ==="
  echo "Command in Terminal A (cwd = lab/): $cmd"
  echo "Recorded: $(date -Is)"
  echo "Environment: $(uname -srm); $(. /etc/os-release && echo "$PRETTY_NAME"); $(python3 --version)"
  echo
  echo "--- Terminal A while the child waits at its prompt (Enter NOT pressed yet) ---"
  tmux capture-pane -p -t "$session" | sed '/^$/d'
  echo
  echo "--- Terminal B: inspection of child PID $child_pid (parent PID $parent_pid) ---"
  echo "\$ date -Is"; date -Is
  echo "\$ ps -o pid,ppid,stat,%cpu,vsz,rss,nlwp,comm -p $child_pid"
  ps -o pid,ppid,stat,%cpu,vsz,rss,nlwp,comm -p "$child_pid"
  echo "\$ ps -o pid,ppid,stat,%cpu,vsz,rss,nlwp,comm -p $parent_pid    # the parent, waiting in wait()"
  ps -o pid,ppid,stat,%cpu,vsz,rss,nlwp,comm -p "$parent_pid"
  echo "\$ ps -o pid,ppid,stat,time,etime,args -p $parent_pid,$child_pid   # cumulative CPU TIME and command lines"
  ps -o pid,ppid,stat,time,etime,args -p "$parent_pid,$child_pid"
  echo "\$ ps -o pid,ppid,stat,comm --forest -s \$(ps -o sid= -p $parent_pid)   # process tree of this terminal session"
  ps -o pid,ppid,stat,comm --forest -s "$(ps -o sid= -p "$parent_pid" | tr -d ' ')"
  echo "\$ awk '{print \"utime_ticks=\"\$14, \"stime_ticks=\"\$15}' /proc/$child_pid/stat; getconf CLK_TCK   # exact cumulative CPU"
  awk '{print "utime_ticks="$14, "stime_ticks="$15}' "/proc/$child_pid/stat"; getconf CLK_TCK
  echo "\$ grep -E '^(Name|State|Pid|PPid|Threads|VmSize|VmRSS)' /proc/$child_pid/status"
  grep -E '^(Name|State|Pid|PPid|Threads|VmSize|VmRSS)' "/proc/$child_pid/status"
  echo "\$ cat /proc/$child_pid/wchan; echo     # kernel function the child sleeps in"
  cat "/proc/$child_pid/wchan" 2>/dev/null || echo "(unavailable)"; echo
  echo "\$ cat /proc/$parent_pid/wchan; echo    # kernel function the parent sleeps in"
  cat "/proc/$parent_pid/wchan" 2>/dev/null || echo "(unavailable)"; echo
  echo "\$ ls -l /proc/$child_pid/fd"
  ls -l "/proc/$child_pid/fd" | sed -E 's/^[^ ]+ +[0-9]+ +[^ ]+ +[^ ]+ +[0-9]+ +//'
  echo "\$ lsof -p $child_pid | wc -l    # open resources incl. header line (paths not copied)"
  lsof -p "$child_pid" 2>/dev/null | wc -l
  echo "\$ lsof -p $child_pid | awk 'NR>1{print \$5}' | sort | uniq -c    # resource TYPE counts"
  lsof -p "$child_pid" 2>/dev/null | awk 'NR>1{print $5}' | sort | uniq -c
  echo "\$ sleep 1; ps -o pid,stat,%cpu,time -p $child_pid    # second sample, 1 s later"
  sleep 1; ps -o pid,stat,%cpu,time -p "$child_pid"
  echo
} > "$out"

tmux send-keys -t "$session" "" Enter     # Terminal A: press Enter for the child
wait_for "PARENT: (wait\\(\\) returned|unexpected)|FORK-DEMO: waited" 30
sleep 0.5
tmux send-keys -t "$session" 'echo "parent exit status: $?"' Enter
sleep 0.5

{
  echo "--- Terminal A after Enter (complete transcript) ---"
  tmux capture-pane -p -t "$session" | sed '/^$/d'
  echo
  echo "--- After the run: is the child PID still present? ---"
  echo "\$ ps -o pid,stat,comm -p $child_pid || echo 'no such process (exited and reaped)'"
  ps -o pid,stat,comm -p "$child_pid" || echo "no such process (exited and reaped)"
  echo
  echo "--- Saved synthetic file ---"
  echo "\$ cat output/child-result.txt"
  cat "$lab/output/child-result.txt"
} >> "$out"

cp "$lab/output/child-result.txt" "$here/evidence/$label-child-result.txt"
tmux kill-session -t "$session"
echo "wrote $out"
