from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.core import callback
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
    CONF_TOKEN_SET,
    DEFAULT_CONTAINER_NAME,
    DEFAULT_CONTAINER_PURPOSE,
    DOMAIN,
)
from .exceptions import BMWAuthError, BMWAuthPendingError, BMWCarDataError, BMWRateLimitError
from .models import BMWDeviceApprovalState, BMWTokenSet


class BMWCarDataConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._client_id: str | None = None
        self._enable_location = False
        self._approval_state: BMWDeviceApprovalState | None = None
        self._token_set: BMWTokenSet | None = None
        self._mappings: list[dict[str, Any]] = []
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            self._client_id = user_input[CONF_CLIENT_ID].strip()
            self._enable_location = bool(user_input.get(CONF_ENABLE_LOCATION, False))

            try:
                await self._async_start_device_flow()
            except BMWRateLimitError:
                errors["base"] = "rate_limited"
            except BMWAuthError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_authorize()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CLIENT_ID): str,
                    vol.Optional(CONF_ENABLE_LOCATION, default=False): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_authorize(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if self._approval_state is None:
            return await self.async_step_user()

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            authenticator = BMWAuthenticator(session, self._approval_state.client_id)
            try:
                self._token_set = await authenticator.async_exchange_device_code(
                    device_code=self._approval_state.device_code,
                    code_verifier=self._approval_state.code_verifier,
                )
            except BMWAuthPendingError:
                errors["base"] = "authorization_pending"
            except BMWRateLimitError:
                errors["base"] = "rate_limited"
            except BMWAuthError:
                errors["base"] = "invalid_auth"
            else:
                return await self._async_continue_after_auth()

        return self.async_show_form(
            step_id="authorize",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={
                "user_code": self._approval_state.user_code,
                "verification_url": self._approval_state.direct_verification_uri,
            },
        )

    async def async_step_select_vehicle(
        self, user_input: dict[str, Any] | None = None
    ):
        if user_input is not None:
            return await self._async_create_or_update_entry(user_input[CONF_SELECTED_VIN])

        options = {
            mapping["vin"]: f"{mapping['vin']} ({mapping.get('mappingType', 'UNKNOWN')})"
            for mapping in self._mappings
        }
        return self.async_show_form(
            step_id="select_vehicle",
            data_schema=vol.Schema(
                {vol.Required(CONF_SELECTED_VIN): vol.In(options)}
            ),
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        if self._reauth_entry is None:
            return self.async_abort(reason="cannot_connect")
        self._client_id = self._reauth_entry.data[CONF_CLIENT_ID]
        self._enable_location = bool(
            self._reauth_entry.data.get(CONF_ENABLE_LOCATION, False)
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._async_start_device_flow()
            except BMWRateLimitError:
                errors["base"] = "rate_limited"
            except BMWAuthError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_authorize()

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({}),
            errors=errors,
        )

    async def _async_start_device_flow(self) -> None:
        session = async_get_clientsession(self.hass)
        authenticator = BMWAuthenticator(session, self._client_id or "")
        device_payload, code_verifier = await authenticator.async_request_device_code()
        self._approval_state = BMWDeviceApprovalState(
            client_id=self._client_id or "",
            code_verifier=code_verifier,
            device_code=device_payload.device_code,
            user_code=device_payload.user_code,
            verification_uri=device_payload.verification_uri,
            interval=device_payload.interval,
            expires_in=device_payload.expires_in,
        )

    async def _async_continue_after_auth(self):
        session = async_get_clientsession(self.hass)
        authenticator = BMWAuthenticator(session, self._client_id or "")
        api = BMWCarDataApiClient(
            session,
            authenticator,
            self._token_set or BMWTokenSet("", "", "Bearer", "", 0, ""),
            budget_manager=RequestBudgetManager(self.hass, self._client_id or "setup"),
        )
        try:
            self._mappings = await api.async_get_vehicle_mappings()
        except BMWRateLimitError:
            return self.async_abort(reason="cannot_connect")
        except BMWCarDataError:
            return self.async_abort(reason="cannot_connect")

        if not self._mappings:
            return self.async_abort(reason="cannot_connect")

        if self._reauth_entry is not None:
            return await self._async_create_or_update_entry(
                self._reauth_entry.data.get(CONF_SELECTED_VIN, self._mappings[0]["vin"])
            )

        if len(self._mappings) > 1:
            return await self.async_step_select_vehicle()

        return await self._async_create_or_update_entry(self._mappings[0]["vin"])

    async def _async_create_or_update_entry(self, selected_vin: str):
        session = async_get_clientsession(self.hass)
        authenticator = BMWAuthenticator(session, self._client_id or "")
        budget = RequestBudgetManager(self.hass, self._client_id or selected_vin)
        api = BMWCarDataApiClient(
            session,
            authenticator,
            self._token_set or BMWTokenSet("", "", "Bearer", "", 0, ""),
            budget_manager=budget,
        )
        vehicle_context = await api.async_bootstrap_vehicle_context(
            selected_vin=selected_vin,
            enable_location=self._enable_location,
            container_name=DEFAULT_CONTAINER_NAME,
            container_purpose=DEFAULT_CONTAINER_PURPOSE,
        )
        basic_data = await api.async_get_basic_data(selected_vin)
        title = basic_data.get("modelName") or f"BMW {selected_vin[-4:]}"

        data = {
            CONF_CLIENT_ID: self._client_id,
            CONF_ENABLE_LOCATION: self._enable_location,
            CONF_SELECTED_VIN: vehicle_context.vin,
            CONF_CONTAINER_ID: vehicle_context.container_id,
            CONF_CONTAINER_NAME: vehicle_context.container_name,
            CONF_TOKEN_SET: (self._token_set or api.token_set).to_dict(),
        }
        unique_id = f"{self._client_id}:{vehicle_context.vin}"
        await self.async_set_unique_id(unique_id)

        if self._reauth_entry is not None:
            return self.async_update_reload_and_abort(
                self._reauth_entry,
                unique_id=unique_id,
                data_updates=data,
            )

        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=title, data=data)
