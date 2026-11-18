"""SQLAlchemy engine and metadata helpers.

The engine is created lazily and cached per URL.  Tests can point
``FABPULSE_DATABASE_URL`` at a temporary SQLite file and call
:func:`reset_engine` between cases.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from . import config

logger = logging.getLogger(__name__)

_engines: dict[str, Engine] = {}
_session_factories: dict[str, sessionmaker[Session]] = {}


def get_engine(url: str | None = None, echo: bool = False) -> Engine:
    """Return a cached SQLAlchemy engine for *url* (resolved when omitted).

    SQLite engines use ``check_same_thread=False`` so FastAPI's threadpool can
    share them, and a longer busy timeout so concurrent reads tolerate the
    ingestion writer.
    """
    resolved = url or config.resolve_database_url()
    if resolved not in _engines:
        kwargs: dict = {"pool_pre_ping": True, "echo": echo}
        if config.is_sqlite_url(resolved):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        else:
            kwargs["connect_args"] = {"connect_timeout": 5}
            kwargs["pool_size"] = 5
            kwargs["max_overflow"] = 10
        _engines[resolved] = create_engine(resolved, **kwargs)
        _session_factories[resolved] = sessionmaker(bind=_engines[resolved])
    return _engines[resolved]


def get_session_factory(url: str | None = None) -> sessionmaker[Session]:
    """Return a session factory bound to the resolved engine."""
    get_engine(url)
    resolved = url or config.resolve_database_url()
    return _session_factories[resolved]


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    """Yield a session inside a transaction and close it afterwards."""
    factory = get_session_factory(url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine(url: str | None = None) -> None:
    """Dispose and forget cached engines (all of them when *url* is omitted)."""
    global _engines, _session_factories
    targets = [url] if url else list(_engines)
    for key in targets:
        engine = _engines.pop(key, None)
        _session_factories.pop(key, None)
        if engine is not None:
            engine.dispose()
    if url is None:
        _engines = {}
        _session_factories = {}


def get_metadata():
    """Return the shared star-schema ``MetaData`` (imported lazily)."""
    from .schema import metadata

    return metadata


def as_engine(url_or_engine: str | Engine | None = None) -> Engine:
    """Return *url_or_engine* as an Engine, creating/caching one when needed."""
    if isinstance(url_or_engine, Engine):
        return url_or_engine
    return get_engine(url_or_engine)


def create_all(url_or_engine: str | Engine | None = None) -> None:
    """Create every warehouse table and index that does not exist yet."""
    from .schema import metadata

    metadata.create_all(as_engine(url_or_engine))


def drop_all(url_or_engine: str | Engine | None = None) -> None:
    """Drop every warehouse table (used by tests and ``--truncate``)."""
    from .schema import metadata

    metadata.drop_all(as_engine(url_or_engine))


def table_names(url_or_engine: str | Engine | None = None) -> list[str]:
    """Return the names of the tables currently present in the warehouse."""
    return sorted(inspect(as_engine(url_or_engine)).get_table_names())


def ping(url_or_engine: str | Engine | None = None) -> bool:
    """Return ``True`` when the warehouse answers a trivial query."""
    try:
        with as_engine(url_or_engine).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # pragma: no cover - depends on the host
        return False
