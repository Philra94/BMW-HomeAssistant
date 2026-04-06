from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorEntityDescription
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfLength, UnitOfPower

from .helpers import (
    boolish,
    get_telematic_value,
    latest_charging_session,
    parse_float,
    parse_int,
)


def _telematic_value(descriptor: str) -> Callable[[dict[str, Any]], Any]:
    return lambda payload: get_telematic_value(payload, descriptor)


def _telematic_float(descriptor: str) -> Callable[[dict[str, Any]], Any]:
    return lambda payload: parse_float(get_telematic_value(payload, descriptor))


def _telematic_int(descriptor: str) -> Callable[[dict[str, Any]], Any]:
    return lambda payload: parse_int(get_telematic_value(payload, descriptor))


def _telematic_boolish(descriptor: str) -> Callable[[dict[str, Any]], Any]:
    return lambda payload: boolish(get_telematic_value(payload, descriptor))


def _latest_history_value(key: str) -> Callable[[dict[str, Any]], Any]:
    def reader(payload: dict[str, Any]) -> Any:
        session = latest_charging_session(payload)
        return session.get(key) if session else None

    return reader


def _charging_port_connected(payload: dict[str, Any]) -> bool | None:
    value = get_telematic_value(payload, "vehicle.body.chargingPort.status")
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if normalized == "DISCONNECTED":
        return False
    if normalized:
        return True
    return None


def _remaining_range(payload: dict[str, Any]) -> float | None:
    value = parse_float(
        get_telematic_value(payload, "vehicle.drivetrain.electricEngine.remainingElectricRange")
    )
    if value is not None:
        return value
    return parse_float(
        get_telematic_value(
            payload, "vehicle.drivetrain.electricEngine.kombiRemainingElectricRange"
        )
    )


@dataclass(frozen=True, kw_only=True)
class BMWSensorDescription(SensorEntityDescription):
    source: str
    value_fn: Callable[[dict[str, Any]], Any]


@dataclass(frozen=True, kw_only=True)
class BMWBinarySensorDescription(BinarySensorEntityDescription):
    source: str
    value_fn: Callable[[dict[str, Any]], Any]


