from __future__ import annotations

import json
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def full_probe_payload() -> dict:
    return json.loads((FIXTURES / "full_probe_latest.json").read_text())


@pytest.fixture
def summary_snapshot() -> dict:
    return json.loads((FIXTURES / "summary_snapshot.json").read_text())
