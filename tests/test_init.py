from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

homeassistant = pytest.importorskip("homeassistant")

from custom_components import bmw_cardata as integration  # noqa: E402
from custom_components.bmw_cardata.const import (  # noqa: E402
    CONF_CLIENT_ID,
    CONF_CONTAINER_ID,
    CONF_CONTAINER_NAME,
    CONF_ENABLE_LOCATION,
    CONF_SELECTED_VIN,
    CONF_SELECTED_VINS,
    CONF_TOKEN_SET,
)
from custom_components.bmw_cardata.coordinator import (  # noqa: E402
    BMWCarDataRuntimeData,
    BMWVehicleRuntimeData,
)
from custom_components.bmw_cardata.models import (  # noqa: E402
    BMWTokenSet,
    BMWVehicleContext,
    utc_now,
)
from custom_components.bmw_cardata.sensor import async_setup_entry as sensor_setup_entry  # noqa: E402
from custom_components.bmw_cardata.entity_descriptions import SENSOR_DESCRIPTIONS  # noqa: E402

pytestmark = pytest.mark.asyncio


def _token_set() -> BMWTokenSet:
    return BMWTokenSet(
        access_token="access",
        refresh_token="refresh",
        token_type="Bearer",
        scope="cardata:api:read openid authenticate_user",
        expires_in=3600,
        issued_at=utc_now().isoformat(),
    )


async def test_async_setup_entry_bootstraps_all_selected_vins(hass, monkeypatch) -> None:
    bootstrapped_vins: list[str] = []
    captured_vins: list[str] = []

    async def mock_bootstrap(self, **kwargs):
        vin = kwargs["selected_vin"]
        bootstrapped_vins.append(vin)
        return BMWVehicleContext(
            client_id="client-id",
            vin=vin,
            container_id="C123",
            container_name="ha_ev_current",
            enable_location=True,
        )

    async def mock_build_runtime_data(hass, *, api, budget_manager, vehicle_contexts):
        captured_vins.extend(context.vin for context in vehicle_contexts)
        return "runtime-data"

    monkeypatch.setattr(integration, "async_get_clientsession", lambda hass: object())
    monkeypatch.setattr(
        "custom_components.bmw_cardata.api.BMWCarDataApiClient.async_bootstrap_vehicle_context",
        mock_bootstrap,
    )
    monkeypatch.setattr(integration, "async_build_runtime_data", mock_build_runtime_data)

    updated_data: dict | None = None

    def mock_update_entry(entry, *, data=None, **kwargs):
        nonlocal updated_data
        if data is not None:
            updated_data = data
            entry.data = data

    hass.config_entries.async_update_entry = mock_update_entry
    hass.config_entries.async_forward_entry_setups = AsyncMock()

    entry = SimpleNamespace(
        data={
            CONF_CLIENT_ID: "client-id",
            CONF_ENABLE_LOCATION: True,
            CONF_SELECTED_VINS: ["VIN1", "VIN2"],
            CONF_TOKEN_SET: _token_set().to_dict(),
        },
        runtime_data=None,
    )

    result = await integration.async_setup_entry(hass, entry)

    assert result is True
    assert bootstrapped_vins == ["VIN1", "VIN2"]
    assert captured_vins == ["VIN1", "VIN2"]
    assert entry.runtime_data == "runtime-data"
    assert updated_data is not None
    assert updated_data[CONF_SELECTED_VINS] == ["VIN1", "VIN2"]
    assert updated_data[CONF_CONTAINER_ID] == "C123"
    assert updated_data[CONF_CONTAINER_NAME] == "ha_ev_current"


async def test_async_migrate_entry_wraps_legacy_selected_vin(hass) -> None:
    entry = SimpleNamespace(
        entry_id="entry-1",
        version=1,
        unique_id="client-id:VIN1",
        data={
            CONF_CLIENT_ID: "client-id",
            CONF_SELECTED_VIN: "VIN1",
        },
    )

    hass.config_entries.async_entries = lambda domain: [entry]

    def mock_update_entry(entry, *, data=None, unique_id=None, version=None, **kwargs):
        if data is not None:
            entry.data = data
        if unique_id is not None:
            entry.unique_id = unique_id
        if version is not None:
            entry.version = version

    hass.config_entries.async_update_entry = mock_update_entry

    result = await integration.async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == 2
    assert entry.unique_id == "client-id"
    assert entry.data[CONF_SELECTED_VINS] == ["VIN1"]
    assert CONF_SELECTED_VIN not in entry.data


async def test_sensor_setup_entry_creates_entities_for_each_vehicle(hass) -> None:
    class FakeCoordinator:
        def __init__(self, data):
            self.data = data
            self.last_update_success = True

        def async_add_listener(self, update_callback):
            return lambda: None

    vehicle_one = BMWVehicleRuntimeData(
        vehicle_context=BMWVehicleContext(
            client_id="client-id",
            vin="VIN1",
            container_id="C123",
            container_name="ha_ev_current",
            enable_location=False,
        ),
        telematics_coordinator=FakeCoordinator({"telematicData": {}}),
        metadata_coordinator=FakeCoordinator({"modelName": "BMW i3 94"}),
        history_coordinator=FakeCoordinator({"data": []}),
        settings_coordinator=FakeCoordinator({"data": []}),
    )
    vehicle_two = BMWVehicleRuntimeData(
        vehicle_context=BMWVehicleContext(
            client_id="client-id",
            vin="VIN2",
            container_id="C123",
            container_name="ha_ev_current",
            enable_location=False,
        ),
        telematics_coordinator=FakeCoordinator({"telematicData": {}}),
        metadata_coordinator=FakeCoordinator({"modelName": "BMW i4"}),
        history_coordinator=FakeCoordinator({"data": []}),
        settings_coordinator=FakeCoordinator({"data": []}),
    )
    runtime_data = BMWCarDataRuntimeData(
        api=object(),
        budget_manager=object(),
        scheduler=object(),
        vehicle_runtimes={"VIN1": vehicle_one, "VIN2": vehicle_two},
    )
    entry = SimpleNamespace(runtime_data=runtime_data)
    entities = []

    await sensor_setup_entry(hass, entry, lambda new_entities: entities.extend(new_entities))

    assert len(entities) == len(SENSOR_DESCRIPTIONS) * 2
    assert {entity.device_info["serial_number"] for entity in entities} == {"VIN1", "VIN2"}
