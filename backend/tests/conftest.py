from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from metromobile.config import get_settings
from metromobile.db import Base

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture(autouse=True)
def _clean_settings_cache(monkeypatch):
    """Isolate METROMOBILE_* env overrides between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with Session() as s:
        yield s


@pytest.fixture
def chatr_html() -> bytes:
    return (FIXTURES / "chatr" / "plans_page.html").read_bytes()
