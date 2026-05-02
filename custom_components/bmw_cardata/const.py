from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "bmw_cardata"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
]

CONF_CLIENT_ID = "client_id"
CONF_VIN = "vin"
CONF_ENABLE_LOCATION = "enable_location"
CONF_SELECTED_VIN = "selected_vin"
CONF_SELECTED_VINS = "selected_vins"
CONF_CONTAINER_ID = "container_id"
CONF_CONTAINER_NAME = "container_name"
CONF_CONTAINER_PURPOSE = "container_purpose"
CONF_GCID = "gcid"
CONF_REQUEST_TIMEOUT = "request_timeout"
CONF_TOKEN_SET = "token_set"

ATTR_USER_CODE = "user_code"
ATTR_VERIFICATION_URL = "verification_url"
ATTR_DIRECT_VERIFICATION_URL = "direct_verification_url"
ATTR_REMAINING_BUDGET = "remaining_budget"

AUTH_BASE_URL = "https://customer.bmwgroup.com/gcdm/oauth"
API_BASE_URL = "https://api-cardata.bmwgroup.com"
API_VERSION = "v1"

DEFAULT_CONTAINER_NAME = "ha_ev_current"
DEFAULT_CONTAINER_PURPOSE = "Home Assistant BMW CarData integration"
DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_ENABLE_LOCATION = False

DEFAULT_SCOPES = [
    "authenticate_user",
    "openid",
    "cardata:api:read",
]

DEFAULT_TELEMATIC_DESCRIPTORS = [
    "vehicle.drivetrain.batteryManagement.header",
    "vehicle.drivetrain.batteryManagement.batterySizeMax",
    "vehicle.drivetrain.batteryManagement.maxEnergy",
    "vehicle.drivetrain.electricEngine.kombiRemainingElectricRange",
    "vehicle.drivetrain.electricEngine.remainingElectricRange",
    "vehicle.drivetrain.electricEngine.charging.status",
    "vehicle.drivetrain.electricEngine.charging.hvStatus",
    "vehicle.drivetrain.electricEngine.charging.timeRemaining",
    "vehicle.drivetrain.electricEngine.charging.connectorStatus",
    "vehicle.drivetrain.electricEngine.charging.lastChargingReason",
    "vehicle.drivetrain.electricEngine.charging.lastChargingResult",
    "vehicle.powertrain.electric.battery.stateOfCharge.target",
    "vehicle.vehicle.travelledDistance",
    "vehicle.vehicle.averageWeeklyDistanceLongTerm",
    "vehicle.vehicle.averageWeeklyDistanceShortTerm",
    "vehicle.vehicle.avgAuxPower",
    "vehicle.status.conditionBasedServicesCount",
    "vehicle.status.serviceDistance.yellow",
    "vehicle.status.serviceTime.yellow",
    "vehicle.status.serviceTime.hUandAuServiceYellow",
    "vehicle.body.chargingPort.status",
    "vehicle.body.hood.isOpen",
    "vehicle.body.trunk.isOpen",
    "vehicle.cabin.door.row1.driver.isOpen",
    "vehicle.cabin.door.row1.passenger.isOpen",
    "vehicle.cabin.door.row2.driver.isOpen",
    "vehicle.cabin.door.row2.passenger.isOpen",
]

LOCATION_DESCRIPTORS = [
    "vehicle.cabin.infotainment.navigation.currentLocation.latitude",
    "vehicle.cabin.infotainment.navigation.currentLocation.longitude",
]

DEFAULT_TELEMATIC_DESCRIPTOR_SET = DEFAULT_TELEMATIC_DESCRIPTORS + LOCATION_DESCRIPTORS

DEFAULT_TELEMATICS_INTERVAL = timedelta(hours=1)
DEFAULT_METADATA_INTERVAL = timedelta(hours=24)
DEFAULT_HISTORY_INTERVAL = timedelta(hours=6)
DEFAULT_SETTINGS_INTERVAL = timedelta(hours=24)

DEFAULT_CHARGING_HISTORY_DAYS = 30
CHARGING_HISTORY_DAY_WINDOWS = (30, 14, 7)

DAILY_REQUEST_LIMIT = 50
DEFAULT_REQUEST_RESERVE = 5

SERVICE_REFRESH = "refresh_vehicle_data"

CONFIG_ENTRY_VERSION = 2
STORAGE_VERSION = 1
REQUEST_BUDGET_STORAGE_KEY = f"{DOMAIN}_request_budget"

# Coordinator types
COORDINATOR_TYPE_TELEMATICS = "telematics"
COORDINATOR_TYPE_METADATA = "metadata"
COORDINATOR_TYPE_HISTORY = "history"
COORDINATOR_TYPE_SETTINGS = "settings"

# Scheduler options
CONF_ADAPTIVE_POLLING = "adaptive_polling"
CONF_CHARGING_INTERVAL = "charging_interval"
CONF_NIGHT_MODE_ENABLED = "night_mode_enabled"
CONF_NIGHT_START = "night_start"
CONF_NIGHT_END = "night_end"

# Default scheduler settings
DEFAULT_ADAPTIVE_POLLING = True
DEFAULT_CHARGING_INTERVAL = 30  # minutes
DEFAULT_NIGHT_MODE_ENABLED = True
DEFAULT_NIGHT_START = "21:00"
DEFAULT_NIGHT_END = "06:00"

# Charging status values
CHARGING_STATUS_CHARGING = "CHARGING"
CHARGING_STATUS_FAST_CHARGING = "FASTCHARGING"
CHARGING_STATUS_PLUGGED_IN = "PLUGGED_IN"

LOCATION_LATITUDE_DESCRIPTOR = (
    "vehicle.cabin.infotainment.navigation.currentLocation.latitude"
)
LOCATION_LONGITUDE_DESCRIPTOR = (
    "vehicle.cabin.infotainment.navigation.currentLocation.longitude"
)
