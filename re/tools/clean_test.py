#!/usr/bin/env python3
"""Test a reconstructed /clean/plan/start payload (byte-replica of the app's task)
against the live robot, and verify via current_clean_task readback. Coexists with HA.

ROOM_ID env selects the room (default 9 = Music Room)."""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "/service/home-assistant/custom_components/narwal")

import blackboxprotobuf as bbp  # noqa: E402
from narwal_client import NarwalClient  # noqa: E402

HOST = "narwal-test"
DEVICE_ID = "7228565170b34dd6a242d983f1fc0eeb"
PREFIX = "/iSuVlI1If2"
ROOM_ID = int(os.environ.get("ROOM_ID", "9"))

# Per-room clean params captured byte-for-byte from a working app room-clean.
PARAMS = {"1": 5, "2": 2, "3": 1, "4": 3, "5": 1, "6": 2, "8": 2}
TASK_FIELDS = {
    "1": {"type": "int"},
    "2": {"type": "message", "seen_repeated": True, "message_typedef": {
        "1": {"type": "message", "message_typedef": {"1": {"type": "int"}, "2": {"type": "int"}}},
        "2": {"type": "message", "message_typedef": {k: {"type": "int"} for k in ["1", "2", "3", "4", "5", "6", "8"]}},
        "3": {"type": "int"}}},
    "3": {"type": "message", "message_typedef": {}},
    "5": {"type": "int"}}
REQ_FIELDS = {"1": {"type": "message", "message_typedef": TASK_FIELDS}}


def build_start(room_ids):
    entries = [{"1": {"1": 1, "2": rid}, "2": dict(PARAMS), "3": i + 1}
               for i, rid in enumerate(room_ids)]
    task = {"1": 2, "2": entries if len(entries) != 1 else entries[0], "3": {}, "5": 3}
    return bbp.encode_message({"1": task}, REQ_FIELDS)


def room_of(active_raw):
    try:
        d, _ = bbp.decode_message(active_raw)
        e = d["2"]["2"]
        e = e[0] if isinstance(e, list) else e
        return e["1"]["2"]
    except Exception:
        return None


async def main():
    client = NarwalClient(HOST, device_id=DEVICE_ID, topic_prefix=PREFIX)
    await client.connect()
    try:
        try:
            await client.discover_device_id(timeout=20.0)
        except Exception as e:
            print(f"wake note: {e!r}")
        try:
            await client.get_status(full_update=True)
        except Exception as e:
            print(f"get_status note: {e!r}")
        ws = getattr(client.state.working_status, "name", client.state.working_status)
        docked = getattr(client.state, "is_docked", "?")
        print(f"pre working_status={ws} is_docked={docked}", flush=True)
        if ws in ("CLEANING", "CLEANING_ALT"):
            print(f"ABORT: robot is cleaning ({ws})", flush=True)
            return
        payload = build_start([ROOM_ID])
        print(f"payload room={ROOM_ID} hex={payload.hex()}", flush=True)
        loop = asyncio.get_event_loop()
        accepted = False
        for attempt in range(1, 13):  # ~ up to 8 min of retries
            resp = await client.send_command("clean/plan/start", payload, timeout=12.0)
            print(f"  attempt {attempt}: result_code={resp.result_code}", flush=True)
            if resp.result_code == 1:
                accepted = True
                break
            await asyncio.sleep(40)
        if not accepted:
            print("NOT ACCEPTED after retries (still CONFLICT/busy)", flush=True)
            return
        print("ACCEPTED (result_code=1) — watching navigation", flush=True)
        end = loop.time() + 50
        seen = object()
        while loop.time() < end:
            await asyncio.sleep(3)
            st = client.state
            wss = getattr(st.working_status, "name", st.working_status)
            try:
                tr = await client.send_command("clean/current_clean_task/get", b"", timeout=6.0)
                active_room = room_of(tr.raw_payload) if tr.result_code == 1 else None
            except Exception:
                active_room = "?"
            key = (wss, active_room)
            if key != seen:
                seen = key
                print(f"  ws={wss}  active_task_room={active_room}", flush=True)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
