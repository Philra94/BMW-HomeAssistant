from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BMWApiCoordinator, BMWCarDataRuntimeData
from .helpers import build_device_info


class BMWCarDataEntity(CoordinatorEntity[BMWApiCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        runtime_data: BMWCarDataRuntimeData,
        coordinator: BMWApiCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._runtime_data = runtime_data

    @property
    def device_info(self):
        return build_device_info(
            self._runtime_data.vehicle_context.vin,
            self._runtime_data.metadata_coordinator.data,
        )
