from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BMWCarDataApiClient
from .budget import RequestBudgetManager
from .const import (
    DEFAULT_HISTORY_INTERVAL,
    DEFAULT_METADATA_INTERVAL,
    DEFAULT_SETTINGS_INTERVAL,
    DEFAULT_TELEMATICS_INTERVAL,
    DOMAIN,
    STORAGE_VERSION,
)
from .exceptions import BMWCarDataError, BMWRateLimitError
from .models import BMWVehicleContext, utc_now


class BMWApiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        *,
        api: BMWCarDataApiClient,
        budget_manager: RequestBudgetManager,
        name: str,
        storage_key: str,
        update_interval,
        update_method: Callable[[], Awaitable[dict[str, Any]]],
    ) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=name,
            update_interval=update_interval,
        )
        self._api = api
        self._budget_manager = budget_manager
        self._update_method = update_method
        self._store = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}_{storage_key}_cache",
        )

    async def _async_load_cached(self) -> dict[str, Any] | None:
        payload = await self._store.async_load()
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            return payload["data"]
        return None

    async def _async_save_cached(self, data: dict[str, Any]) -> None:
        await self._store.async_save(
            {"updated_at": utc_now().isoformat(), "data": data}
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self._update_method()
        except BMWRateLimitError as err:
            if self.data:
                return self.data
            cached = await self._async_load_cached()
            if cached:
                return cached
            raise UpdateFailed(str(err)) from err
        except BMWCarDataError as err:
            if self.data:
                return self.data
            cached = await self._async_load_cached()
            if cached:
                return cached
            raise UpdateFailed(str(err)) from err

        await self._async_save_cached(data)
        return data


@dataclass(slots=True)
class BMWVehicleRuntimeData:
    vehicle_context: BMWVehicleContext
    telematics_coordinator: BMWApiCoordinator
    metadata_coordinator: BMWApiCoordinator
    history_coordinator: BMWApiCoordinator
    settings_coordinator: BMWApiCoordinator


@dataclass(slots=True)
class BMWCarDataRuntimeData:
    api: BMWCarDataApiClient
    budget_manager: RequestBudgetManager
    vehicle_runtimes: dict[str, BMWVehicleRuntimeData]


async def async_build_vehicle_runtime(
    hass: HomeAssistant,
    *,
    api: BMWCarDataApiClient,
    budget_manager: RequestBudgetManager,
    vehicle_context: BMWVehicleContext,
) -> BMWVehicleRuntimeData:
    telematics = BMWApiCoordinator(
        hass,
        api=api,
        budget_manager=budget_manager,
        name=f"{DOMAIN}_telematics_{vehicle_context.vin}",
        storage_key=f"{vehicle_context.vin}_telematics",
        update_interval=DEFAULT_TELEMATICS_INTERVAL,
        update_method=lambda: api.async_get_telematic_data(
            vehicle_context.vin, vehicle_context.container_id
        ),
    )
    metadata = BMWApiCoordinator(
        hass,
        api=api,
        budget_manager=budget_manager,
        name=f"{DOMAIN}_metadata_{vehicle_context.vin}",
        storage_key=f"{vehicle_context.vin}_metadata",
        update_interval=DEFAULT_METADATA_INTERVAL,
        update_method=lambda: api.async_get_basic_data(vehicle_context.vin),
    )
    history = BMWApiCoordinator(
        hass,
        api=api,
        budget_manager=budget_manager,
        name=f"{DOMAIN}_history_{vehicle_context.vin}",
        storage_key=f"{vehicle_context.vin}_history",
        update_interval=DEFAULT_HISTORY_INTERVAL,
        update_method=lambda: api.async_get_charging_history(vehicle_context.vin),
    )
    settings = BMWApiCoordinator(
        hass,
        api=api,
        budget_manager=budget_manager,
        name=f"{DOMAIN}_settings_{vehicle_context.vin}",
        storage_key=f"{vehicle_context.vin}_settings",
        update_interval=DEFAULT_SETTINGS_INTERVAL,
        update_method=lambda: api.async_get_location_based_charging_settings(
            vehicle_context.vin
        ),
    )

    for coordinator in (telematics, metadata, history, settings):
        await coordinator.async_config_entry_first_refresh()

    return BMWVehicleRuntimeData(
        vehicle_context=vehicle_context,
        telematics_coordinator=telematics,
        metadata_coordinator=metadata,
        history_coordinator=history,
        settings_coordinator=settings,
    )


async def async_build_runtime_data(
    hass: HomeAssistant,
    *,
    api: BMWCarDataApiClient,
    budget_manager: RequestBudgetManager,
    vehicle_contexts: list[BMWVehicleContext],
) -> BMWCarDataRuntimeData:
    vehicle_runtimes = {}
    for vehicle_context in vehicle_contexts:
        vehicle_runtimes[vehicle_context.vin] = await async_build_vehicle_runtime(
            hass,
            api=api,
            budget_manager=budget_manager,
            vehicle_context=vehicle_context,
        )

    return BMWCarDataRuntimeData(
        api=api,
        budget_manager=budget_manager,
        vehicle_runtimes=vehicle_runtimes,
    )
