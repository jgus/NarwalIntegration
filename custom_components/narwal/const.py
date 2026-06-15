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

# Consumable alert enum value → name (ConsumableMaintainItem / ConsumableReplaceItem).
CONSUMABLE_MAINTAIN_ITEMS: dict[int, str] = {
    1: "dust box", 2: "dust filter", 4: "wash ribs", 6: "universal wheel",
    7: "cliff sensor", 8: "side distance sensor", 9: "water tank sponge",
    10: "anti-winding brush", 11: "smart module sponge", 20: "dust container",
}
CONSUMABLE_REPLACE_ITEMS: dict[int, str] = {
    1: "dust filter", 2: "mop", 3: "side brush", 4: "clear water filter",
    5: "roller brush", 6: "detergent", 7: "smart module filter", 8: "dust bag",
    20: "station bag", 21: "silver ions", 22: "curing agent", 23: "heavy detergent",
    24: "inner dust box",
}

# Best-effort help-center deep link for a robot error code. The app's goHelpCenterByCode
# builds <localized help base>?code=<n>&deviceId=…&lang=…; the exact base is a runtime
# i18n value we can't read, so this is inferred from the Flow's help-center family and
# should be corrected if a real error opens a different path. The raw code is the fallback.
ERROR_HELP_URL_TEMPLATE = (
    "https://help.narwal.com/helpcenter/vall/#/p2/question/all?eType=1&code={code}&lang=en-US"
)
