"""Runtime configuration for FabPulse.

The warehouse URL is taken from ``FABPULSE_DATABASE_URL`` when set.  Otherwise
FabPulse probes a local PostgreSQL server (database ``fabpulse``) and falls back
to a local SQLite file when no server is reachable.  All DDL and analytical SQL
is written Postgres-first; the SQLite path exists so the whole stack still runs
on a laptop with no database server installed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# FabPulse/api/fabpulse/config.py -> repository root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
REPORTS_DIR = PROJECT_ROOT / "reports"
SQLITE_FALLBACK_PATH = DATA_DIR / "fabpulse.db"

#: Default Postgres DSN used when no explicit URL is supplied.
DEFAULT_POSTGRES_URL = os.environ.get(
    "FABPULSE_POSTGRES_URL", "postgresql+psycopg://localhost:5432/fabpulse"
)

#: Name of the environment variable that overrides everything.
DATABASE_URL_ENV = "FABPULSE_DATABASE_URL"

#: Seconds to wait for a Postgres handshake during the fallback probe.
POSTGRES_PROBE_TIMEOUT = 2


def sqlite_fallback_url() -> str:
    """Return the SQLAlchemy URL of the local SQLite fallback warehouse."""
    return f"sqlite:///{SQLITE_FALLBACK_PATH}"


def is_postgres_url(url: str) -> bool:
    """Return ``True`` when *url* points at PostgreSQL."""
    return url.startswith("postgresql") or url.startswith("postgres://")


def is_sqlite_url(url: str) -> bool:
    """Return ``True`` when *url* points at SQLite."""
    return url.startswith("sqlite")


def _postgres_reachable(url: str) -> bool:
    """Probe *url* with a short timeout.  Never raises."""
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(
            url,
            connect_args={"connect_timeout": POSTGRES_PROBE_TIMEOUT},
            pool_pre_ping=True,
        )
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        finally:
            engine.dispose()
    except Exception as exc:  # pragma: no cover - depends on the host
        logger.debug("Postgres probe failed for %s: %s", url, exc)
        return False


def resolve_database_url(probe: bool = True) -> str:
    """Resolve the warehouse URL, preferring Postgres and falling back to SQLite.

    Args:
        probe: When ``True``, verify that Postgres answers before using it.
            When ``False``, honour an explicit URL without touching the network.

    Returns:
        A SQLAlchemy-compatible database URL.
    """
    explicit = os.environ.get(DATABASE_URL_ENV)
    if explicit:
        return explicit

    if not probe:
        return DEFAULT_POSTGRES_URL

    if _postgres_reachable(DEFAULT_POSTGRES_URL):
        return DEFAULT_POSTGRES_URL

    logger.warning(
        "No PostgreSQL server reachable at %s; using SQLite fallback at %s",
        DEFAULT_POSTGRES_URL,
        SQLITE_FALLBACK_PATH,
    )
    SQLITE_FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite_fallback_url()


def database_label(url: str) -> str:
    """Return a short, safe label describing the active backend (no credentials)."""
    if is_postgres_url(url):
        return "postgresql"
    if is_sqlite_url(url):
        return "sqlite"
    return "unknown"
