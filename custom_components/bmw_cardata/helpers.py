from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, LOCATION_LATITUDE_DESCRIPTOR, LOCATION_LONGITUDE_DESCRIPTOR


def extract_items(payload: Any, preferred_keys: list[str]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in preferred_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def get_telematic_entry(
    telematic_payload: dict[str, Any] | None,
    descriptor: str,
) -> dict[str, Any] | None:
    if not telematic_payload:
        return None
    telematic_data = telematic_payload.get("telematicData", {})
    entry = telematic_data.get(descriptor)
    if isinstance(entry, dict):
        return entry
    return None


def get_telematic_value(
    telematic_payload: dict[str, Any] | None,
    descriptor: str,
) -> Any:
    entry = get_telematic_entry(telematic_payload, descriptor)
    if not entry:
        return None
    return entry.get("value")


def latest_charging_session(charging_history: dict[str, Any] | None) -> dict[str, Any] | None:
    sessions = charging_history.get("data", []) if isinstance(charging_history, dict) else []
    sessions = [session for session in sessions if isinstance(session, dict)]
    if not sessions:
        return None
    return max(sessions, key=lambda item: item.get("endTime", item.get("startTime", 0)))


def latest_location_setting(settings_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    records = settings_payload.get("data", []) if isinstance(settings_payload, dict) else []
    records = [record for record in records if isinstance(record, dict)]
    if not records:
        return None
    return max(records, key=lambda item: item.get("lastUpdated", ""))


def parse_float(value: Any) -> float | None:
    if value in (None, "", "INVALID"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    parsed = parse_float(value)
    if parsed is None:
        return None
    return int(parsed)


def boolish(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "open", "opened", "connected"}:
        return True
    if normalized in {"false", "closed", "disconnected"}:
        return False
    return None


def location_available(telematic_payload: dict[str, Any] | None) -> bool:
    latitude = parse_float(get_telematic_value(telematic_payload, LOCATION_LATITUDE_DESCRIPTOR))
    longitude = parse_float(get_telematic_value(telematic_payload, LOCATION_LONGITUDE_DESCRIPTOR))
    return latitude is not None and longitude is not None


def build_device_info(vin: str, basic_data: dict[str, Any] | None) -> DeviceInfo:
    basic_data = basic_data or {}
    model = basic_data.get("modelName") or basic_data.get("series") or vin
    brand = basic_data.get("brand") or "BMW"
    name = f"{brand} {model}".strip()
    return DeviceInfo(
        identifiers={(DOMAIN, vin)},
        manufacturer="BMW",
        model=model,
        name=name,
        serial_number=vin,
        sw_version=basic_data.get("puStep"),
    )
