"""Run hotel-booking/docs/api-check.md against the real app: uvicorn on localhost, curl, a SQLite file.

    python3 -I practices/P07-capacity-api-design/evidence/api_check.py hotel-booking [--port 5080]

What it does, exactly like a person following the document:

1. deletes nothing in the project: the database is a fresh file in a temporary folder
   (HOTEL_DB_PATH), so the run starts from an empty database;
2. starts ``python main.py --port <port>`` (uvicorn) in the hotel-booking folder and waits until
   the port answers;
3. for every numbered section with a command block, runs the command with bash in the
   hotel-booking folder (``localhost:5080`` is replaced by the chosen port, and the SQLite file
   name by the temporary file) and compares its output with the section's Expected block;
4. at the section "Stop the app ... start it again" it stops the server (SIGINT, like Ctrl+C) and
   starts a new one over the same database file;
5. prints a report (command, actual output, ✓ or ✗) and the server's own log; exits 1 on any ✗.

Standard library only; needs curl and the project's requirements (starlette, uvicorn, pydantic).
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

SECTION = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)
BLOCK = re.compile(r"```text\n(.*?)```", re.DOTALL)


@dataclass
class Step:
    number: int
    title: str
    command: str | None
    expected: str | None
    restart: bool


def read_steps(document: str) -> list[Step]:
    steps = []
    matches = list(SECTION.finditer(document))
    for match, following in zip(matches, [*matches[1:], None]):
        body = document[match.end(): following.start() if following else len(document)]
        blocks = BLOCK.findall(body)
        command = blocks[0].strip() if blocks else None
        expected = None
        if "Expected:" in body:
            expected = BLOCK.findall(body[body.index("Expected:"):])[0]
        steps.append(Step(int(match.group(1)), match.group(2), command, expected,
                          restart="start it again" in match.group(2)))
    return steps


def normalise(text: str) -> str:
    """Compare line by line, ignoring blank lines at the start/end (a 204 prints an empty body line)."""
    return "\n".join(line.rstrip() for line in text.strip("\n").splitlines()).strip("\n")


class Server:
    def __init__(self, project: Path, port: int, database: Path, log: Path) -> None:
        self.project, self.port, self.database, self.log = project, port, database, log
        self.process: subprocess.Popen[bytes] | None = None

    def start(self) -> float:
        env = {**os.environ, "HOTEL_DB_PATH": str(self.database), "PYTHONUNBUFFERED": "1"}
        handle = self.log.open("ab")
        started = time.monotonic()
        self.process = subprocess.Popen([sys.executable, "main.py", "--port", str(self.port)],
                                        cwd=self.project, env=env, stdout=handle, stderr=subprocess.STDOUT)
        while time.monotonic() - started < 15:
            try:
                urllib.request.urlopen(f"http://localhost:{self.port}/openapi.yaml", timeout=1).read()
                return time.monotonic() - started
            except (urllib.error.URLError, ConnectionError, OSError):
                time.sleep(0.1)
        raise RuntimeError("the app did not start; see the server log")

    def stop(self) -> int:
        assert self.process is not None
        self.process.send_signal(signal.SIGINT)  # what Ctrl+C sends
        return self.process.wait(timeout=10)


def main(argv: list[str]) -> int:
    project = Path(argv[0]).resolve()
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 5080
    document = (project / "docs" / "api-check.md").read_text(encoding="utf-8")
    steps = read_steps(document)
    workdir = Path(tempfile.mkdtemp(prefix="api-check-"))
    database, server_log = workdir / "hotel.sqlite3", workdir / "server.log"
    server = Server(project, port, database, server_log)

    print(f"Project: {project.name}/   database: <tmp>/hotel.sqlite3 (empty at the start)   port: {port}")
    print(f"Python {sys.version.split()[0]}; {subprocess.run(['curl', '--version'], capture_output=True, text=True).stdout.splitlines()[0]}")
    print(f"Server started in {server.start():.2f} s: python main.py --port {port}\n")
    failures = 0
    for step in steps:
        if step.restart:
            code = server.stop()
            print(f"## {step.number}. {step.title}\nServer stopped with SIGINT (exit code {code}); "
                  f"restarted in {server.start():.2f} s over the same database file.\n")
            continue
        if step.command is None or step.expected is None:
            continue
        command = step.command.replace("localhost:5080", f"localhost:{port}").replace("'hotel.sqlite3'", f"'{database}'")
        result = subprocess.run(["bash", "-c", command], cwd=project, capture_output=True, text=True, timeout=30)
        ok = normalise(result.stdout) == normalise(step.expected)
        failures += not ok
        print(f"## {step.number}. {step.title}\n$ {step.command}\n{result.stdout.rstrip()}\n"
              f"{'✓ matches Expected' if ok else '✗ DIFFERS from Expected:' + chr(10) + step.expected}\n")
    code = server.stop()
    checked = sum(1 for step in steps if step.command and step.expected)
    print(f"Server stopped with SIGINT (exit code {code}).")
    print(f"Result: {checked - failures} of {checked} answers exactly as expected, 1 restart.\n")
    print("---- server log (uvicorn) ----")
    print(server_log.read_text(encoding="utf-8").replace(str(project), "<project>").rstrip())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
