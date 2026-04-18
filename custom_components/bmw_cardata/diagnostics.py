from __future__ import annotations

from dataclasses import asdict
from copy import deepcopy
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CLIENT_ID,
    CONF_SELECTED_VIN,
    CONF_SELECTED_VINS,
    LOCATION_LATITUDE_DESCRIPTOR,
    LOCATION_LONGITUDE_DESCRIPTOR,
)
from .coordinator import BMWCarDataRuntimeData

TO_REDACT = {
    CONF_CLIENT_ID,
    CONF_SELECTED_VIN,
    CONF_SELECTED_VINS,
    "access_token",
    "refresh_token",
    "id_token",
    "device_code",
    "code_verifier",
    "verification_uri",
    "direct_verification_uri",
    "gcid",
}


def _redact_location_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return payload
    redacted = deepcopy(payload)
    telematic_data = redacted.get("telematicData", {})
    for descriptor in (LOCATION_LATITUDE_DESCRIPTOR, LOCATION_LONGITUDE_DESCRIPTOR):
        if descriptor in telematic_data and isinstance(telematic_data[descriptor], dict):
            telematic_data[descriptor]["value"] = "REDACTED"
    return redacted


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    runtime_data: BMWCarDataRuntimeData = entry.runtime_data
    vehicle_diagnostics = {}
    for vin, vehicle_runtime in runtime_data.vehicle_runtimes.items():
        vehicle_diagnostics[vin] = {
            "vehicle_context": async_redact_data(
                asdict(vehicle_runtime.vehicle_context), TO_REDACT
            ),
            "telematics": _redact_location_payload(
                vehicle_runtime.telematics_coordinator.data
            ),
            "basic_data": vehicle_runtime.metadata_coordinator.data,
            "charging_history": vehicle_runtime.history_coordinator.data,
            "location_settings": vehicle_runtime.settings_coordinator.data,
        }

    diagnostics = {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "budget": await runtime_data.budget_manager.async_snapshot(),
        "vehicles": vehicle_diagnostics,
    }
    return diagnostics