SENSOR_DESCRIPTIONS: tuple[BMWSensorDescription, ...] = (
    BMWSensorDescription(
        key="current_soc",
        name="Current state of charge",
        icon="mdi:battery",
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        source="telematics",
        value_fn=_telematic_int("vehicle.drivetrain.batteryManagement.header"),
    ),
    BMWSensorDescription(
        key="target_soc",
        name="Target state of charge",
        icon="mdi:battery-charging-100",
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        source="telematics",
        value_fn=_telematic_int("vehicle.powertrain.electric.battery.stateOfCharge.target"),
    ),
    BMWSensorDescription(
        key="remaining_range",
        name="Remaining range",
        icon="mdi:map-marker-distance",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        source="telematics",
        value_fn=_remaining_range,
    ),
    BMWSensorDescription(
        key="odometer",
        name="Odometer",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class="total",
        source="telematics",
        value_fn=_telematic_int("vehicle.vehicle.travelledDistance"),
    ),
    BMWSensorDescription(
        key="battery_size_max",
        name="Battery size",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        source="telematics",
        value_fn=_telematic_float("vehicle.drivetrain.batteryManagement.batterySizeMax"),
    ),
    BMWSensorDescription(
        key="battery_max_energy",
        name="Maximum usable energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        source="telematics",
        value_fn=_telematic_float("vehicle.drivetrain.batteryManagement.maxEnergy"),
    ),
    BMWSensorDescription(
        key="charging_status",
        name="Charging status",
        icon="mdi:ev-station",
        source="telematics",
        value_fn=_telematic_value("vehicle.drivetrain.electricEngine.charging.status"),
    ),
    BMWSensorDescription(
        key="charging_hv_status",
        name="High-voltage charging status",
        icon="mdi:flash",
        source="telematics",
        value_fn=_telematic_value("vehicle.drivetrain.electricEngine.charging.hvStatus"),
    ),
    BMWSensorDescription(
        key="charging_connector_status",
        name="Charging connector status",
        icon="mdi:power-plug",
        source="telematics",
        value_fn=_telematic_value("vehicle.drivetrain.electricEngine.charging.connectorStatus"),
    ),
    BMWSensorDescription(
        key="charging_time_remaining",
        name="Charging time remaining",
        icon="mdi:timer-outline",
        native_unit_of_measurement="min",
        source="telematics",
        value_fn=_telematic_int("vehicle.drivetrain.electricEngine.charging.timeRemaining"),
    ),
    BMWSensorDescription(
        key="charging_last_reason",
        name="Last charging reason",
        icon="mdi:history",
        source="telematics",
        value_fn=_telematic_value("vehicle.drivetrain.electricEngine.charging.lastChargingReason"),
    ),
    BMWSensorDescription(
        key="charging_last_result",
        name="Last charging result",
        icon="mdi:check-decagram",
        source="telematics",
        value_fn=_telematic_value("vehicle.drivetrain.electricEngine.charging.lastChargingResult"),
    ),
    BMWSensorDescription(
        key="weekly_distance_long_term",
        name="Average weekly distance (long term)",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        source="telematics",
        value_fn=_telematic_float("vehicle.vehicle.averageWeeklyDistanceLongTerm"),
    ),
    BMWSensorDescription(
        key="weekly_distance_short_term",
        name="Average weekly distance (short term)",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        source="telematics",
        value_fn=_telematic_float("vehicle.vehicle.averageWeeklyDistanceShortTerm"),
    ),
    BMWSensorDescription(
        key="average_aux_power",
        name="Average auxiliary power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        source="telematics",
        value_fn=_telematic_float("vehicle.vehicle.avgAuxPower"),
    ),
    BMWSensorDescription(
        key="condition_based_service_count",
        name="Condition based service messages",
        icon="mdi:wrench-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        source="telematics",
        value_fn=_telematic_int("vehicle.status.conditionBasedServicesCount"),
    ),
    BMWSensorDescription(
        key="service_distance_warning",
        name="Service distance warning",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        source="telematics",
        value_fn=_telematic_int("vehicle.status.serviceDistance.yellow"),
    ),
    BMWSensorDescription(
        key="service_time_warning",
        name="Service time warning",
        native_unit_of_measurement="weeks",
        entity_category=EntityCategory.DIAGNOSTIC,
        source="telematics",
        value_fn=_telematic_int("vehicle.status.serviceTime.yellow"),
    ),
    BMWSensorDescription(
        key="inspection_warning",
        name="Inspection warning",
        native_unit_of_measurement="months",
        entity_category=EntityCategory.DIAGNOSTIC,
        source="telematics",
        value_fn=_telematic_int("vehicle.status.serviceTime.hUandAuServiceYellow"),
    ),
    BMWSensorDescription(
        key="latest_charge_end_soc",
        name="Latest charge end state of charge",
        icon="mdi:battery-charging-high",
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        source="history",
        value_fn=_latest_history_value("displayedSoc"),
    ),
    BMWSensorDescription(
        key="latest_charge_start_soc",
        name="Latest charge start state of charge",
        icon="mdi:battery-start",
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        source="history",
        value_fn=_latest_history_value("displayedStartSoc"),
    ),
    BMWSensorDescription(
        key="latest_charge_mileage",
        name="Latest charge mileage",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        source="history",
        value_fn=_latest_history_value("mileage"),
    ),
)


BINARY_SENSOR_DESCRIPTIONS: tuple[BMWBinarySensorDescription, ...] = (
    BMWBinarySensorDescription(
        key="charging_port_connected",
        name="Charging port connected",
        icon="mdi:power-plug-battery",
        source="telematics",
        value_fn=_charging_port_connected,
    ),
    BMWBinarySensorDescription(
        key="hood_open",
        name="Hood open",
        device_class=BinarySensorDeviceClass.DOOR,
        source="telematics",
        value_fn=_telematic_boolish("vehicle.body.hood.isOpen"),
    ),
    BMWBinarySensorDescription(
        key="trunk_open",
        name="Trunk open",
        device_class=BinarySensorDeviceClass.DOOR,
        source="telematics",
        value_fn=_telematic_boolish("vehicle.body.trunk.isOpen"),
    ),
    BMWBinarySensorDescription(
        key="driver_door_open",
        name="Driver door open",
        device_class=BinarySensorDeviceClass.DOOR,
        source="telematics",
        value_fn=_telematic_boolish("vehicle.cabin.door.row1.driver.isOpen"),
    ),
    BMWBinarySensorDescription(
        key="front_passenger_door_open",
        name="Front passenger door open",
        device_class=BinarySensorDeviceClass.DOOR,
        source="telematics",
        value_fn=_telematic_boolish("vehicle.cabin.door.row1.passenger.isOpen"),
    ),
    BMWBinarySensorDescription(
        key="rear_left_door_open",
        name="Rear left door open",
        device_class=BinarySensorDeviceClass.DOOR,
        source="telematics",
        value_fn=_telematic_boolish("vehicle.cabin.door.row2.driver.isOpen"),
    ),
    BMWBinarySensorDescription(
        key="rear_right_door_open",
        name="Rear right door open",
        device_class=BinarySensorDeviceClass.DOOR,
        source="telematics",
        value_fn=_telematic_boolish("vehicle.cabin.door.row2.passenger.isOpen"),
    ),
)
