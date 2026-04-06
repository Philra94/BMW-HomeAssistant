from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any, Iterable

from aiohttp import ClientError, ClientSession

from .const import AUTH_BASE_URL, DEFAULT_SCOPES, DEFAULT_REQUEST_TIMEOUT
from .exceptions import BMWAuthError, BMWAuthPendingError, BMWReauthRequiredError
from .models import BMWDeviceCodePayload, BMWTokenSet


class BMWAuthenticator:
    def __init__(
        self,
        session: ClientSession,
        client_id: str,
        *,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
        scopes: Iterable[str] | None = None,
    ) -> None:
        if not client_id:
            raise BMWAuthError("BMW client ID is required.")
        self._session = session
        self._client_id = client_id
        self._timeout = timeout
        self._scopes = list(scopes or DEFAULT_SCOPES)

    @property
    def client_id(self) -> str:
        return self._client_id

    @staticmethod
    def generate_code_verifier() -> str:
        verifier = secrets.token_urlsafe(72).rstrip("=")
        return verifier[:128]

    @staticmethod
    def build_code_challenge(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    async def _async_post_form(
        self,
        endpoint_path: str,
        data: dict[str, Any],
        *,
        accepted_statuses: tuple[int, ...] = (200,),
    ) -> tuple[int, dict[str, Any]]:
        try:
            response = await self._session.post(
                f"{AUTH_BASE_URL}{endpoint_path}",
                data=data,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=self._timeout,
            )
        except ClientError as err:
            raise BMWAuthError(f"BMW authentication request failed: {err}") from err

        async with response:
            try:
                payload = await response.json()
            except Exception:
                payload = {"raw_response": await response.text()}

            if response.status not in accepted_statuses:
                detail = (
                    payload.get("error_description")
                    or payload.get("raw_response")
                    or payload
                )
                raise BMWAuthError(
                    f"BMW auth endpoint {endpoint_path} failed with {response.status}: {detail}"
                )
            return response.status, payload

    async def async_request_device_code(
        self,
    ) -> tuple[BMWDeviceCodePayload, str]:
        code_verifier = self.generate_code_verifier()
        code_challenge = self.build_code_challenge(code_verifier)
        _, payload = await self._async_post_form(
            "/device/code",
            data={
                "client_id": self._client_id,
                "response_type": "device_code",
                "scope": " ".join(self._scopes),
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            },
        )
        required = ["user_code", "device_code", "verification_uri", "interval", "expires_in"]
        missing = [field for field in required if field not in payload]
        if missing:
            raise BMWAuthError(
                f"Device code response is missing fields: {', '.join(missing)}"
            )
        return (
            BMWDeviceCodePayload(
                user_code=str(payload["user_code"]),
                device_code=str(payload["device_code"]),
                verification_uri=str(payload["verification_uri"]),
                interval=int(payload["interval"]),
                expires_in=int(payload["expires_in"]),
            ),
            code_verifier,
        )

    async def async_exchange_device_code(
        self,
        *,
        device_code: str,
        code_verifier: str,
    ) -> BMWTokenSet:
        status, payload = await self._async_post_form(
            "/token",
            data={
                "client_id": self._client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "code_verifier": code_verifier,
            },
            accepted_statuses=(200, 400, 403),
        )

        if status == 200:
            return BMWTokenSet.from_bmw_payload(payload)

        error = str(payload.get("error", ""))
        error_description = str(payload.get("error_description", "")).lower()
        if error == "authorization_pending" or (
            status == 403 and "not yet completed authorization" in error_description
        ):
            raise BMWAuthPendingError("Device approval is still pending.")
        if error in {"access_denied", "expired_token"}:
            raise BMWReauthRequiredError(
                payload.get("error_description", "BMW device approval expired.")
            )
        raise BMWAuthError(
            payload.get("error_description", f"Unexpected BMW auth error: {error}")
        )

    async def async_refresh_tokens(self, refresh_token: str) -> BMWTokenSet:
        _, payload = await self._async_post_form(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id,
            },
            accepted_statuses=(200, 400, 401, 403),
        )
        if "access_token" not in payload:
            raise BMWReauthRequiredError("Stored BMW refresh token is no longer valid.")
        return BMWTokenSet.from_bmw_payload(payload)
