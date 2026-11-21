"""Automated checks for the P02 lab programs and my Step 8 changes.

Every test copies ``lab/starter`` into a temporary folder, so the supplied files and the
saved ``lab/output/child-result.txt`` are never touched. Input is given through a pipe
instead of a person pressing Enter; the interactive terminal runs are recorded separately
in ``evidence/``.

Run from the practice folder:  python3 -m pytest -q lab/tests
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parent.parent
STARTER = LAB / "starter"
CHANGES = LAB / "changes"
TIMEOUT = 30


@dataclass(frozen=True)
class Run:
    returncode: int
    output: str
    seconds: float
    lab_root: Path

    @property
    def saved(self) -> dict[str, str]:
        """The key=value lines of the synthetic output file, if it was written."""
        path = self.lab_root / "output" / "child-result.txt"
        if not path.exists():
            return {}
        lines = path.read_text(encoding="utf-8").splitlines()[1:]
        return dict(line.split("=", 1) for line in lines)


def make_lab(tmp_path: Path, **constants: str) -> Path:
    """Copy the starter programs and optionally rewrite named constants in child.py."""
    lab_root = tmp_path / "p02-lab"
    shutil.copytree(STARTER, lab_root / "starter")
    child = lab_root / "starter" / "child.py"
    source = child.read_text(encoding="utf-8")
    for name, value in constants.items():
        source, count = re.subn(rf"^{name} = .*$", f"{name} = {value}", source, flags=re.M)
        assert count == 1, f"constant {name} not found exactly once"
    child.write_text(source, encoding="utf-8")
    return lab_root


def run_program(lab_root: Path, script: str, stdin: str | None = "\n") -> Run:
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, f"starter/{script}"],
        cwd=lab_root,
        input=stdin,
        stdin=subprocess.DEVNULL if stdin is None else None,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    elapsed = time.perf_counter() - started
    return Run(completed.returncode, completed.stdout + completed.stderr, elapsed, lab_root)


def child_ids(output: str) -> tuple[int, int]:
    match = re.search(r"CHILD: PID=(\d+) PPID=(\d+)", output)
    assert match, output
    return int(match.group(1)), int(match.group(2))


# --- Step 4/6: the supplied program, unchanged -------------------------------------------


def test_baseline_parent_reports_intentional_exit_code_7(tmp_path: Path) -> None:
    run = run_program(make_lab(tmp_path), "parent.py")

    assert run.returncode == 0, "the parent itself finishes normally"
    assert "PARENT: wait() returned; child exit code was 7." in run.output
    assert "non-zero is intentional" in run.output


def test_parent_reports_the_pid_the_child_reports_and_is_its_parent(tmp_path: Path) -> None:
    run = run_program(make_lab(tmp_path), "parent.py")

    reported = int(re.search(r"child PID is (\d+)", run.output).group(1))
    child_pid, child_ppid = child_ids(run.output)
    assert reported == child_pid
    assert child_ppid != child_pid
    assert run.saved["child_pid"] == str(child_pid)
    assert run.saved["parent_pid"] == str(child_ppid)


def test_parent_report_comes_after_child_exit(tmp_path: Path) -> None:
    run = run_program(make_lab(tmp_path), "parent.py")

    assert run.output.index("CHILD: exiting with code 7.") < run.output.index("PARENT: wait() returned")


def test_saved_file_has_only_synthetic_labels_and_survives_child_exit(tmp_path: Path) -> None:
    run = run_program(make_lab(tmp_path), "parent.py")

    # The child process no longer exists here, yet the file can be reopened.
    assert set(run.saved) == {
        "child_pid", "parent_pid", "platform", "cpu_iterations", "requested_exit_code",
    }
    assert run.saved["requested_exit_code"] == "7"
    assert run.saved["platform"] == __import__("platform").system()
    assert int(run.saved["cpu_iterations"]) > 0


def test_no_input_means_no_output_file_and_parent_flags_unexpected_result(tmp_path: Path) -> None:
    run = run_program(make_lab(tmp_path), "parent.py", stdin=None)  # immediate end-of-file

    assert run.returncode == 1
    assert "no terminal input was available" in run.output
    assert "child exit code was 1" in run.output
    assert run.saved == {}


def test_ctrl_c_in_parent_ends_only_its_own_child(tmp_path: Path) -> None:
    lab_root = make_lab(tmp_path)
    parent = subprocess.Popen(
        [sys.executable, "-u", "starter/parent.py"],
        cwd=lab_root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    seen = b""
    deadline = time.monotonic() + TIMEOUT
    while b"press Enter" not in seen and time.monotonic() < deadline:
        chunk = os.read(parent.stdout.fileno(), 4096)
        if not chunk:
            break
        seen += chunk
    assert b"press Enter" in seen, seen
    child_pid, _ = child_ids(seen.decode())

    # Signal only the parent. Keep its stdin pipe open until it has finished: closing it
    # early would give the child end-of-file, so the child would exit by itself (code 1)
    # inside Popen.wait()'s short Ctrl+C grace period instead of being terminated.
    parent.send_signal(signal.SIGINT)
    parent.wait(timeout=TIMEOUT)
    rest = parent.stdout.read()
    parent.stdin.close()
    parent.stdout.close()
    output = (seen + rest).decode()

    assert parent.returncode == 0
    assert "Ctrl+C received" in output
    assert f"child ended after interruption with code {-signal.SIGTERM}" in output
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)  # the child is gone (terminated and reaped)


# --- Step 8: my controlled changes --------------------------------------------------------


def test_change_exit_code_to_0_parent_reports_success(tmp_path: Path) -> None:
    run = run_program(make_lab(tmp_path, EXIT_CODE="0"), "parent.py")

    assert run.returncode == 0
    assert "PARENT: wait() returned; child exit code was 0." in run.output
    assert "non-zero is intentional" not in run.output
    assert "unexpected child result" not in run.output
    assert run.saved["requested_exit_code"] == "0", "the file is still written; only the code changed"


def test_change_exit_code_to_another_nonzero_value_is_reported_as_unexpected(tmp_path: Path) -> None:
    run = run_program(make_lab(tmp_path, EXIT_CODE="3"), "parent.py")

    assert run.returncode == 1
    assert "child exit code was 3" in run.output
    assert "unexpected child result" in run.output


def test_change_cpu_seconds_to_1_50_makes_cpu_phase_at_least_1_5_seconds(tmp_path: Path) -> None:
    run = run_program(make_lab(tmp_path, EXIT_CODE="0", CPU_SECONDS="1.50"), "parent.py")

    assert "CHILD: CPU phase for 1.5 seconds..." in run.output
    # The loop runs until a wall-clock deadline, so the whole run cannot be shorter.
    assert run.seconds >= 1.5
    assert "child exit code was 0" in run.output


@pytest.mark.skipif(shutil.which("patch") is None, reason="patch tool not installed")
def test_recorded_patches_apply_cleanly_to_the_supplied_child(tmp_path: Path) -> None:
    lab_root = make_lab(tmp_path)
    for patch_file in ("01-exit-code-0.patch", "02-cpu-seconds-1.50.patch"):
        subprocess.run(
            ["patch", "-p1", "--quiet", "-i", str(CHANGES / patch_file)],
            cwd=lab_root, check=True, timeout=TIMEOUT,
        )
    source = (lab_root / "starter" / "child.py").read_text(encoding="utf-8")
    assert re.search(r"^EXIT_CODE = 0$", source, flags=re.M)
    assert re.search(r"^CPU_SECONDS = 1.50$", source, flags=re.M)


def test_supplied_child_is_restored_to_the_original_values() -> None:
    source = (STARTER / "child.py").read_text(encoding="utf-8")
    assert re.search(r"^EXIT_CODE = 7$", source, flags=re.M)
    assert re.search(r"^CPU_SECONDS = 0.75$", source, flags=re.M)


# --- Step 6: explicit POSIX fork / exec / wait ---------------------------------------------


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork() is not available (Windows)")
def test_fork_exec_wait_keeps_the_pid_through_exec_and_reports_exit_code(tmp_path: Path) -> None:
    run = run_program(make_lab(tmp_path), "fork_exec_wait.py")

    forking_parent = int(re.search(r"parent PID=(\d+) is about to fork", run.output).group(1))
    created = int(re.search(r"parent created PID=(\d+)", run.output).group(1))
    child_pid, child_ppid = child_ids(run.output)
    assert child_pid == created, "exec replaced the program but kept the forked PID"
    assert child_ppid == forking_parent
    assert f"waited for PID={created}; exit code=7" in run.output
    assert run.returncode == 0
