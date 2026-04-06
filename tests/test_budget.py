from __future__ import annotations

import pytest

pytest.importorskip("homeassistant")

from custom_components.bmw_cardata.budget import RequestBudgetManager  # noqa: E402

pytestmark = pytest.mark.asyncio


async def test_request_budget_manager_records_requests(hass) -> None:
    manager = RequestBudgetManager(hass, "test-client")

    assert await manager.async_remaining() == 50

    await manager.async_record("GET /customers/vehicles/mappings")

    snapshot = await manager.async_snapshot()
    assert snapshot["count"] == 1
    assert snapshot["labels"]["GET /customers/vehicles/mappings"] == 1
