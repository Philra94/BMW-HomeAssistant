from __future__ import annotations

from datetime import timedelta

from custom_components.bmw_cardata.models import BMWTokenSet, utc_now


def test_access_token_is_fresh_for_recent_token() -> None:
    token_set = BMWTokenSet(
        access_token="token",
        refresh_token="refresh",
        token_type="Bearer",
        scope="cardata:api:read",
        expires_in=3600,
        issued_at=utc_now().isoformat(),
    )

    assert token_set.access_token_is_fresh()


def test_access_token_is_not_fresh_when_old() -> None:
    token_set = BMWTokenSet(
        access_token="token",
        refresh_token="refresh",
        token_type="Bearer",
        scope="cardata:api:read",
        expires_in=300,
        issued_at=(utc_now() - timedelta(minutes=10)).isoformat(),
    )

    assert not token_set.access_token_is_fresh()
