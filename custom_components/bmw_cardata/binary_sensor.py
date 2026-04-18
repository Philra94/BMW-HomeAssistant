from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import BMWCarDataRuntimeData, BMWVehicleRuntimeData
from .entity import BMWCarDataEntity
from .entity_descriptions import BINARY_SENSOR_DESCRIPTIONS, BMWBinarySensorDescription


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime_data: BMWCarDataRuntimeData = entry.runtime_data
    async_add_entities(
        BMWBinarySensor(entry, vehicle_runtime, description)
        for vehicle_runtime in runtime_data.vehicle_runtimes.values()
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class BMWBinarySensor(BMWCarDataEntity, BinarySensorEntity):
    entity_description: BMWBinarySensorDescription

    def __init__(
        self,
        entry: ConfigEntry,
        runtime_data: BMWVehicleRuntimeData,
        description: BMWBinarySensorDescription,
    ) -> None:
        super().__init__(entry, runtime_data, runtime_data.telematics_coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{runtime_data.vehicle_context.vin}_{description.key}"
        )

    @property
    def is_on(self):
        if not isinstance(self.coordinator.data, dict):
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.is_on is not None
