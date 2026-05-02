from __future__ import annotations

from datetime import time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

homeassistant = pytest.importorskip("homeassistant")

from custom_components.bmw_cardata.const import (  # noqa: E402
    CHARGING_STATUS_CHARGING,
    CHARGING_STATUS_FAST_CHARGING,
    CONF_ADAPTIVE_POLLING,
    CONF_CHARGING_INTERVAL,
    CONF_NIGHT_END,
    CONF_NIGHT_MODE_ENABLED,
    CONF_NIGHT_START,
    COORDINATOR_TYPE_HISTORY,
    COORDINATOR_TYPE_METADATA,
    COORDINATOR_TYPE_SETTINGS,
    COORDINATOR_TYPE_TELEMATICS,
)
from custom_components.bmw_cardata.scheduler import (  # noqa: E402
    BMWAccountScheduler,
    _parse_time,
)

pytestmark = pytest.mark.asyncio


def _budget_manager(remaining: int = 45, can_spend: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        async_remaining=AsyncMock(return_value=remaining),
        async_can_spend=AsyncMock(return_value=can_spend),
    )


def _telematics_data(charging_status: str | None = "NOCHARGING") -> dict:
    return {
        "telematicData": {
            "vehicle.drivetrain.electricEngine.charging.status": {
                "value": charging_status
            }
        }
    }


class TestParseTime:
    def test_valid_time(self):
        assert _parse_time("22:00") == time(22, 0)
        assert _parse_time("05:30") == time(5, 30)

    def test_invalid_time_fallback(self):
        assert _parse_time("not-a-time") == time(0, 0)
        assert _parse_time("") == time(0, 0)


class TestRegisterVehicle:
    def test_register_creates_empty_last_poll(self):
        scheduler = BMWAccountScheduler(_budget_manager())
        scheduler.register_vehicle("VIN1")
        assert "VIN1" in scheduler._last_poll


class TestShouldPoll:
    async def test_first_poll_always_allowed(self):
        scheduler = BMWAccountScheduler(_budget_manager())
        scheduler.register_vehicle("VIN1")
        result = await scheduler.should_poll("VIN1", COORDINATOR_TYPE_TELEMATICS, None)
        assert result is True

    async def test_adaptive_disabled_always_polls(self):
        scheduler = BMWAccountScheduler(
            _budget_manager(),
            options={CONF_ADAPTIVE_POLLING: False},
        )
        scheduler.register_vehicle("VIN1")
        scheduler.record_poll("VIN1", COORDINATOR_TYPE_TELEMATICS)
        result = await scheduler.should_poll("VIN1", COORDINATOR_TYPE_TELEMATICS, None)
        assert result is True

    async def test_budget_exhausted_skips(self):
        scheduler = BMWAccountScheduler(
            _budget_manager(can_spend=False),
        )
        scheduler.register_vehicle("VIN1")
        scheduler.record_poll("VIN1", COORDINATOR_TYPE_TELEMATICS)
        result = await scheduler.should_poll("VIN1", COORDINATOR_TYPE_TELEMATICS, None)
        assert result is False

    async def test_telematics_idle_day_interval(self):
        budget = _budget_manager()
        scheduler = BMWAccountScheduler(budget)
        scheduler.register_vehicle("VIN1")
        scheduler.record_poll("VIN1", COORDINATOR_TYPE_TELEMATICS)

        # Immediately after poll, should skip
        result = await scheduler.should_poll(
            "VIN1", COORDINATOR_TYPE_TELEMATICS, _telematics_data("NOCHARGING")
        )
        assert result is False

    async def test_telematics_charging_interval(self):
        budget = _budget_manager()
        scheduler = BMWAccountScheduler(
            budget, options={CONF_CHARGING_INTERVAL: 30}
        )
        scheduler.register_vehicle("VIN1")
        scheduler.record_poll("VIN1", COORDINATOR_TYPE_TELEMATICS)

        result = await scheduler.should_poll(
            "VIN1", COORDINATOR_TYPE_TELEMATICS, _telematics_data(CHARGING_STATUS_CHARGING)
        )
        assert result is False

    async def test_charging_interval_15_min_option(self):
        budget = _budget_manager()
        scheduler = BMWAccountScheduler(
            budget, options={CONF_CHARGING_INTERVAL: 15}
        )
        scheduler.register_vehicle("VIN1")
        scheduler.record_poll("VIN1", COORDINATOR_TYPE_TELEMATICS)

        result = await scheduler.should_poll(
            "VIN1", COORDINATOR_TYPE_TELEMATICS, _telematics_data(CHARGING_STATUS_CHARGING)
        )
        assert result is False

    async def test_fast_charging_detected_as_charging(self):
        budget = _budget_manager()
        scheduler = BMWAccountScheduler(budget)
        scheduler.register_vehicle("VIN1")
        scheduler.record_poll("VIN1", COORDINATOR_TYPE_TELEMATICS)

        result = await scheduler.should_poll(
            "VIN1",
            COORDINATOR_TYPE_TELEMATICS,
            _telematics_data(CHARGING_STATUS_FAST_CHARGING),
        )
        assert result is False

    async def test_critical_budget_blocks_non_telematics(self):
        budget = _budget_manager(remaining=6)
        scheduler = BMWAccountScheduler(budget)
        scheduler.register_vehicle("VIN1")
        scheduler.record_poll("VIN1", COORDINATOR_TYPE_HISTORY)

        result = await scheduler.should_poll(
            "VIN1", COORDINATOR_TYPE_HISTORY, None
        )
        assert result is False

    async def test_critical_budget_allows_charging_telematics(self):
        budget = _budget_manager(remaining=6)
        scheduler = BMWAccountScheduler(budget)
        scheduler.register_vehicle("VIN1")
        scheduler.record_poll("VIN1", COORDINATOR_TYPE_TELEMATICS)

        result = await scheduler.should_poll(
            "VIN1",
            COORDINATOR_TYPE_TELEMATICS,
            _telematics_data(CHARGING_STATUS_CHARGING),
        )
        assert result is True

    async def test_critical_budget_blocks_idle_telematics(self):
        budget = _budget_manager(remaining=6)
        scheduler = BMWAccountScheduler(budget)
        scheduler.register_vehicle("VIN1")
        scheduler.record_poll("VIN1", COORDINATOR_TYPE_TELEMATICS)

        result = await scheduler.should_poll(
            "VIN1",
            COORDINATOR_TYPE_TELEMATICS,
            _telematics_data("NOCHARGING"),
        )
        assert result is False


