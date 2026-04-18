from __future__ import annotations

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import LOCATION_LATITUDE_DESCRIPTOR, LOCATION_LONGITUDE_DESCRIPTOR
from .coordinator import BMWCarDataRuntimeData, BMWVehicleRuntimeData
from .entity import BMWCarDataEntity
from .helpers import get_telematic_value, parse_float


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime_data: BMWCarDataRuntimeData = entry.runtime_data
    async_add_entities(
        [
            BMWCarDataTracker(entry, vehicle_runtime)
            for vehicle_runtime in runtime_data.vehicle_runtimes.values()
            if vehicle_runtime.vehicle_context.enable_location
        ]
    )


class BMWCarDataTracker(BMWCarDataEntity, TrackerEntity):
    _attr_name = "Location"

    def __init__(self, entry: ConfigEntry, runtime_data: BMWVehicleRuntimeData) -> None:
        super().__init__(entry, runtime_data, runtime_data.telematics_coordinator)
        self._attr_unique_id = f"{runtime_data.vehicle_context.vin}_location"

    @property
    def latitude(self):
        return parse_float(
            get_telematic_value(self.coordinator.data, LOCATION_LATITUDE_DESCRIPTOR)
        )

    @property
    def longitude(self):
        return parse_float(
            get_telematic_value(self.coordinator.data, LOCATION_LONGITUDE_DESCRIPTOR)
        )

    @property
    def location_accuracy(self):
        return 100

    @property
    def available(self) -> bool:
        return super().available and self.latitude is not None and self.longitude is not None
