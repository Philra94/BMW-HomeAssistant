from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class BMWDeviceCodePayload:
    user_code: str
    device_code: str
    verification_uri: str
    interval: int
    expires_in: int

    @property
    def direct_verification_uri(self) -> str:
        return f"{self.verification_uri}?user_code={self.user_code}"


@dataclass(slots=True)
class BMWTokenSet:
    access_token: str
    refresh_token: str
    token_type: str
    scope: str
    expires_in: int
    issued_at: str
    id_token: str | None = None
    gcid: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BMWTokenSet":
        return cls(
            access_token=str(data["access_token"]),
            refresh_token=str(data["refresh_token"]),
            token_type=str(data.get("token_type", "Bearer")),
            scope=str(data.get("scope", "")),
            expires_in=int(data["expires_in"]),
            issued_at=str(data["issued_at"]),
            id_token=str(data["id_token"]) if data.get("id_token") else None,
            gcid=str(data["gcid"]) if data.get("gcid") else None,
        )

    @classmethod
    def from_bmw_payload(cls, data: dict[str, Any]) -> "BMWTokenSet":
        return cls(
            access_token=str(data["access_token"]),
            refresh_token=str(data["refresh_token"]),
            token_type=str(data["token_type"]),
            scope=str(data["scope"]),
            expires_in=int(data["expires_in"]),
            issued_at=utc_now().isoformat(),
            id_token=str(data["id_token"]) if data.get("id_token") else None,
            gcid=str(data["gcid"]) if data.get("gcid") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "scope": self.scope,
            "expires_in": self.expires_in,
            "issued_at": self.issued_at,
            "id_token": self.id_token,
            "gcid": self.gcid,
        }

    def access_token_is_fresh(self, *, safety_margin_seconds: int = 120) -> bool:
        issued_at = datetime.fromisoformat(self.issued_at)
        age = (utc_now() - issued_at).total_seconds()
        return age < max(self.expires_in - safety_margin_seconds, 0)


@dataclass(slots=True)
class BMWVehicleContext:
    client_id: str
    vin: str
    container_id: str
    container_name: str
    enable_location: bool


@dataclass(slots=True)
class BMWDeviceApprovalState:
    client_id: str
    code_verifier: str
    device_code: str
    user_code: str
    verification_uri: str
    interval: int
    expires_in: int

    @property
    def direct_verification_uri(self) -> str:
        return f"{self.verification_uri}?user_code={self.user_code}"
