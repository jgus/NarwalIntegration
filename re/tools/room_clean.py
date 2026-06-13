#!/usr/bin/env python3
"""Validated room-clean tester for the Narwal Flow 2 over the LAN WebSocket.

Sends the RE'd /clean/start_clean request (StartClean -> CleanTask) for the
given room ids, confirms the robot is actually targeting them via
clean/current_clean_task/get, then cancels and redocks. This is the live proof
behind the #25/#37 fix. See project_history.md for the protocol.

Run from the s2 host (coexists with HA's container connection — one WS per
client IP). Needs websockets + blackboxprotobuf (the flake devShell provides
both): `nix develop` then `python re/tools/room_clean.py 2 12`.

Env: NARWAL_HOST, NARWAL_DEVICE_ID, NARWAL_PREFIX override the defaults below.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Import the in-repo client (top-level narwal_client package).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import blackboxprotobuf as bbp  # noqa: E402
from narwal_client import NarwalClient  # noqa: E402

HOST = os.environ.get("NARWAL_HOST", "narwal-test")
DEVICE_ID = os.environ.get("NARWAL_DEVICE_ID", "7228565170b34dd6a242d983f1fc0eeb")
PREFIX = os.environ.get("NARWAL_PREFIX", "/iSuVlI1If2")

# CleanParam the app sends for a room clean (captured live, robot-accepted).
# Field semantics are only partly known — see project_history.md TODO.
PARAM = {"1": 5, "2": 2, "3": 1, "4": 3, "5": 1, "6": 2, "8": 2}


def build_start_clean(room_ids: list[int], map_id: int) -> bytes:
    """StartClean_Request{1: CleanTask{1: map_id, 2: [CleanItem...], 3: {}, 5: 3}}."""
    items = [
        {"1": {"1": 1, "2": rid}, "2": dict(PARAM), "3": i + 1}
        for i, rid in enumerate(room_ids)
    ]
    task = {"1": map_id, "2": items if len(items) > 1 else items[0], "3": {}, "5": 3}
    item_td = {
        "type": "message", "seen_repeated": True, "message_typedef": {
            "1": {"type": "message", "message_typedef": {"1": {"type": "int"}, "2": {"type": "int"}}},
            "2": {"type": "message", "message_typedef": {k: {"type": "int"} for k in PARAM}},
            "3": {"type": "int"},
        },
    }
    td = {"1": {"type": "message", "message_typedef": {
        "1": {"type": "int"}, "2": item_td,
        "3": {"type": "message", "message_typedef": {}}, "5": {"type": "int"},
    }}}
    return bbp.encode_message({"1": task}, td)


def active_room(raw: bytes) -> int | None:
    try:
        d, _ = bbp.decode_message(raw)
        e = d["2"]["2"]
        e = e[0] if isinstance(e, list) else e
        return e["1"]["2"]
    except Exception:
        return None


async def main(room_ids: list[int]) -> None:
    c = NarwalClient(HOST, device_id=DEVICE_ID, topic_prefix=PREFIX)
    await c.connect()
    try:
        try:
            await c.discover_device_id(timeout=20)
        except Exception as e:
            print("wake:", e)
        await c.get_status(full_update=True)
        ws = getattr(c.state.working_status, "name", c.state.working_status)
        print(f"pre: ws={ws} battery={getattr(c.state, 'battery_level', '?')}")
        if ws in ("CLEANING", "CLEANING_ALT"):
            print("ABORT: already cleaning")
            return

        md = await c.get_map()
        map_id = md.map_id if md else 0
        print(f"active map_id={map_id}; rooms={room_ids}")
        payload = build_start_clean(room_ids, map_id)
        r = await c.send_command("clean/start_clean", payload, timeout=12)
        print(f"start_clean result_code={r.result_code} (1=OK, 2=NOT_APPLICABLE, "
              f"3=CONFLICT, 4=NOT_READY/STANDBY)")
        if r.result_code != 1:
            return

        loop = asyncio.get_event_loop()
        end = loop.time() + 25
        while loop.time() < end:
            await asyncio.sleep(3)
            tr = await c.send_command("clean/current_clean_task/get", b"", timeout=6)
            ar = active_room(tr.raw_payload) if tr.result_code == 1 else None
            print(f"  active_task_room={ar}")
            if ar in room_ids:
                print(f"  >>> CONFIRMED targeting {ar}")
                break
        print("cancelling + redocking…")
        await c.cancel()
        await c.return_to_base(timeout=20)
    finally:
        await c.disconnect()


if __name__ == "__main__":
    rooms = [int(a) for a in sys.argv[1:]] or [2]
    asyncio.run(main(rooms))
