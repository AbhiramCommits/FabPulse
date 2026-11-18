"""Shared pytest fixtures.

The whole test session runs against a temporary SQLite warehouse so it never
needs a database server. The environment variable is set before ``fabpulse`` is
imported so the application's normal configuration path is exercised.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = Path(tempfile.mkdtemp(prefix="fabpulse-tests-"))
os.environ["FABPULSE_DATABASE_URL"] = f"sqlite:///{TEST_DIR / 'warehouse.db'}"
os.environ.setdefault("FABPULSE_CORS_ORIGINS", "http://localhost:5173")


def _load_generator():
    """Import ``data/generate.py`` by path (it is not an installed package)."""
    spec = importlib.util.spec_from_file_location(
        "fabpulse_generate", REPO_ROOT / "data" / "generate.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclasses resolves the defining module through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GENERATOR = _load_generator()


@pytest.fixture(scope="session")
def sample_raw(tmp_path_factory: pytest.TempPathFactory) -> tuple[pd.DataFrame, Path]:
    """Ten days of six-tool telemetry written as both Parquet and CSV."""
    frame = GENERATOR.generate_events(days=10, seed=1234, tools_per_family=2)
    out = tmp_path_factory.mktemp("raw")
    frame.to_parquet(out / "equipment_events.parquet", index=False)
    frame.to_csv(out / "equipment_events.csv", index=False)
    return frame, out


@pytest.fixture(scope="session")
def small_raw(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A very small raw file used by idempotency and parity tests."""
    frame = GENERATOR.generate_events(days=3, seed=77, tools_per_family=1)
    out = tmp_path_factory.mktemp("raw-small")
    frame.to_parquet(out / "equipment_events.parquet", index=False)
    frame.to_csv(out / "equipment_events.csv", index=False)
    return out


@pytest.fixture(scope="session")
def warehouse(sample_raw):
    """Load the session warehouse once; stats and API tests share it."""
    from fabpulse import db, ingest

    db.reset_engine()
    result = ingest.run_ingest(sample_raw[1], fmt="parquet", truncate=True)
    assert result.report.rows_loaded > 0
    return result


@pytest.fixture(scope="session")
def client(warehouse):
    """FastAPI TestClient bound to the loaded warehouse."""
    from fastapi.testclient import TestClient

    from fabpulse.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def sqlite_engine(tmp_path: Path):
    """A disposable SQLite engine for ingestion tests."""
    return create_engine(f"sqlite:///{tmp_path / 'ingest.db'}")