class TestGetNextInterval:
    def test_adaptive_disabled_returns_defaults(self):
        scheduler = BMWAccountScheduler(
            _budget_manager(),
            options={CONF_ADAPTIVE_POLLING: False},
        )
        from custom_components.bmw_cardata.const import DEFAULT_TELEMATICS_INTERVAL

        interval = scheduler.get_next_interval(COORDINATOR_TYPE_TELEMATICS, None)
        assert interval == DEFAULT_TELEMATICS_INTERVAL

    def test_telematics_idle_day(self):
        scheduler = BMWAccountScheduler(_budget_manager())
        interval = scheduler.get_next_interval(
            COORDINATOR_TYPE_TELEMATICS, _telematics_data("NOCHARGING")
        )
        assert interval == timedelta(minutes=60)

    def test_telematics_charging(self):
        scheduler = BMWAccountScheduler(
            _budget_manager(), options={CONF_CHARGING_INTERVAL: 30}
        )
        interval = scheduler.get_next_interval(
            COORDINATOR_TYPE_TELEMATICS, _telematics_data(CHARGING_STATUS_CHARGING)
        )
        assert interval == timedelta(minutes=30)

    def test_background_coordinator_returns_24h(self):
        scheduler = BMWAccountScheduler(_budget_manager())
        for coord_type in (
            COORDINATOR_TYPE_METADATA,
            COORDINATOR_TYPE_HISTORY,
            COORDINATOR_TYPE_SETTINGS,
        ):
            interval = scheduler.get_next_interval(coord_type, None)
            assert interval == timedelta(hours=24)

    def test_night_mode_extends_telematics_interval(self):
        scheduler = BMWAccountScheduler(
            _budget_manager(),
            options={
                CONF_NIGHT_MODE_ENABLED: True,
                CONF_NIGHT_START: "00:00",
                CONF_NIGHT_END: "23:59",
            },
        )
        interval = scheduler.get_next_interval(
            COORDINATOR_TYPE_TELEMATICS, _telematics_data("NOCHARGING")
        )
        assert interval == timedelta(hours=6)

    def test_night_mode_skips_background_until_morning(self):
        scheduler = BMWAccountScheduler(
            _budget_manager(),
            options={
                CONF_NIGHT_MODE_ENABLED: True,
                CONF_NIGHT_START: "00:00",
                CONF_NIGHT_END: "23:59",
            },
        )
        for coord_type in (
            COORDINATOR_TYPE_METADATA,
            COORDINATOR_TYPE_HISTORY,
            COORDINATOR_TYPE_SETTINGS,
        ):
            interval = scheduler.get_next_interval(coord_type, None)
            # Should be roughly 24 hours minus a tiny bit because night_end is 23:59
            assert interval >= timedelta(hours=23)

    def test_night_mode_disabled_uses_normal_intervals(self):
        scheduler = BMWAccountScheduler(
            _budget_manager(),
            options={CONF_NIGHT_MODE_ENABLED: False},
        )
        interval = scheduler.get_next_interval(
            COORDINATOR_TYPE_TELEMATICS, _telematics_data("NOCHARGING")
        )
        assert interval == timedelta(minutes=60)


