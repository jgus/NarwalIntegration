"""Constants for the Narwal vacuum integration."""

from homeassistant.const import Platform

from .narwal_client import FanLevel

DOMAIN = "narwal"
DEFAULT_PORT = 9002

MANUFACTURER = "Narwal"
MODEL = "Flow (AX12)"

# Model selector for config flow.
# Keys are user-facing labels; values are product key prefixes.
# "auto" cycles all known keys during discovery (slower, fallback).
NARWAL_MODELS: dict[str, str] = {
    "Narwal Flow": "QoEsI5qYXO",
    "Narwal Flow 2": "QxMSPG6VSO",
    "Narwal Freo Z10 Ultra": "DrzDKQ0MU8",
    "Narwal Freo X10 Pro": "CNbforyZWI",
    "Other / Auto-detect": "auto",
}

CONF_MODEL = "model"
CONF_PRODUCT_KEY = "product_key"

PLATFORMS: list[Platform] = [
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CAMERA,
]

FAN_SPEED_MAP: dict[str, FanLevel] = {
    "quiet": FanLevel.QUIET,
    "normal": FanLevel.NORMAL,
    "strong": FanLevel.STRONG,
    "max": FanLevel.MAX,
}

FAN_SPEED_LIST: list[str] = list(FAN_SPEED_MAP.keys())

# base_status field 15 (terminateReason) value → HA option key. From the decoded
# TaskResult enum (re/ENUMS.md). Live-confirmed: 1 = NORMAL_END.
TASK_RESULT_OPTIONS: dict[int, str] = {
    1: "normal_end",
    2: "user_force_end",
    3: "shutdown_force_end",
    4: "low_battery_force_end",
    5: "overflow_force_end",
    6: "pause_too_long_force_end",
    7: "system_error_force_end",
    8: "user_force_end_on_station",
    9: "user_force_end_on_app",
    10: "recall_end",
    11: "normal_end_replenish_map_fail",
    12: "map_unmatched_force_end",
    13: "relocation_fail_with_station_force_end",
    14: "relocation_fail_without_station_force_end",
    15: "pretask_error_force_end",
    16: "schedule_task_force_end",
    17: "unexecuted",
    18: "not_find_pet",
}

# Best-effort help-center deep link for a robot error code. The app's goHelpCenterByCode
# builds <localized help base>?code=<n>&deviceId=…&lang=…; the exact base is a runtime
# i18n value we can't read, so this is inferred from the Flow's help-center family and
# should be corrected if a real error opens a different path. The raw code is the fallback.
ERROR_HELP_URL_TEMPLATE = (
    "https://help.narwal.com/helpcenter/vall/#/p2/question/all?eType=1&code={code}&lang=en-US"
)
