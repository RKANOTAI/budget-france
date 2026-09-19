"""Reproducible PostgreSQL test server helper.

The helper uses an explicitly marked, uniquely isolated ``TEST_DATABASE_URL`` only
when requested. Without one it starts a temporary PostgreSQL cluster from a
user-space installation; Docker is neither required nor used.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DEFAULT_PGROOT = Path("/opt/data/cache/spikes/pg17-local/replay/root")
_EXTERNAL_TEST_MARKER = "BUDGET_FRANCE_ALLOW_EXTERNAL_TEST_DATABASE"
_ISOLATED_DATABASE_PATTERN = re.compile(r"^budget_france_test_[a-z0-9]{8,64}$")
_SENSITIVE_QUERY_KEYS = {"password", "passwd", "pwd", "secret", "token"}


def _redact_url(url: str) -> str:
    """Return a log-safe URL without user credentials or secret query values."""

    parts = urlsplit(url)
    if parts.hostname is None:
        return "<invalid-database-url>"
    try:
        host = parts.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parts.port}" if parts.port is not None else ""
    except ValueError:
        return "<invalid-database-url>"
    userinfo = f"{parts.username}:***@" if parts.username else ""
    query = urlencode(
        [
            (key, "***" if key.lower() in _SENSITIVE_QUERY_KEYS else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    return urlunsplit((parts.scheme, f"{userinfo}{host}{port}", parts.path, query, ""))


def _validate_external_url(url: str) -> str:
    normalized = _normalise_url(url)
    database_name = urlsplit(normalized).path.removeprefix("/")
    if not _ISOLATED_DATABASE_PATTERN.fullmatch(database_name):
        raise RuntimeError(
            "external test database must use a uniquely isolated "
            "budget_france_test_<token> database"
        )
    return normalized


def _select_external_url(explicit_url: str | None) -> str | None:
    """Select only an explicitly marked, uniquely isolated external test DB."""

    test_url = explicit_url or os.environ.get("TEST_DATABASE_URL")
    if test_url:
        if os.environ.get(_EXTERNAL_TEST_MARKER) != "1":
            raise RuntimeError(
                "external test database requires "
                f"{_EXTERNAL_TEST_MARKER}=1 and an isolated database"
            )
        return _validate_external_url(test_url)
    if os.environ.get("DATABASE_URL"):
        raise RuntimeError("ambient DATABASE_URL is not permitted by the PostgreSQL test harness")
    return None


def _normalise_url(url: str) -> str:
    """Make a SQLAlchemy URL that always selects psycopg 3."""

    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    if url.startswith("postgresql+psycopg://"):
        return url
    raise ValueError("PostgreSQL URL must use postgresql:// or postgresql+psycopg://")


def _raw_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(("postgresql", parts.netloc, parts.path, parts.query, parts.fragment))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run(
    command: list[str], *, env: dict[str, str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, env=env, text=True, capture_output=True)


@dataclass
class PostgresTestServer:
    """A temporary PostgreSQL cluster or a caller-owned external database."""

    database_url: str
    _data_dir: Path | None = None
    _pg_ctl: Path | None = None
    _env: dict[str, str] | None = None

    def __repr__(self) -> str:
        return f"PostgresTestServer(database_url={_redact_url(self.database_url)!r})"

    @classmethod
    def start(
        cls, database_url: str | None = None, pgroot: str | Path | None = None
    ) -> PostgresTestServer:
        external_url = _select_external_url(database_url)
        if external_url:
            return cls(database_url=external_url)

        root_value = pgroot if pgroot is not None else os.environ.get("PGROOT")
        root = Path(root_value or DEFAULT_PGROOT)
        bindir = root / "usr/lib/postgresql/17/bin"
        initdb = bindir / "initdb"
        pg_ctl = bindir / "pg_ctl"
        psql = bindir / "psql"
        missing = [str(path) for path in (initdb, pg_ctl, psql) if not path.is_file()]
        if missing:
            raise RuntimeError(
                "No PostgreSQL 17 user-space installation found; set PGROOT or TEST_DATABASE_URL. "
                f"Missing: {', '.join(missing)}"
            )

        data_dir = Path(tempfile.mkdtemp(prefix="budget-france-pg-"))
        env = os.environ.copy()
        env["PATH"] = f"{bindir}:{env.get('PATH', '')}"
        library_dir = root / "usr/lib/x86_64-linux-gnu"
        env["LD_LIBRARY_PATH"] = f"{library_dir}:{env.get('LD_LIBRARY_PATH', '')}".rstrip(":")
        try:
            _run(
                [
                    str(initdb),
                    "--pgdata",
                    str(data_dir),
                    "--username=postgres",
                    "--auth-local=trust",
                    "--auth-host=trust",
                    "--no-locale",
                    "--encoding=UTF8",
                ],
                env=env,
            )
            port = _free_port()
            log_path = data_dir / "postgres.log"
            _run(
                [
                    str(pg_ctl),
                    "start",
                    "--pgdata",
                    str(data_dir),
                    "--options",
                    f"-h 127.0.0.1 -k {data_dir} -p {port}",
                    "--log",
                    str(log_path),
                    "--wait",
                ],
                env=env,
            )
            raw_url = f"postgresql://postgres@127.0.0.1:{port}/postgres"
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                ready = _run([str(psql), raw_url, "-Atqc", "SELECT 1"], env=env, check=False)
                if ready.returncode == 0 and ready.stdout.strip() == "1":
                    return cls(
                        database_url=_normalise_url(raw_url),
                        _data_dir=data_dir,
                        _pg_ctl=pg_ctl,
                        _env=env,
                    )
                time.sleep(0.05)
            raise RuntimeError(f"PostgreSQL did not become ready; see {log_path}")
        except BaseException:
            if pg_ctl.is_file() and (data_dir / "postmaster.pid").exists():
                _run(
                    [str(pg_ctl), "--pgdata", str(data_dir), "--mode=immediate", "--wait", "stop"],
                    env=env,
                    check=False,
                )
            shutil.rmtree(data_dir, ignore_errors=True)
            raise

    def stop(self) -> None:
        if self._pg_ctl is None or self._data_dir is None or self._env is None:
            return
        _run(
            [
                str(self._pg_ctl),
                "--pgdata",
                str(self._data_dir),
                "--mode=fast",
                "--wait",
                "stop",
            ],
            env=self._env,
            check=False,
        )
        shutil.rmtree(self._data_dir, ignore_errors=True)


@contextmanager
def temporary_postgres(
    database_url: str | None = None,
    *,
    pgroot: str | Path | None = None,
) -> Iterator[str]:
    """Yield a psycopg SQLAlchemy URL, managing only locally started servers."""

    server = PostgresTestServer.start(database_url, pgroot)
    try:
        yield server.database_url
    finally:
        server.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url", help="Use this external PostgreSQL URL instead of starting a server"
    )
    parser.add_argument("--pgroot", help="PostgreSQL installation root for a local server")
    args = parser.parse_args()
    with temporary_postgres(args.url, pgroot=args.pgroot) as url:
        print(_redact_url(url), flush=True)
        if args.url:
            return 0
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
