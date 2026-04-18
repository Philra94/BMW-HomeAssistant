from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv

from .api import BMWCarDataApiClient
from .auth import BMWAuthenticator
from .budget import RequestBudgetManager
from .const import (
    CONFIG_ENTRY_VERSION,
    CONF_CLIENT_ID,
    CONF_CONTAINER_ID,
    CONF_CONTAINER_NAME,
    CONF_ENABLE_LOCATION,
    CONF_SELECTED_VIN,
    CONF_SELECTED_VINS,
    CONF_TOKEN_SET,
    DEFAULT_CONTAINER_NAME,
    DEFAULT_CONTAINER_PURPOSE,
    DOMAIN,
)
from .exceptions import BMWAuthError, BMWAuthPendingError, BMWCarDataError, BMWRateLimitError
from .models import BMWDeviceApprovalState, BMWTokenSet, normalize_selected_vins


class BMWCarDataConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = CONFIG_ENTRY_VERSION

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
            selected_vins = self._ordered_selected_vins(user_input.get(CONF_SELECTED_VINS))
            if selected_vins:
                return await self._async_create_or_update_entry(selected_vins)
            return self.async_show_form(
                step_id="select_vehicle",
                data_schema=self._vehicle_selection_schema(),
                errors={"base": "no_vehicles_selected"},
            )

        return self.async_show_form(
            step_id="select_vehicle",
            data_schema=self._vehicle_selection_schema(),
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
            selected_vins = normalize_selected_vins(
                self._reauth_entry.data.get(CONF_SELECTED_VINS),
                self._reauth_entry.data.get(CONF_SELECTED_VIN),
            )
            return await self._async_create_or_update_entry(
                self._ordered_selected_vins(selected_vins or [self._mappings[0]["vin"]])
            )

        if len(self._mappings) > 1:
            return await self.async_step_select_vehicle()

        return await self._async_create_or_update_entry([self._mappings[0]["vin"]])

    def _mapped_vin_options(self) -> dict[str, str]:
        return {
            str(mapping["vin"]): (
                f"{mapping['vin']} ({mapping.get('mappingType', 'UNKNOWN')})"
            )
            for mapping in self._mappings
            if mapping.get("vin")
        }

    def _ordered_selected_vins(self, selected_vins: Any) -> list[str]:
        normalized = normalize_selected_vins(selected_vins)
        if not normalized:
            return []
        selected_set = {str(vin) for vin in normalized}
        return [
            str(mapping["vin"])
            for mapping in self._mappings
            if str(mapping.get("vin")) in selected_set
        ]

    def _vehicle_selection_schema(self) -> vol.Schema:
        options = self._mapped_vin_options()
        default_vins = list(options)
        return vol.Schema(
            {
                vol.Required(
                    CONF_SELECTED_VINS,
                    default=default_vins,
                ): cv.multi_select(options)
            }
        )

    async def _async_create_or_update_entry(self, selected_vins: list[str]):
        selected_vins = self._ordered_selected_vins(selected_vins)
        if not selected_vins:
            return self.async_abort(reason="cannot_connect")

        session = async_get_clientsession(self.hass)
        authenticator = BMWAuthenticator(session, self._client_id or "")
        budget = RequestBudgetManager(self.hass, self._client_id or "account")
        api = BMWCarDataApiClient(
            session,
            authenticator,
            self._token_set or BMWTokenSet("", "", "Bearer", "", 0, ""),
            budget_manager=budget,
        )

        first_vehicle_context = None
        container_id: str | None = None
        container_name = DEFAULT_CONTAINER_NAME

        for vin in selected_vins:
            vehicle_context = await api.async_bootstrap_vehicle_context(
                selected_vin=vin,
                enable_location=self._enable_location,
                existing_container_id=container_id,
                container_name=container_name,
                container_purpose=DEFAULT_CONTAINER_PURPOSE,
            )
            if first_vehicle_context is None:
                first_vehicle_context = vehicle_context
            container_id = vehicle_context.container_id
            container_name = vehicle_context.container_name

        if first_vehicle_context is None:
            return self.async_abort(reason="cannot_connect")

        basic_data = await api.async_get_basic_data(first_vehicle_context.vin)
        title = basic_data.get("modelName") or f"BMW {first_vehicle_context.vin[-4:]}"
        if len(selected_vins) > 1:
            title = f"BMW CarData ({len(selected_vins)} vehicles)"

        data = {
            CONF_CLIENT_ID: self._client_id,
            CONF_ENABLE_LOCATION: self._enable_location,
            CONF_SELECTED_VINS: selected_vins,
            CONF_CONTAINER_ID: container_id,
            CONF_CONTAINER_NAME: container_name,
            CONF_TOKEN_SET: (self._token_set or api.token_set).to_dict(),
        }
        unique_id = self._client_id or ""
        await self.async_set_unique_id(unique_id)

        if self._reauth_entry is not None:
            return self.async_update_reload_and_abort(
                self._reauth_entry,
                unique_id=unique_id,
                data_updates=data,
            )

        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=title, data=data)
