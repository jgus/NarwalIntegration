"""Constants for the Narwal vacuum integration."""

from homeassistant.const import Platform

from .narwal_client import FanLevel, MopHumidity, MopStrengthLevel, WorkMode

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
    Platform.SELECT,
    Platform.NUMBER,
]

# HA fan_speed labels → FanLevel, verbatim from the app's user-visible suction names (sentence case, as HA shows fan_speed values directly). The enum members keep the app's internal identifiers, so DEEP surfaces as "Super powerful" and SUPER as "Ultra powerful".
_FAN_SPEED_CANONICAL: dict[str, FanLevel] = {
    "Quiet": FanLevel.MUTE,
    "Standard": FanLevel.NORMAL,
    "Strong": FanLevel.STRONG,
    "Super powerful": FanLevel.DEEP,
    "Ultra powerful": FanLevel.SUPER,
}

FAN_SPEED_LIST: list[str] = list(_FAN_SPEED_CANONICAL)

# FAN_SPEED_MAP also accepts the original lowercase fan_speed values (quiet/normal/strong/max) so existing automations keep working; these aliases are not offered in FAN_SPEED_LIST.
FAN_SPEED_MAP: dict[str, FanLevel] = _FAN_SPEED_CANONICAL | {
    "quiet": FanLevel.MUTE,
    "normal": FanLevel.NORMAL,
    "strong": FanLevel.STRONG,
    "max": FanLevel.SUPER,
}

# Select option id → robot enum. Option ids are rendered to the app's user-visible labels via translations.
WORK_MODE_MAP: dict[str, WorkMode] = {
    "vacuum": WorkMode.VACUUM,
    "mop": WorkMode.MOP,
    "vacuum_then_mop": WorkMode.VACUUM_THEN_MOP,
    "vacuum_and_mop": WorkMode.VACUUM_AND_MOP,
}
WATER_MAP: dict[str, MopHumidity] = {
    "dry": MopHumidity.DRY,
    "normal": MopHumidity.NORMAL,
    "wet": MopHumidity.WET,
}
MOP_STRENGTH_MAP: dict[str, MopStrengthLevel] = {
    "normal": MopStrengthLevel.NORMAL,
    "high": MopStrengthLevel.HIGH,
}

PASSES_MIN = 1
PASSES_MAX = 3
