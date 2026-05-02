from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from homeassistant.util import dt as dt_util

from .budget import RequestBudgetManager
from .const import (
    CHARGING_STATUS_CHARGING,
    CHARGING_STATUS_FAST_CHARGING,
    CHARGING_STATUS_PLUGGED_IN,
    CONF_ADAPTIVE_POLLING,
    CONF_CHARGING_INTERVAL,
    CONF_NIGHT_END,
    CONF_NIGHT_MODE_ENABLED,
    CONF_NIGHT_START,
    COORDINATOR_TYPE_TELEMATICS,
    DEFAULT_ADAPTIVE_POLLING,
    DEFAULT_CHARGING_INTERVAL,
    DEFAULT_HISTORY_INTERVAL,
    DEFAULT_METADATA_INTERVAL,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_MODE_ENABLED,
    DEFAULT_NIGHT_START,
    DEFAULT_SETTINGS_INTERVAL,
    DEFAULT_TELEMATICS_INTERVAL,
    DEFAULT_REQUEST_RESERVE,
)
from .helpers import get_telematic_value
from .models import utc_now

_LOGGER = logging.getLogger(__name__)

_DEFAULT_INTERVALS: dict[str, timedelta] = {
    COORDINATOR_TYPE_TELEMATICS: DEFAULT_TELEMATICS_INTERVAL,
    COORDINATOR_TYPE_METADATA: DEFAULT_METADATA_INTERVAL,
    COORDINATOR_TYPE_HISTORY: DEFAULT_HISTORY_INTERVAL,
    COORDINATOR_TYPE_SETTINGS: DEFAULT_SETTINGS_INTERVAL,
}


def _parse_time(time_str: str) -> time:
    try:
        return datetime.strptime(time_str.strip(), "%H:%M").time()
    except (ValueError, AttributeError):
        return time(0, 0)


class BMWAccountScheduler:
    """Account-level scheduler that coordinates API polling across all vehicles.

    Because BMW containers (and therefore API budgets) are shared per account,
    polling decisions must be made globally rather than per-vehicle.
    """

    def __init__(
        self,
        budget_manager: RequestBudgetManager,
        options: dict[str, any] | None = None,
    ) -> None:
        self._budget_manager = budget_manager
        self._options = options or {}
        self._last_poll: dict[str, dict[str, datetime]] = {}

    def register_vehicle(self, vin: str) -> None:
        """Register a vehicle so the scheduler can track its polls."""
        self._last_poll[vin] = {}

    def record_poll(self, vin: str, coordinator_type: str) -> None:
        """Record that a poll attempt was made for a vehicle/coordinator."""
        self._last_poll.setdefault(vin, {})[coordinator_type] = utc_now()

    async def should_poll(
        self,
        vin: str,
        coordinator_type: str,
        current_data: dict[str, any] | None,
    ) -> bool:
        """Return True if an API call should be made now.

        When adaptive polling is disabled this always returns True and the
        coordinator relies on its static update_interval.
        """
        if not self._options.get(CONF_ADAPTIVE_POLLING, DEFAULT_ADAPTIVE_POLLING):
            return True

        last_poll = self._last_poll.get(vin, {}).get(coordinator_type)
        if last_poll is None:
            return True

        if not await self._budget_manager.async_can_spend():
            _LOGGER.debug(
                "Skipping poll for %s/%s: local request budget exhausted", vin, coordinator_type
            )
            return False

        interval = self._get_interval(coordinator_type, current_data)
        elapsed = (utc_now() - last_poll).total_seconds()
        if elapsed < interval.total_seconds():
            _LOGGER.debug(
                "Skipping poll for %s/%s: elapsed %ds < interval %ds",
                vin,
                coordinator_type,
                elapsed,
                interval.total_seconds(),
            )
            return False

        # Critical budget mode: only allow telematics for actively charging vehicles
        remaining = await self._budget_manager.async_remaining()
        if remaining <= DEFAULT_REQUEST_RESERVE + 5:
            if coordinator_type != COORDINATOR_TYPE_TELEMATICS:
                _LOGGER.debug(
                    "Skipping poll for %s/%s: critical budget mode (non-telematics)",
                    vin,
                    coordinator_type,
                )
                return False
            if not self._is_charging(current_data):
                _LOGGER.debug(
                    "Skipping poll for %s/%s: critical budget mode (not charging)",
                    vin,
                    coordinator_type,
                )
                return False

        return True

    def get_next_interval(
        self,
        coordinator_type: str,
        current_data: dict[str, any] | None,
    ) -> timedelta:
        """Return the timedelta to use for the coordinator's next refresh."""
        if not self._options.get(CONF_ADAPTIVE_POLLING, DEFAULT_ADAPTIVE_POLLING):
            return _DEFAULT_INTERVALS.get(coordinator_type, DEFAULT_TELEMATICS_INTERVAL)

        # Background coordinators sleep through the night and resume in the morning
        if coordinator_type != COORDINATOR_TYPE_TELEMATICS and self._is_night():
            return self._time_until_morning()

        return self._get_interval(coordinator_type, current_data)

    def _get_interval(
        self,
        coordinator_type: str,
        current_data: dict[str, any] | None,
    ) -> timedelta:
        if coordinator_type == COORDINATOR_TYPE_TELEMATICS:
            return self._telematics_interval(current_data)
        return timedelta(hours=24)

    def _telematics_interval(
        self,
        current_data: dict[str, any] | None,
    ) -> timedelta:
        if self._is_charging(current_data):
            minutes = self._options.get(CONF_CHARGING_INTERVAL, DEFAULT_CHARGING_INTERVAL)
            return timedelta(minutes=minutes)
        if self._is_night():
            return timedelta(hours=3)
        return timedelta(minutes=60)

    def _time_until_morning(self) -> timedelta:
        now = dt_util.now()
        end_str = self._options.get(CONF_NIGHT_END, DEFAULT_NIGHT_END)
        end_time = _parse_time(end_str) or time(5, 0)
        end_dt = datetime.combine(now.date(), end_time, tzinfo=now.tzinfo)
        if end_dt <= now:
            end_dt += timedelta(days=1)
        delta = end_dt - now
        # Ensure we always schedule at least a short delay so we don't loop
        if delta.total_seconds() < 60:
            delta = timedelta(minutes=1)
        return delta

    @staticmethod
    def _is_charging(current_data: dict[str, any] | None) -> bool:
        if not current_data:
            return False
        status = get_telematic_value(
            current_data,
            "vehicle.drivetrain.electricEngine.charging.status",
        )
        if status is None:
            return False
        return str(status).upper() in (
            CHARGING_STATUS_CHARGING,
            CHARGING_STATUS_FAST_CHARGING,
            CHARGING_STATUS_PLUGGED_IN,
        )

    def _is_night(self) -> bool:
        if not self._options.get(CONF_NIGHT_MODE_ENABLED, DEFAULT_NIGHT_MODE_ENABLED):
            return False
        now_time = dt_util.now().time()
        start_str = self._options.get(CONF_NIGHT_START, DEFAULT_NIGHT_START)
        end_str = self._options.get(CONF_NIGHT_END, DEFAULT_NIGHT_END)
        start = _parse_time(start_str) or time(22, 0)
        end = _parse_time(end_str) or time(5, 0)
        if start <= end:
            return start <= now_time <= end
        return now_time >= start or now_time <= end
