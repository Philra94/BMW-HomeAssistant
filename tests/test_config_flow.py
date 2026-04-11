from __future__ import annotations

import pytest

homeassistant = pytest.importorskip("homeassistant")

from homeassistant import config_entries  # noqa: E402

from custom_components.bmw_cardata.const import (  # noqa: E402
    CONF_CLIENT_ID,
    CONF_CONTAINER_ID,
    CONF_CONTAINER_NAME,
    CONF_ENABLE_LOCATION,
    CONF_SELECTED_VIN,
    DOMAIN,
)
from custom_components.bmw_cardata.models import (  # noqa: E402
    BMWDeviceCodePayload,
    BMWTokenSet,
    BMWVehicleContext,
    utc_now,
)

pytestmark = pytest.mark.asyncio


async def test_user_flow_requests_device_code_and_creates_entry(hass, monkeypatch) -> None:
    async def mock_request_device_code(self):
        return (
            BMWDeviceCodePayload(
                user_code="ABCD1234",
                device_code="device-code",
                verification_uri="https://customer.bmwgroup.com/oneid/link",
                interval=5,
                expires_in=300,
            ),
            "verifier",
        )

    async def mock_exchange_device_code(self, *, device_code, code_verifier):
        return BMWTokenSet(
            access_token="access",
            refresh_token="refresh",
            token_type="Bearer",
            scope="cardata:api:read openid authenticate_user",
            expires_in=3600,
            issued_at=utc_now().isoformat(),
        )

    async def mock_get_vehicle_mappings(self):
        return [{"vin": "TESTVIN1234567890", "mappingType": "PRIMARY"}]

    async def mock_bootstrap(self, **kwargs):
        return BMWVehicleContext(
            client_id="client-id",
            vin="TESTVIN1234567890",
            container_id="C123",
            container_name="ha_ev_current",
            enable_location=False,
        )

    async def mock_basic_data(self, vin):
        return {"modelName": "BMW Vehicle"}

    monkeypatch.setattr(
        "custom_components.bmw_cardata.auth.BMWAuthenticator.async_request_device_code",
        mock_request_device_code,
    )
    monkeypatch.setattr(
        "custom_components.bmw_cardata.auth.BMWAuthenticator.async_exchange_device_code",
        mock_exchange_device_code,
    )
    monkeypatch.setattr(
        "custom_components.bmw_cardata.api.BMWCarDataApiClient.async_get_vehicle_mappings",
        mock_get_vehicle_mappings,
    )
    monkeypatch.setattr(
        "custom_components.bmw_cardata.api.BMWCarDataApiClient.async_bootstrap_vehicle_context",
        mock_bootstrap,
    )
    monkeypatch.setattr(
        "custom_components.bmw_cardata.api.BMWCarDataApiClient.async_get_basic_data",
        mock_basic_data,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CLIENT_ID: "client-id",
            CONF_ENABLE_LOCATION: False,
        },
    )
    assert result["type"] == "form"
    assert result["step_id"] == "authorize"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    assert result["title"] == "BMW Vehicle"
    assert result["data"][CONF_SELECTED_VIN] == "TESTVIN1234567890"
    assert result["data"][CONF_CONTAINER_ID] == "C123"
    assert result["data"][CONF_CONTAINER_NAME] == "ha_ev_current"
