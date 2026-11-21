"""A throw-away PostgreSQL 16 cluster for the P09 evidence (the same approach as P07's E6/E9).

The build container has the PostgreSQL 16 server binaries and psql, but no Docker daemon. This
helper creates a cluster in a fresh temporary directory, owned by the ``postgres`` system user
(PostgreSQL refuses to run as root, and that user cannot enter the session's scratch folder),
listening on 127.0.0.1 only, with *trust* authentication for local test connections. It creates the
user ``hotel`` and the database ``hotel`` owned by it - the names docker-compose.yml uses - and
``drop()`` stops the server and deletes the directory again.

    with throwaway_cluster(55432) as cluster:
        cluster.psql("-c", "SELECT version();")
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

BIN = Path("/usr/lib/postgresql/16/bin")


def as_postgres(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["runuser", "-u", "postgres", "--", *command], check=True, text=True, capture_output=True)


@dataclass
class Cluster:
    directory: Path
    port: int

    @property
    def psql_args(self) -> list[str]:
        return ["psql", "-X", "-h", "127.0.0.1", "-p", str(self.port), "-U", "hotel", "-d", "hotel"]

    def psql(self, *args: str, input_text: str | None = None, check: bool = False,
             cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run([*self.psql_args, *args], input=input_text, text=True, capture_output=True, check=check,
                              cwd=cwd)

    def admin(self, sql: str) -> None:
        subprocess.run(["psql", "-X", "-q", "-h", "127.0.0.1", "-p", str(self.port), "-U", "postgres", "-d", "postgres",
                        "-v", "ON_ERROR_STOP=1", "-c", sql], check=True, text=True, capture_output=True)

    def recreate_database(self) -> None:
        """An empty ``hotel`` database (each experiment starts from nothing, like docker compose down -v)."""
        self.admin("DROP DATABASE IF EXISTS hotel WITH (FORCE);")
        self.admin("CREATE DATABASE hotel OWNER hotel;")


def start(port: int) -> Cluster:
    directory = Path(tempfile.mkdtemp(prefix="p09-pg."))
    shutil.chown(directory, "postgres", "postgres")
    os.chmod(directory, 0o700)
    data = directory / "data"
    as_postgres(str(BIN / "initdb"), "-D", str(data), "-U", "postgres", "--auth=trust", "-E", "UTF8", "--locale=C.UTF-8")
    as_postgres(str(BIN / "pg_ctl"), "-D", str(data), "-l", str(directory / "server.log"), "-w", "-o",
                f"-p {port} -c listen_addresses=127.0.0.1 -k {directory} -c max_connections=200", "start")
    for _ in range(50):
        if subprocess.run(["pg_isready", "-h", "127.0.0.1", "-p", str(port)], capture_output=True).returncode == 0:
            break
        time.sleep(0.1)
    cluster = Cluster(directory, port)
    cluster.admin("CREATE ROLE hotel LOGIN;")
    cluster.recreate_database()
    return cluster


def drop(cluster: Cluster) -> None:
    subprocess.run(["runuser", "-u", "postgres", "--", str(BIN / "pg_ctl"), "-D", str(cluster.directory / "data"),
                    "-m", "fast", "-w", "stop"], capture_output=True, text=True)
    shutil.rmtree(cluster.directory, ignore_errors=True)


@contextmanager
def throwaway_cluster(port: int) -> Iterator[Cluster]:
    cluster = start(port)
    try:
        yield cluster
    finally:
        drop(cluster)
