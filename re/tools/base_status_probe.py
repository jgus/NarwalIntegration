#!/usr/bin/env python3
"""Query the robot's base status once and print every field with the verified
RobotBaseStatus proto names (from decompiled BuilderInfo). Read-only."""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/service/home-assistant/custom_components/narwal")

from narwal_client import NarwalClient  # noqa: E402

HOST = "narwal-test"
DEVICE_ID = "7228565170b34dd6a242d983f1fc0eeb"
PREFIX = "/iSuVlI1If2"

# Verified RobotBaseStatus field tags -> name (decompiled _i() BuilderInfo).
NAMES = {
    1: "errorCode[]", 2: "batteryPercentage(f32)", 3: "robotTaskStatus{}",
    5: "supplyAndDrainageModuleState", 6: "inDisturbMode", 7: "triggerType",
    8: "hasTaskSchedule", 11: "stationContactType", 12: "detergentState",
    13: "bindedUuid(str)", 14: "stationSupplyWaterModuleState", 15: "terminateReason",
    16: "autoAddDetergentEnabled", 17: "telecontrolCleanStage", 18: "dustBoxStatus",
    19: "dustBagStatus", 20: "dustBoxState", 21: "dustBagState", 22: "smartModuleState",
    23: "cleanWaterTankState", 24: "sewageTankState", 25: "deviceStatusCodeList{}",
    26: "fanLevel", 27: "energyCertificationModeStatus", 28: "robotWaterTankState",
    29: "mopHumidity", 30: "mapId", 31: "manualControlStatus", 32: "robotTaskStatusList[]",
    33: "multiLiquidStatus", 34: "dryBoxFinishFlag", 35: "stationBagHealthScore(f32)",
    36: "stationBagHealthResetTime", 37: "manualControlFanCooldownTime",
    38: "curingAgentConsumptionPercent", 39: "stationBagStatus", 40: "heavyDetergentStatus",
    41: "heavyDetergentRemainPercent", 42: "streamingStatus", 43: "streamingExtraData",
    44: "hasStation", 45: "isRobotAtOrigin", 46: "robotTaskStatusListV2{}",
    47: "chargingStatus", 48: "robotTaskListExternalV2{}", 49: "batteryCooling",
    50: "ambientLightStatus",
}


async def main() -> int:
    client = NarwalClient(HOST, device_id=DEVICE_ID, topic_prefix=PREFIX)
    await client.connect()
    try:
        try:
            await client.discover_device_id(timeout=20.0)
        except Exception as e:
            print(f"wake note: {e!r}")
        resp = await client.get_status()
        bs = resp.data.get("2", {})
        print(f"=== base_status (result={resp.result_code}, {len(bs)} fields) ===")
        for k in sorted(bs, key=lambda x: int(x)):
            name = NAMES.get(int(k), "?")
            v = bs[k]
            if isinstance(v, (dict, list)):
                print(f"  {k:>2} {name:<34} {v}")
            elif isinstance(v, bytes):
                print(f"  {k:>2} {name:<34} bytes[{len(v)}] {v[:24].hex()}")
            else:
                print(f"  {k:>2} {name:<34} {v!r}")
    finally:
        await client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
