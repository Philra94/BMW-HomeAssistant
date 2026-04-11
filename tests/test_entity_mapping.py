from __future__ import annotations

import pytest

pytest.importorskip("homeassistant")

from custom_components.bmw_cardata.entity_descriptions import (  # noqa: E402
    BINARY_SENSOR_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS,
)


def _sensor(key: str):
    return next(description for description in SENSOR_DESCRIPTIONS if description.key == key)


def _binary_sensor(key: str):
    return next(
        description for description in BINARY_SENSOR_DESCRIPTIONS if description.key == key
    )


def test_sensor_mapping_uses_fixture_values(full_probe_payload: dict) -> None:
    telematics = full_probe_payload["telematicData"]

    assert _sensor("current_soc").value_fn(telematics) == 80
    assert _sensor("remaining_range").value_fn(telematics) == 240.0
    assert _sensor("odometer").value_fn(telematics) == 12345
    assert _sensor("charging_status").value_fn(telematics) == "NOCHARGING"
    assert _sensor("target_soc").value_fn(telematics) == 90


def test_binary_sensor_mapping_uses_fixture_values(full_probe_payload: dict) -> None:
    telematics = full_probe_payload["telematicData"]

    assert _binary_sensor("charging_port_connected").value_fn(telematics) is False
    assert _binary_sensor("hood_open").value_fn(telematics) is False
    assert _binary_sensor("driver_door_open").value_fn(telematics) is False
