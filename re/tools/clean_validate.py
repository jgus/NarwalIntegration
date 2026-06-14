#!/usr/bin/env python3
"""Validate Narwal Flow 2 CleanParam field handling over the LAN WebSocket.

Subcommands:
  probe              Read-only. Dump status + active map + current_clean_task + cur_plan,
                     fully decoded. No clean is started; the robot does not move.
  once               Start ONE clean/start_clean with a chosen mode + param overrides,
                     read back current_clean_task and cur_plan, then cancel + redock.
  ab                 Run TWO cleans differing only in one CleanParam tag and diff the
                     readbacks. This answers the open RE question: the app's
                     CleanTask->CleanPlan converter never reads tags 3 (mopStrengthLevel)
                     or 8 (overlapLevel), so we don't know if the ROBOT honors them.
                     Comparing readbacks across a single-field change shows whether the
                     robot preserves/derives it.

`once` and `ab` PHYSICALLY undock the robot; each case cancels + returns to base before
the next. Run from the s2 host (one WS per client IP — coexists with HA's container
connection). See project_history.md "CleanParam — fully decoded" for tags/enums.

Env: NARWAL_HOST, NARWAL_DEVICE_ID, NARWAL_PREFIX override the defaults below.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import blackboxprotobuf as bbp  # noqa: E402
from narwal_client import NarwalClient  # noqa: E402
from narwal_client.const import CommandResult, WorkingStatus  # noqa: E402

HOST = os.environ.get("NARWAL_HOST", "narwal-test")
DEVICE_ID = os.environ.get("NARWAL_DEVICE_ID", "7228565170b34dd6a242d983f1fc0eeb")
PREFIX = os.environ.get("NARWAL_PREFIX", "/iSuVlI1If2")

DOCKED = {WorkingStatus.DOCKED_V2, WorkingStatus.DOCKED, WorkingStatus.CHARGED}
CLEANING = {WorkingStatus.CLEANING, WorkingStatus.CLEANING_ALT}

# CleanParam tag -> name, and enum value labels, from the RE decode (project_history.md).
TAG_NAME = {
    "1": "mode", "2": "fanLevel", "3": "mopStrengthLevel", "4": "mopHumidity",
    "5": "sweepTime", "6": "mopTime", "7": "sweepMopSyncTime", "8": "overlapLevel",
    "9": "enableSmartMode", "10": "enableHeavyDirtyClean",
}
ENUM_LABEL = {
    "1": {0: "UNSPECIFIED", 2: "SWEEP", 3: "MOP", 4: "SWEEP_MOP_SYNC", 5: "SWEEP_THEN_MOP"},
    "2": {0: "UNSPECIFIED", 1: "MUTE", 2: "NORMAL", 3: "STRONG", 4: "DEEP", 5: "SUPER"},
    "3": {0: "UNSPECIFIED", 1: "NORMAL", 2: "HIGH"},
    "4": {0: "UNSPECIFIED", 1: "DRY", 2: "NORMAL", 3: "WET"},
    "8": {0: "UNSPECIFIED", 1: "NORMAL", 2: "DENSE"},
}


def base_param(mode: int) -> dict[str, int]:
    """A robot-accepted CleanParam for `mode` with all enum fields at safe defaults.

    Includes only the pass-count tag the mode actually consumes (sweep 5, mop 6, sync 7).
    """
    p = {"1": mode, "2": 2, "3": 1, "4": 2, "8": 1}  # fan/mopStrength/humidity/overlap
    if mode in (2, 5):
        p["5"] = 1
    if mode in (3, 5):
        p["6"] = 2
    if mode == 4:
        p["7"] = 2
    return p


def label(tag: str, value: int) -> str:
    name = TAG_NAME.get(tag, f"tag{tag}")
    enum = ENUM_LABEL.get(tag)
    return f"{name}={value}" + (f" ({enum[value]})" if enum and value in enum else "")


def fmt_param(param: dict) -> str:
    return ", ".join(label(t, param[t]) for t in sorted(param, key=int))


def build_start_clean(room_ids: list[int], map_id: int, param: dict[str, int],
                      task_type: int = 3) -> bytes:
    """StartClean_Request{1: CleanTask{1: map_id, 2: [CleanItem...], 3: {}, 5: task_type}}.

    CleanTask.taskType (field 5) is the execution-mode carrier the robot honors — the app
    derives it from the chosen CleanMode (1 GENERAL_SWEEP, 2 GENERAL_MOP, 3 SWEEP_THEN_MOP,
    4 SWEEP_MOP_SYNC). Per-item CleanParam.mode alone does NOT change what the robot does.
    """
    items = [
        {"1": {"1": 1, "2": rid}, "2": dict(param), "3": i + 1}
        for i, rid in enumerate(room_ids)
    ]
    task = {"1": map_id, "2": items if len(items) > 1 else items[0], "3": {}, "5": task_type}
    item_td = {
        "type": "message", "seen_repeated": True, "message_typedef": {
            "1": {"type": "message", "message_typedef": {"1": {"type": "int"}, "2": {"type": "int"}}},
            "2": {"type": "message", "message_typedef": {k: {"type": "int"} for k in param}},
            "3": {"type": "int"},
        },
    }
    td = {"1": {"type": "message", "message_typedef": {
        "1": {"type": "int"}, "2": item_td,
        "3": {"type": "message", "message_typedef": {}}, "5": {"type": "int"},
    }}}
    return bbp.encode_message({"1": task}, td)


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj).hex()
    return obj


def decode(raw: bytes) -> object:
    if not raw:
        return None
    try:
        msg, _ = bbp.decode_message(raw)
    except Exception as e:  # blackboxprotobuf raises bare Exception on malformed input
        return {"_decode_error": str(e), "_hex": raw.hex()}
    return _jsonable(msg)


def task_clean_params(decoded: object) -> list[dict]:
    """CleanParam dicts (keyed by tag) from a decoded current_clean_task response."""
    if not isinstance(decoded, dict):
        return []
    task = decoded.get("2")
    if not isinstance(task, dict):
        return []
    items = task.get("2")
    if items is None:
        return []
    if isinstance(items, dict):
        items = [items]
    return [it.get("2", {}) for it in items if isinstance(it, dict)]


# CleanAreaOption sub-option fields the robot's plan can carry per mode.
_PLAN_SUBOPT = {"4": "sweep", "5": "mop", "6": "sweep_mop_sync", "7": "sweep_then_mop"}


def plan_area_options(decoded: object) -> list[dict]:
    """Flatten a decoded cur_plan to [{zoneId, cleanZoneType, <suboption>: {...}}].

    The robot derives mopStrengthLevel into MopAreaOption.field1 — the field the app's
    own converter never sets — so this is where tag 3 honoring shows up. overlapLevel has
    no plan field, so its absence here is the signal for tag 8.
    """
    if not isinstance(decoded, dict):
        return []
    plan = decoded.get("2")
    if not isinstance(plan, dict):
        return []
    areas = plan.get("9")
    if areas is None:
        return []
    if isinstance(areas, dict):
        areas = [areas]
    out = []
    for a in areas:
        if not isinstance(a, dict):
            continue
        entry = {"zoneId": a.get("1"), "cleanZoneType": a.get("2")}
        for field, name in _PLAN_SUBOPT.items():
            if field in a:
                entry[name] = a[field]
        out.append(entry)
    return out


async def status(c: NarwalClient) -> WorkingStatus:
    await c.get_status(full_update=True)
    return c.state.working_status


async def wait_docked(c: NarwalClient, timeout: float = 180.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ws = await status(c)
        if ws in DOCKED:
            return True
        await asyncio.sleep(4)
    return False


def task_type_of(decoded: object) -> object:
    """CleanTask.taskType (field 5) from a decoded current_clean_task response."""
    if isinstance(decoded, dict) and isinstance(decoded.get("2"), dict):
        return decoded["2"].get("5")
    return None


def plan_clean_mode(decoded: object) -> object:
    """CleanPlan.cleanMode (field 3) from a decoded cur_plan response."""
    if isinstance(decoded, dict) and isinstance(decoded.get("2"), dict):
        return decoded["2"].get("3")
    return None


async def read_back(c: NarwalClient) -> dict:
    """Decoded current_clean_task + cur_plan, with the mode-bearing fields extracted."""
    ct = await c.send_command("clean/current_clean_task/get", b"", timeout=8)
    cp = await c.send_command("clean/cur_plan/get", b"", timeout=8)
    ct_dec = decode(ct.raw_payload) if ct.result_code == CommandResult.SUCCESS else None
    cp_dec = decode(cp.raw_payload) if cp.result_code == CommandResult.SUCCESS else None
    return {
        "current_clean_task": {"result": int(ct.result_code), "decoded": ct_dec,
                               "task_type": task_type_of(ct_dec),
                               "clean_params": task_clean_params(ct_dec)},
        "cur_plan": {"result": int(cp.result_code), "decoded": cp_dec,
                     "clean_mode": plan_clean_mode(cp_dec),
                     "area_options": plan_area_options(cp_dec)},
    }


async def run_case(c: NarwalClient, room_ids: list[int], map_id: int,
                   param: dict[str, int], ready_timeout: float = 600.0) -> dict:
    """Start one clean, read back, cancel + redock. Returns the readback + result code.

    Retries start_clean through the post-wash CONFLICT(3) / not-docked NOT_READY(4) window
    until the robot accepts the task or `ready_timeout` elapses — the robot self-washes
    after every job, so the prior case's redock can leave it busy for minutes.
    """
    print(f"\n>>> case: rooms={room_ids} | {fmt_param(param)}")
    payload = build_start_clean(room_ids, map_id, param)
    deadline = time.monotonic() + ready_timeout
    while True:
        ws = await status(c)
        r = await c.send_command("clean/start_clean", payload, timeout=12)
        if r.result_code == CommandResult.SUCCESS:
            break
        retryable = r.result_code in (CommandResult.CONFLICT, CommandResult.NOT_READY)
        if retryable and time.monotonic() < deadline:
            print(f"  not ready (result={r.result_code}, ws={ws.name}); waiting 15s…")
            await asyncio.sleep(15)
            continue
        print(f"  start_clean result={r.result_code} "
              f"(1=OK 2=NOT_APPLICABLE 3=CONFLICT 4=NOT_READY) — skipping case")
        return {"started": False, "result_code": int(r.result_code), "sent_param": param}
    print("  start_clean accepted (result=1)")

    await asyncio.sleep(6)  # let the robot adopt the task and build cur_plan
    readback = await read_back(c)
    echoed = readback["current_clean_task"]["clean_params"]
    print(f"  robot-echoed CleanParam(s): "
          f"{[fmt_param(p) for p in echoed] if echoed else '(none)'}")
    print(f"  robot-derived plan area_options: "
          f"{readback['cur_plan']['area_options'] or '(none)'}")

    print("  cancel + return to base…")
    await c.cancel()
    await c.return_to_base(timeout=20)
    if not await wait_docked(c):
        print("  WARNING: robot did not report docked within timeout")
    return {"started": True, "result_code": int(r.result_code),
            "sent_param": param, **readback}


# Thorough matrix: one case per mode, each with distinct non-default values so the robot's
# plan readback reveals which CleanParam tag each plan field tracks. overlapLevel=2 (DENSE)
# in every case probes whether tag 8 ever surfaces (it has no plan field — see decode).
MATRIX = [
    ("mode3_MOP", 3, {"3": 2, "4": 3, "6": 2, "8": 2}),
    ("mode2_SWEEP", 2, {"2": 3, "5": 3, "8": 2}),
    ("mode4_SWEEP_MOP_SYNC", 4, {"2": 4, "3": 2, "4": 1, "7": 3, "8": 2}),
    ("mode5_SWEEP_THEN_MOP", 5, {"2": 2, "3": 2, "4": 3, "5": 1, "6": 4, "8": 2}),
]


async def cmd_matrix(c: NarwalClient, room: int) -> None:
    md = await c.get_map()
    map_id = md.map_id if md else 0
    ws = await status(c)
    if ws in CLEANING:
        print(f"robot is {ws.name}; cancelling current job + returning to base…")
        await c.cancel()
        await c.return_to_base(timeout=20)

    results = {}
    for name, mode, overrides in MATRIX:
        param = base_param(mode) | overrides
        print(f"\n########## {name} ##########")
        results[name] = await run_case(c, [room], map_id, param)

    print("\n=== MATRIX SUMMARY (robot-derived plan per mode) ===")
    for name, _mode, _ov in MATRIX:
        r = results[name]
        if not r.get("started"):
            print(f"  {name}: NOT STARTED (result={r.get('result_code')})")
            continue
        print(f"  {name}: sent={fmt_param(r['sent_param'])}")
        print(f"           plan={r['cur_plan']['area_options']}")
    print("\nFull readbacks:")
    print(json.dumps(_jsonable(results), indent=2))


# GetFeatureList bool tags (from BuilderInfo) relevant to clean params; for annotation.
FEATURE_TAGS = {"6": "supportPetMode", "7": "supportOverlapAdjust",
                "8": "supportStationCleanMode"}


def _find_feature_struct(obj: object) -> dict | None:
    """The sub-dict holding the GetFeatureList bools (has the supportOverlapAdjust tag 7)."""
    if isinstance(obj, dict):
        if "7" in obj and any(k in obj for k in ("6", "8")):
            return obj
        for v in obj.values():
            found = _find_feature_struct(v)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_feature_struct(v)
            if found:
                return found
    return None


async def cmd_features(c: NarwalClient) -> None:
    r = await c.send_command("common/get_feature_list", b"", timeout=8)
    print(f"common/get_feature_list result={r.result_code}")
    dec = decode(r.raw_payload)
    feats = _find_feature_struct(dec)
    if feats:
        print("\nfeature flags (known tags):")
        for tag, name in FEATURE_TAGS.items():
            print(f"  {name} (tag {tag}) = {feats.get(tag, '(absent → false)')}")
        print(f"\n>>> supportOverlapAdjust = {feats.get('7', 0)} "
              f"({'TRUE' if feats.get('7') else 'FALSE — robot ignores overlapLevel'})")
    print("\nfull decoded get_feature_list:")
    print(json.dumps(_jsonable(dec), indent=2))


async def cmd_ov(c: NarwalClient, room: int, level: int, ready_timeout: float = 150.0) -> None:
    """Start a vacuum-only (mode 2) clean of `room` with overlapLevel=`level`, leave it running.

    If the robot is already cleaning, stop it with cancel only (NOT return_to_base) so it does
    not redock — testing whether start_clean is accepted off-dock. The robot is left cleaning
    for physical observation; run `dock` to send it home afterward.
    """
    md = await c.get_map()
    map_id = md.map_id if md else 0
    ws = await status(c)
    if ws in CLEANING:
        print(f"robot is {ws.name}; stopping WITHOUT docking (cancel only)…")
        await c.cancel()
        await asyncio.sleep(8)
        ws = await status(c)
        print(f"  after cancel: ws={ws.name}")

    param = base_param(2) | {"8": level}  # mode 2 = SWEEP (vacuum only)
    print(f"\n>>> office vacuum-only, {label('8', level)} | {fmt_param(param)}")
    payload = build_start_clean([room], map_id, param)
    deadline = time.monotonic() + ready_timeout
    while True:
        ws = await status(c)
        r = await c.send_command("clean/start_clean", payload, timeout=12)
        if r.result_code == CommandResult.SUCCESS:
            break
        if r.result_code in (CommandResult.CONFLICT, CommandResult.NOT_READY) \
                and time.monotonic() < deadline:
            print(f"  not ready (result={r.result_code}, ws={ws.name}); retry in 10s "
                  f"(NOT_READY from STANDBY likely means it must dock first)…")
            await asyncio.sleep(10)
            continue
        print(f"  start_clean result={r.result_code} — NOT started "
              f"(4=NOT_READY: off-dock restart not accepted; robot needs the dock).")
        return

    print("  start_clean accepted (result=1) — robot is cleaning; OBSERVE NOW.")
    await asyncio.sleep(6)
    rb = await read_back(c)
    echoed = rb["current_clean_task"]["clean_params"]
    print(f"  echoed CleanParam: {[fmt_param(p) for p in echoed] if echoed else '(none)'}")
    print(f"  plan area_options: {rb['cur_plan']['area_options'] or '(none)'}")
    print("  left RUNNING (not docking). Run `dock` to send it home when done.")


async def cmd_dock(c: NarwalClient) -> None:
    print("cancel + return to base…")
    await c.cancel()
    await c.return_to_base(timeout=20)
    print("done; robot heading to dock.")


TASKTYPE_NAME = {1: "GENERAL_SWEEP", 2: "GENERAL_MOP", 3: "GENERAL_SWEEP_THEN_MOP",
                 4: "GENERAL_SWEEP_MOP_SYNC", 5: "CUSTOM_CLEAN"}
TASKTYPE_TO_MODE = {1: 2, 2: 3, 3: 5, 4: 4}  # CleanTask.taskType -> matching CleanParam.mode


async def cmd_modetest(c: NarwalClient, room: int, task_type: int,
                       ready_timeout: float = 150.0) -> None:
    """Start a clean of `room` with CleanTask.taskType=`task_type` and a matching CleanParam.mode.

    Reports whether cur_plan.cleanMode now tracks taskType (vs the constant 5 we saw when only
    CleanParam.mode varied). Leaves the robot running for physical observation (vacuum vs mop).
    Needs the dock, so it cancels + redocks any running clean first.
    """
    md = await c.get_map()
    map_id = md.map_id if md else 0
    ws = await status(c)
    if ws in CLEANING:
        print(f"robot is {ws.name}; cancelling + returning to base (start_clean needs the dock)…")
        await c.cancel()
        await c.return_to_base(timeout=20)
        await wait_docked(c)

    mode = TASKTYPE_TO_MODE.get(task_type, 5)
    param = base_param(mode)
    tt_name = TASKTYPE_NAME.get(task_type, f"taskType{task_type}")
    print(f"\n>>> room {room}: taskType={task_type} ({tt_name}), CleanParam.mode={mode} "
          f"({ENUM_LABEL['1'].get(mode, '?')}) | {fmt_param(param)}")
    payload = build_start_clean([room], map_id, param, task_type=task_type)
    deadline = time.monotonic() + ready_timeout
    while True:
        ws = await status(c)
        r = await c.send_command("clean/start_clean", payload, timeout=12)
        if r.result_code == CommandResult.SUCCESS:
            break
        if r.result_code in (CommandResult.CONFLICT, CommandResult.NOT_READY) \
                and time.monotonic() < deadline:
            print(f"  not ready (result={r.result_code}, ws={ws.name}); retry in 12s…")
            await asyncio.sleep(12)
            continue
        print(f"  start_clean result={r.result_code} — NOT started.")
        return

    print("  start_clean accepted (result=1) — robot is cleaning; OBSERVE NOW (vacuum? mop? both?)")
    await asyncio.sleep(6)
    rb = await read_back(c)
    tt = rb["current_clean_task"]["task_type"]
    cm = rb["cur_plan"]["clean_mode"]
    print(f"  echoed CleanTask.taskType = {tt} ({TASKTYPE_NAME.get(tt, '?')})")
    print(f"  cur_plan.cleanMode        = {cm} ({ENUM_LABEL['1'].get(cm, '?')})  "
          f"<-- tracks taskType?  (was constant 5 when only CleanParam.mode varied)")
    print(f"  plan area_options         = {rb['cur_plan']['area_options'] or '(none)'}")
    print("  left RUNNING (not docking). Run `dock` to send it home when done.")


async def cmd_probe(c: NarwalClient) -> None:
    ws = await status(c)
    print(f"working_status = {ws.name} ({int(ws)}); battery = "
          f"{getattr(c.state, 'battery_level', '?')}")
    md = await c.get_map()
    print(f"active map_id = {md.map_id if md else None}")
    rb = await read_back(c)
    print("\n=== clean/current_clean_task/get ===")
    print(json.dumps(rb["current_clean_task"], indent=2))
    print("\n=== clean/cur_plan/get ===")
    print(json.dumps(rb["cur_plan"], indent=2))


async def cmd_once(c: NarwalClient, room: int, mode: int, overrides: dict[str, int]) -> None:
    md = await c.get_map()
    map_id = md.map_id if md else 0
    param = base_param(mode) | overrides
    res = await run_case(c, [room], map_id, param)
    print("\n=== result ===")
    print(json.dumps(_jsonable(res), indent=2))


async def cmd_ab(c: NarwalClient, room: int, mode: int, tag: str, v1: int, v2: int) -> None:
    md = await c.get_map()
    map_id = md.map_id if md else 0
    results = {}
    for v in (v1, v2):
        param = base_param(mode) | {tag: v}
        results[v] = await run_case(c, [room], map_id, param)

    print(f"\n=== A/B diff on {label(tag, v1)} vs {label(tag, v2)} ===")
    for v in (v1, v2):
        r = results[v]
        if not r.get("started"):
            print(f"  {label(tag, v)}: NOT STARTED ({r})")
            continue
        echoed = r["current_clean_task"]["clean_params"]
        print(f"  {label(tag, v)}: start={r['result_code']} "
              f"echoed_tag{tag}={[p.get(tag) for p in echoed]} "
              f"plan={r['cur_plan']['area_options']}")
    print("\nFull readbacks:")
    print(json.dumps(_jsonable(results), indent=2))


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe", help="read-only; no robot movement")
    sub.add_parser("features", help="read-only; dump get_feature_list (supportOverlapAdjust)")
    p_once = sub.add_parser("once", help="one clean + readback (moves robot)")
    p_once.add_argument("--room", type=int, default=2)
    p_once.add_argument("--mode", type=int, default=4)
    p_once.add_argument("--set", action="append", default=[], metavar="TAG=VAL",
                        help="override a CleanParam tag, e.g. --set 3=2 --set 8=2")
    p_ab = sub.add_parser("ab", help="two cleans differing in one tag, diff readbacks")
    p_ab.add_argument("--room", type=int, default=2)
    p_ab.add_argument("--mode", type=int, default=4)
    p_ab.add_argument("--tag", required=True, help="CleanParam tag to vary, e.g. 3 or 8")
    p_ab.add_argument("--values", nargs=2, type=int, required=True, metavar=("V1", "V2"))
    p_mx = sub.add_parser("matrix", help="one clean per mode (2/3/4/5), thorough (moves robot)")
    p_mx.add_argument("--room", type=int, default=2)
    p_ov = sub.add_parser("ov", help="vacuum-only overlap experiment step; starts + leaves running")
    p_ov.add_argument("--room", type=int, default=2)
    p_ov.add_argument("--level", type=int, required=True, choices=[1, 2],
                      help="overlapLevel: 1=NORMAL (sparse), 2=DENSE")
    sub.add_parser("dock", help="cancel + return to base (cleanup)")
    p_md = sub.add_parser("modetest", help="start with a given CleanTask.taskType; check mode honoring")
    p_md.add_argument("--room", type=int, default=1)
    p_md.add_argument("--tasktype", type=int, required=True, choices=[1, 2, 3, 4],
                      help="1=GENERAL_SWEEP 2=GENERAL_MOP 3=SWEEP_THEN_MOP 4=SWEEP_MOP_SYNC")
    args = ap.parse_args()

    c = NarwalClient(HOST, device_id=DEVICE_ID, topic_prefix=PREFIX)
    await c.connect()
    try:
        try:
            await c.discover_device_id(timeout=20)
        except Exception as e:  # device may already be awake; not fatal
            print("wake:", e)
        if args.cmd == "probe":
            await cmd_probe(c)
        elif args.cmd == "features":
            await cmd_features(c)
        elif args.cmd == "once":
            overrides = dict(kv.split("=", 1) for kv in args.set)
            await cmd_once(c, args.room, args.mode, {k: int(v) for k, v in overrides.items()})
        elif args.cmd == "ab":
            await cmd_ab(c, args.room, args.mode, args.tag, *args.values)
        elif args.cmd == "matrix":
            await cmd_matrix(c, args.room)
        elif args.cmd == "ov":
            await cmd_ov(c, args.room, args.level)
        elif args.cmd == "dock":
            await cmd_dock(c)
        elif args.cmd == "modetest":
            await cmd_modetest(c, args.room, args.tasktype)
    finally:
        await c.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
