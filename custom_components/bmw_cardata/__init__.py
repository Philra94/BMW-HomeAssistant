from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BMWCarDataApiClient
from .auth import BMWAuthenticator
from .budget import RequestBudgetManager
from .const import (
    CONF_CLIENT_ID,
    CONF_CONTAINER_ID,
    CONF_CONTAINER_NAME,
    CONF_ENABLE_LOCATION,
    CONF_SELECTED_VIN,
    CONF_SELECTED_VINS,
    CONF_TOKEN_SET,
    CONF_VIN,
    DEFAULT_CONTAINER_NAME,
    DEFAULT_CONTAINER_PURPOSE,
    DOMAIN,
    PLATFORMS,
    SERVICE_REFRESH,
)
from .coordinator import BMWCarDataRuntimeData, async_build_runtime_data
from .models import BMWTokenSet, normalize_selected_vins

SERVICE_SCHEMA = vol.Schema({vol.Optional(CONF_VIN): cv.string})


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    async def async_handle_refresh(call: ServiceCall) -> None:
        vin = call.data.get(CONF_VIN)
        refreshes = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            runtime = entry.runtime_data
            if not isinstance(runtime, BMWCarDataRuntimeData):
                continue
            for vehicle_runtime in runtime.vehicle_runtimes.values():
                if vin and vehicle_runtime.vehicle_context.vin != vin:
                    continue
                refreshes.extend(
                    [
                        vehicle_runtime.telematics_coordinator.async_request_refresh(),
                        vehicle_runtime.metadata_coordinator.async_request_refresh(),
                        vehicle_runtime.history_coordinator.async_request_refresh(),
                        vehicle_runtime.settings_coordinator.async_request_refresh(),
                    ]
                )
        if refreshes:
            await asyncio.gather(*refreshes)

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        async_handle_refresh,
        schema=SERVICE_SCHEMA,
    )
    return True


async def _async_persist_tokens(
    hass: HomeAssistant,
    entry: ConfigEntry,
    token_set: BMWTokenSet,
) -> None:
    new_data = dict(entry.data)
    new_data[CONF_TOKEN_SET] = token_set.to_dict()
    hass.config_entries.async_update_entry(entry, data=new_data)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client_id = entry.data[CONF_CLIENT_ID]
    session = async_get_clientsession(hass)
    authenticator = BMWAuthenticator(session, client_id)
    budget_manager = RequestBudgetManager(hass, client_id)
    token_set = BMWTokenSet.from_dict(entry.data[CONF_TOKEN_SET])
    selected_vins = normalize_selected_vins(
        entry.data.get(CONF_SELECTED_VINS),
        entry.data.get(CONF_SELECTED_VIN),
    )

    api = BMWCarDataApiClient(
        session,
        authenticator,
        token_set,
        budget_manager=budget_manager,
        token_update_callback=lambda tokens: _async_persist_tokens(hass, entry, tokens),
    )

    vehicle_contexts = []
    container_id = entry.data.get(CONF_CONTAINER_ID)
    container_name = entry.data.get(CONF_CONTAINER_NAME, DEFAULT_CONTAINER_NAME)

    for vin in selected_vins:
        vehicle_context = await api.async_bootstrap_vehicle_context(
            selected_vin=vin,
            enable_location=bool(entry.data.get(CONF_ENABLE_LOCATION, False)),
            existing_container_id=container_id,
            container_name=container_name,
            container_purpose=DEFAULT_CONTAINER_PURPOSE,
        )
        vehicle_contexts.append(vehicle_context)
        container_id = vehicle_context.container_id
        container_name = vehicle_context.container_name

    if not vehicle_contexts:
        return False

    updated_data = dict(entry.data)
    updated_data.pop(CONF_SELECTED_VIN, None)
    updated_data[CONF_SELECTED_VINS] = [context.vin for context in vehicle_contexts]
    updated_data[CONF_CONTAINER_ID] = container_id
    updated_data[CONF_CONTAINER_NAME] = container_name
    updated_data[CONF_ENABLE_LOCATION] = vehicle_contexts[0].enable_location
    updated_data[CONF_TOKEN_SET] = api.token_set.to_dict()
    hass.config_entries.async_update_entry(entry, data=updated_data)

    entry.runtime_data = await async_build_runtime_data(
        hass,
        api=api,
        budget_manager=budget_manager,
        vehicle_contexts=vehicle_contexts,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version > 2:
        return False

    if entry.version == 1:
        data = dict(entry.data)
        selected_vins = normalize_selected_vins(
            data.get(CONF_SELECTED_VINS),
            data.pop(CONF_SELECTED_VIN, None),
        )
        data[CONF_SELECTED_VINS] = selected_vins

        unique_id = entry.unique_id
        client_id = data.get(CONF_CLIENT_ID)
        if unique_id != client_id and client_id:
            account_entry_exists = any(
                other.entry_id != entry.entry_id and other.unique_id == client_id
                for other in hass.config_entries.async_entries(DOMAIN)
            )
            if not account_entry_exists:
                unique_id = client_id

        hass.config_entries.async_update_entry(
            entry,
            data=data,
            unique_id=unique_id,
            version=2,
        )

    return True
