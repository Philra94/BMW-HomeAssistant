from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import BMWApiCoordinator, BMWCarDataRuntimeData
from .entity import BMWCarDataEntity
from .entity_descriptions import BMWSensorDescription, SENSOR_DESCRIPTIONS


def _coordinator_for_source(
    runtime_data: BMWCarDataRuntimeData, source: str
) -> BMWApiCoordinator:
    if source == "telematics":
        return runtime_data.telematics_coordinator
    if source == "history":
        return runtime_data.history_coordinator
    if source == "settings":
        return runtime_data.settings_coordinator
    return runtime_data.metadata_coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime_data: BMWCarDataRuntimeData = entry.runtime_data
    async_add_entities(
        BMWSensor(entry, runtime_data, description) for description in SENSOR_DESCRIPTIONS
    )


class BMWSensor(BMWCarDataEntity, SensorEntity):
    entity_description: BMWSensorDescription

    def __init__(
        self,
        entry: ConfigEntry,
        runtime_data: BMWCarDataRuntimeData,
        description: BMWSensorDescription,
    ) -> None:
        coordinator = _coordinator_for_source(runtime_data, description.source)
        super().__init__(entry, runtime_data, coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{runtime_data.vehicle_context.vin}_{description.key}"
        )

    @property
    def native_value(self):
        if not isinstance(self.coordinator.data, dict):
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.native_value is not None
