from __future__ import annotations

import pytest

pytest.importorskip("homeassistant")

from custom_components.bmw_cardata.helpers import (  # noqa: E402
    get_telematic_value,
    latest_charging_session,
    location_available,
)


def test_location_is_unavailable_when_coordinates_are_null(full_probe_payload: dict) -> None:
    assert not location_available(full_probe_payload["telematicData"])


def test_current_soc_can_be_read_from_telematics(full_probe_payload: dict) -> None:
    assert (
        get_telematic_value(
            full_probe_payload["telematicData"],
            "vehicle.drivetrain.batteryManagement.header",
        )
        == "80"
    )


def test_latest_charging_session_values(summary_snapshot: dict) -> None:
    session = latest_charging_session(
        {"data": [summary_snapshot["latestChargingSession"]]}
    )
    assert session is not None
    assert session["displayedSoc"] == 82
    assert session["displayedStartSoc"] == 41
