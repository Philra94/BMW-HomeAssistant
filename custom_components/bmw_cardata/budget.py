from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DAILY_REQUEST_LIMIT, DEFAULT_REQUEST_RESERVE, DOMAIN, STORAGE_VERSION


class RequestBudgetManager:
    def __init__(self, hass: HomeAssistant, budget_key: str) -> None:
        self._daily_limit = DAILY_REQUEST_LIMIT
        self._default_reserve = DEFAULT_REQUEST_RESERVE
        self._store = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}_{budget_key}_request_budget",
        )
        self._state: dict[str, Any] | None = None

    async def _async_load(self) -> dict[str, Any]:
        if self._state is None:
            self._state = await self._store.async_load()
        if not self._state:
            self._state = self._new_state()
        if self._state.get("date") != date.today().isoformat():
            self._state = self._new_state()
        return self._state

    def _new_state(self) -> dict[str, Any]:
        return {"date": date.today().isoformat(), "count": 0, "labels": {}}

    async def async_remaining(self) -> int:
        state = await self._async_load()
        return max(self._daily_limit - int(state["count"]), 0)

    async def async_can_spend(self, cost: int = 1, reserve: int | None = None) -> bool:
        remaining = await self.async_remaining()
        reserve = self._default_reserve if reserve is None else reserve
        return remaining - cost >= reserve

    async def async_record(self, label: str) -> dict[str, Any]:
        state = await self._async_load()
        state["count"] += 1
        labels = state.setdefault("labels", {})
        labels[label] = labels.get(label, 0) + 1
        await self._store.async_save(state)
        return deepcopy(state)

    async def async_snapshot(self) -> dict[str, Any]:
        return deepcopy(await self._async_load())
