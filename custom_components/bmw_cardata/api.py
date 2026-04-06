from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import ClientError, ClientSession

from .auth import BMWAuthenticator
from .const import (
    API_BASE_URL,
    API_VERSION,
    CHARGING_HISTORY_DAY_WINDOWS,
    CONF_CONTAINER_NAME,
    DEFAULT_CHARGING_HISTORY_DAYS,
    DEFAULT_CONTAINER_NAME,
    DEFAULT_CONTAINER_PURPOSE,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_TELEMATIC_DESCRIPTORS,
    LOCATION_DESCRIPTORS,
)
from .exceptions import BMWCarDataError, BMWRateLimitError, BMWReauthRequiredError
from .helpers import extract_items
from .models import BMWTokenSet, BMWVehicleContext, utc_now

_LOGGER = logging.getLogger(__name__)


def _format_api_datetime(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


class BMWCarDataApiClient:
    def __init__(
        self,
        session: ClientSession,
        authenticator: BMWAuthenticator,
        token_set: BMWTokenSet,
        *,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
        budget_manager: Any | None = None,
        token_update_callback: Callable[[BMWTokenSet], Awaitable[None]] | None = None,
    ) -> None:
        self._session = session
        self._authenticator = authenticator
        self._token_set = token_set
        self._timeout = timeout
        self._budget_manager = budget_manager
        self._token_update_callback = token_update_callback

    @property
    def token_set(self) -> BMWTokenSet:
        return self._token_set

    async def _async_maybe_record_budget(self, label: str) -> None:
        if self._budget_manager is None:
            return
        if not await self._budget_manager.async_can_spend():
            raise BMWRateLimitError("Local BMW request budget has been exhausted.")
        await self._budget_manager.async_record(label)

    async def _async_refresh_and_persist(self) -> None:
        self._token_set = await self._authenticator.async_refresh_tokens(
            self._token_set.refresh_token
        )
        if self._token_update_callback is not None:
            await self._token_update_callback(self._token_set)

    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        accept: str = "application/json",
        retry_on_401: bool = True,
    ) -> Any:
        if not self._token_set.access_token_is_fresh():
            await self._async_refresh_and_persist()

        label = f"{method.upper()} {path}"
        await self._async_maybe_record_budget(label)

        headers = {
            "Authorization": f"Bearer {self._token_set.access_token}",
            "Accept": accept,
            "x-version": API_VERSION,
        }

        try:
            response = await self._session.request(
                method=method.upper(),
                url=f"{API_BASE_URL}{path}",
                params=params,
                json=json_body,
                headers=headers,
                timeout=self._timeout,
            )
        except ClientError as err:
            raise BMWCarDataError(f"BMW API request failed: {err}") from err

        async with response:
            if response.status == 401 and retry_on_401:
                await self._async_refresh_and_persist()
                return await self._async_request(
                    method,
                    path,
                    params=params,
                    json_body=json_body,
                    accept=accept,
                    retry_on_401=False,
                )

            if accept.startswith("image/"):
                if response.status >= 400:
                    text = await response.text()
                    raise BMWCarDataError(
                        f"BMW API request {label} failed with {response.status}: {text}"
                    )
                return await response.read()

            try:
                payload = await response.json()
            except Exception:
                payload = {"raw_response": await response.text()}

            if response.status >= 400:
                detail = (
                    payload.get("exveErrorMsg")
                    or payload.get("error_description")
                    or payload.get("raw_response")
                    or payload
                )
                if response.status == 403 and "rate limit" in str(detail).lower():
                    raise BMWRateLimitError(str(detail))
                if response.status in (401, 403) and "refresh" in str(detail).lower():
                    raise BMWReauthRequiredError(str(detail))
                raise BMWCarDataError(
                    f"BMW API request {label} failed with {response.status}: {detail}"
                )

            return payload

    async def async_get_vehicle_mappings(self) -> list[dict[str, Any]]:
        payload = await self._async_request("GET", "/customers/vehicles/mappings")
        mappings = extract_items(payload, ["mappings", "data", "vehicles"])
        if not mappings and isinstance(payload, dict) and payload.get("vin"):
            mappings = [payload]
        return mappings

    async def async_list_containers(self) -> list[dict[str, Any]]:
        payload = await self._async_request("GET", "/customers/containers")
        containers = extract_items(payload, ["containers", "data", "items"])
        if not containers and isinstance(payload, dict) and payload.get("containerId"):
            containers = [payload]
        return containers

    async def async_get_container_details(self, container_id: str) -> dict[str, Any]:
        payload = await self._async_request("GET", f"/customers/containers/{container_id}")
        if not isinstance(payload, dict):
            raise BMWCarDataError("BMW container details response had an unexpected shape.")
        return payload

    async def async_create_container(
        self,
        *,
        name: str,
        purpose: str,
        technical_descriptors: list[str],
    ) -> dict[str, Any]:
        payload = await self._async_request(
            "POST",
            "/customers/containers",
            json_body={
                "name": name,
                "purpose": purpose,
                "technicalDescriptors": technical_descriptors,
            },
        )
        if not isinstance(payload, dict):
            raise BMWCarDataError("BMW container creation response had an unexpected shape.")
        return payload

    async def async_get_telematic_data(self, vin: str, container_id: str) -> dict[str, Any]:
        payload = await self._async_request(
            "GET",
            f"/customers/vehicles/{vin}/telematicData",
            params={"containerId": container_id},
        )
        if not isinstance(payload, dict):
            raise BMWCarDataError("BMW telematic data response had an unexpected shape.")
        return payload

    async def async_get_basic_data(self, vin: str) -> dict[str, Any]:
        payload = await self._async_request("GET", f"/customers/vehicles/{vin}/basicData")
        if not isinstance(payload, dict):
            raise BMWCarDataError("BMW basicData response had an unexpected shape.")
        return payload

    async def async_get_charging_history(
        self,
        vin: str,
        *,
        days: int = DEFAULT_CHARGING_HISTORY_DAYS,
    ) -> dict[str, Any]:
        now = utc_now()
        candidate_windows = []
        for day_window in (days, *CHARGING_HISTORY_DAY_WINDOWS):
            if day_window not in candidate_windows:
                candidate_windows.append(day_window)

        last_error: BMWCarDataError | None = None
        for day_window in candidate_windows:
            params = {
                "from": _format_api_datetime(now - timedelta(days=day_window)),
                "to": _format_api_datetime(now),
            }
            try:
                payload = await self._async_request(
                    "GET",
                    f"/customers/vehicles/{vin}/chargingHistory",
                    params=params,
                )
            except BMWCarDataError as err:
                last_error = err
                if "Parameter invalid" in str(err):
                    continue
                raise
            if not isinstance(payload, dict):
                raise BMWCarDataError(
                    "BMW chargingHistory response had an unexpected shape."
                )
            return payload

        if last_error is not None:
            raise last_error
        raise BMWCarDataError("BMW chargingHistory request failed unexpectedly.")

    async def async_get_location_based_charging_settings(
        self,
        vin: str,
        *,
        tolerate_not_found: bool = True,
    ) -> dict[str, Any]:
        try:
            payload = await self._async_request(
                "GET",
                f"/customers/vehicles/{vin}/locationBasedChargingSettings",
            )
        except BMWCarDataError as err:
            if tolerate_not_found and "No LBCS data found" in str(err):
                return {"data": []}
            raise
        if not isinstance(payload, dict):
            raise BMWCarDataError(
                "BMW locationBasedChargingSettings response had an unexpected shape."
            )
        return payload

    async def async_resolve_vin(self, selected_vin: str | None = None) -> str:
        if selected_vin:
            return selected_vin
        mappings = await self.async_get_vehicle_mappings()
        if len(mappings) == 1:
            return str(mappings[0]["vin"])
        if not mappings:
            raise BMWCarDataError("No mapped vehicles were returned for this account.")
        vins = ", ".join(str(item.get("vin", "<unknown>")) for item in mappings)
        raise BMWCarDataError(
            "Multiple mapped vehicles were returned. A VIN selection is required: "
            f"{vins}"
        )

    async def async_ensure_container(
        self,
        *,
        name: str = DEFAULT_CONTAINER_NAME,
        purpose: str = DEFAULT_CONTAINER_PURPOSE,
        descriptors: list[str] | None = None,
        enable_location: bool = False,
        existing_container_id: str | None = None,
    ) -> dict[str, Any]:
        requested_descriptors = list(descriptors or DEFAULT_TELEMATIC_DESCRIPTORS)
        if enable_location:
            for descriptor in LOCATION_DESCRIPTORS:
                if descriptor not in requested_descriptors:
                    requested_descriptors.append(descriptor)

        if existing_container_id:
            details = await self.async_get_container_details(existing_container_id)
            if details.get("state") == "ACTIVE":
                return details

        containers = await self.async_list_containers()
        matching_names = [
            container
            for container in containers
            if container.get("name") == name and container.get("state") == "ACTIVE"
        ]
        for container in matching_names:
            details = await self.async_get_container_details(container["containerId"])
            current = set(details.get("technicalDescriptors", []))
            if set(requested_descriptors).issubset(current):
                return details

        if matching_names:
            name = f"{name}_{utc_now().strftime('%Y%m%d%H%M%S')}"

        created = await self.async_create_container(
            name=name,
            purpose=purpose,
            technical_descriptors=requested_descriptors,
        )
        if created.get("technicalDescriptors"):
            return created
        return await self.async_get_container_details(created["containerId"])

    async def async_bootstrap_vehicle_context(
        self,
        *,
        selected_vin: str | None = None,
        enable_location: bool = False,
        existing_container_id: str | None = None,
        container_name: str = DEFAULT_CONTAINER_NAME,
        container_purpose: str = DEFAULT_CONTAINER_PURPOSE,
        descriptors: list[str] | None = None,
    ) -> BMWVehicleContext:
        vin = await self.async_resolve_vin(selected_vin)
        container = await self.async_ensure_container(
            name=container_name,
            purpose=container_purpose,
            descriptors=descriptors,
            enable_location=enable_location,
            existing_container_id=existing_container_id,
        )
        return BMWVehicleContext(
            client_id=self._authenticator.client_id,
            vin=vin,
            container_id=str(container["containerId"]),
            container_name=str(container.get("name", container_name)),
            enable_location=enable_location,
        )
