"""Shared fixtures: a Store backed by a throwaway SQLite file in a tmp dir."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recalldeck.db import Store


@pytest.fixture()
def store(tmp_path):
    db = Store(str(tmp_path / "recalldeck.db"))
    try:
        yield db
    finally:
        db.close()
