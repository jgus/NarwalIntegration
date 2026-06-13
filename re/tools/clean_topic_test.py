#!/usr/bin/env python3
"""Test room cleaning via /clean_system/req_sweep_room_by_plan_params (the topic the
app actually uses), with the captured room-plan-param element. Verifies via task readback.

Env: ROOM_ID (default 9), TOPIC (default the sweep-room topic), MODE (list|task|wrap)."""

from __future__ import annotations
import asyncio, os, sys
sys.path.insert(0, "/service/home-assistant/custom_components/narwal")
import blackboxprotobuf as bbp
from narwal_client import NarwalClient

HOST, DEVICE_ID, PREFIX = "narwal-test", "7228565170b34dd6a242d983f1fc0eeb", "/iSuVlI1If2"
ROOM_ID = int(os.environ.get("ROOM_ID", "9"))
TOPIC = os.environ.get("TOPIC", "clean_system/req_sweep_room_by_plan_params")
MODE = os.environ.get("MODE", "list")

PARAMS = {"1": 5, "2": 2, "3": 1, "4": 3, "5": 1, "6": 2, "8": 2}
ELEM_TD = {"type": "message", "seen_repeated": True, "message_typedef": {
    "1": {"type": "message", "message_typedef": {"1": {"type": "int"}, "2": {"type": "int"}}},
    "2": {"type": "message", "message_typedef": {k: {"type": "int"} for k in ["1","2","3","4","5","6","8"]}},
    "3": {"type": "int"}}}

def elem(rid, seq=1):
    return {"1": {"1": 1, "2": rid}, "2": dict(PARAMS), "3": seq}

def build(room_ids, mode):
    elems = [elem(r, i+1) for i, r in enumerate(room_ids)]
    one = elems if len(elems) != 1 else elems[0]
    if mode == "list":      # {1: repeated elem}
        return bbp.encode_message({"1": one}, {"1": ELEM_TD})
    if mode == "task":      # {1:2, 2:repeated elem, 3:{}, 5:3}
        td = {"1": {"type": "int"}, "2": ELEM_TD, "3": {"type": "message", "message_typedef": {}}, "5": {"type": "int"}}
        return bbp.encode_message({"1": 2, "2": one, "3": {}, "5": 3}, td)
    if mode == "wrap":      # {1: {task}}
        ttd = {"1": {"type": "int"}, "2": ELEM_TD, "3": {"type": "message", "message_typedef": {}}, "5": {"type": "int"}}
        return bbp.encode_message({"1": {"1": 2, "2": one, "3": {}, "5": 3}}, {"1": {"type": "message", "message_typedef": ttd}})
    raise SystemExit("bad MODE")

def task_room(raw):
    try:
        d, _ = bbp.decode_message(raw); e = d["2"]["2"]; e = e[0] if isinstance(e, list) else e
        return e["1"]["2"]
    except Exception: return None

async def main():
    c = NarwalClient(HOST, device_id=DEVICE_ID, topic_prefix=PREFIX)
    await c.connect()
    try:
        try: await c.discover_device_id(timeout=20)
        except Exception as e: print("wake:", e)
        try: await c.get_status(full_update=True)
        except Exception as e: print("status:", e)
        ws = getattr(c.state.working_status, "name", c.state.working_status)
        print(f"pre ws={ws}  topic={TOPIC}  mode={MODE}  room={ROOM_ID}", flush=True)
        if ws in ("CLEANING", "CLEANING_ALT"):
            print("ABORT: cleaning"); return
        payload = build([ROOM_ID], MODE)
        print(f"payload hex={payload.hex()}", flush=True)
        accepted = False
        for a in range(1, 8):
            r = await c.send_command(TOPIC, payload, timeout=12)
            print(f"  attempt {a}: result_code={r.result_code}", flush=True)
            if r.result_code == 1: accepted = True; break
            await asyncio.sleep(35)
        if not accepted:
            print("NOT ACCEPTED"); return
        loop = asyncio.get_event_loop(); end = loop.time() + 60; seen = object()
        while loop.time() < end:
            await asyncio.sleep(3)
            wss = getattr(c.state.working_status, "name", c.state.working_status)
            try:
                tr = await c.send_command("clean/current_clean_task/get", b"", timeout=6)
                ar = task_room(tr.raw_payload) if tr.result_code == 1 else None
            except Exception: ar = "?"
            k = (wss, ar)
            if k != seen: seen = k; print(f"  ws={wss} active_task_room={ar}", flush=True)
    finally:
        await c.disconnect()

asyncio.run(main())