class TestIsCharging:
    def test_none_data(self):
        scheduler = BMWAccountScheduler(_budget_manager())
        assert scheduler._is_charging(None) is False

    def test_no_charging_status(self):
        scheduler = BMWAccountScheduler(_budget_manager())
        assert scheduler._is_charging({"telematicData": {}}) is False

    def test_nocharging(self):
        scheduler = BMWAccountScheduler(_budget_manager())
        assert scheduler._is_charging(_telematics_data("NOCHARGING")) is False

    def test_charging(self):
        scheduler = BMWAccountScheduler(_budget_manager())
        assert scheduler._is_charging(_telematics_data(CHARGING_STATUS_CHARGING)) is True

    def test_fast_charging(self):
        scheduler = BMWAccountScheduler(_budget_manager())
        assert scheduler._is_charging(_telematics_data(CHARGING_STATUS_FAST_CHARGING)) is True

    def test_plugged_in(self):
        scheduler = BMWAccountScheduler(_budget_manager())
        assert scheduler._is_charging(_telematics_data("PLUGGED_IN")) is True


class TestIsNight:
    def test_night_mode_disabled(self):
        scheduler = BMWAccountScheduler(
            _budget_manager(), options={CONF_NIGHT_MODE_ENABLED: False}
        )
        assert scheduler._is_night() is False

    def test_wraparound_night_window(self):
        # 22:00 - 05:00 should be night at 23:00 and 03:00 but not at 12:00
        from homeassistant.util import dt as dt_util

        scheduler = BMWAccountScheduler(
            _budget_manager(),
            options={
                CONF_NIGHT_MODE_ENABLED: True,
                CONF_NIGHT_START: "22:00",
                CONF_NIGHT_END: "05:00",
            },
        )

        # Patch now to 23:00
        import datetime

        with patch.object(
            dt_util, "now", return_value=datetime.datetime(2026, 1, 1, 23, 0, tzinfo=datetime.timezone.utc)
        ):
            assert scheduler._is_night() is True

        with patch.object(
            dt_util, "now", return_value=datetime.datetime(2026, 1, 1, 3, 0, tzinfo=datetime.timezone.utc)
        ):
            assert scheduler._is_night() is True

        with patch.object(
            dt_util, "now", return_value=datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
        ):
            assert scheduler._is_night() is False

    def test_daytime_night_window(self):
        # 10:00 - 14:00 should be night at 12:00 but not at 09:00 or 15:00
        from homeassistant.util import dt as dt_util
        import datetime

        scheduler = BMWAccountScheduler(
            _budget_manager(),
            options={
                CONF_NIGHT_MODE_ENABLED: True,
                CONF_NIGHT_START: "10:00",
                CONF_NIGHT_END: "14:00",
            },
        )

        with patch.object(
            dt_util, "now", return_value=datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
        ):
            assert scheduler._is_night() is True

        with patch.object(
            dt_util, "now", return_value=datetime.datetime(2026, 1, 1, 9, 0, tzinfo=datetime.timezone.utc)
        ):
            assert scheduler._is_night() is False

        with patch.object(
            dt_util, "now", return_value=datetime.datetime(2026, 1, 1, 15, 0, tzinfo=datetime.timezone.utc)
        ):
            assert scheduler._is_night() is False
