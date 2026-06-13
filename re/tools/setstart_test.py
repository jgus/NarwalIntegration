#!/usr/bin/env python3
"""Test the real room-clean flow learned from the APK: UpdateCurPlan(rooms) -> StartWithPlan(id).
Reuses the live cur_plan as a template, swapping zoneId. Coexists with HA."""
from __future__ import annotations
import asyncio, os, sys, copy
sys.path.insert(0, "/service/home-assistant/custom_components/narwal")
import blackboxprotobuf as bbp
from narwal_client import NarwalClient

HOST, DEVICE_ID, PREFIX = "narwal-test", "7228565170b34dd6a242d983f1fc0eeb", "/iSuVlI1If2"
ROOM_ID = int(os.environ.get("ROOM_ID", "9"))

def dec(raw): return bbp.decode_message(raw)[0] if raw else {}

async def main():
    c = NarwalClient(HOST, device_id=DEVICE_ID, topic_prefix=PREFIX)
    await c.connect()
    try:
        try: await c.discover_device_id(timeout=20)
        except Exception as e: print("wake:", e)

        # 1) read current plan -> get mapId + an area-option template (CleanPlan field 9)
        r = await c.send_command("clean/cur_plan/get", b"", timeout=10)
        plan = dec(r.raw_payload).get("2", {})
        print("cur_plan CleanPlan:", plan)
        map_id = plan.get("2", 1)
        tmpl = plan.get("9")
        tmpl = (tmpl[0] if isinstance(tmpl, list) else tmpl) if tmpl else {"1": 1, "2": 1, "7": {"1": {"1": 2, "2": 1}, "2": {"1": 1, "2": 3, "3": 2}}}
        area = copy.deepcopy(tmpl); area["1"] = ROOM_ID    # swap zoneId -> target room
        print(f"map_id={map_id}  new area option (zoneId={ROOM_ID}):", area)

        # 2) UpdateCurPlan {1: [area]}
        up = bbp.encode_message({"1": area}, {"1": {"type": "message", "message_typedef": _td(area)}})
        ru = await c.send_command("clean/plan/update_cur_plan", up, timeout=12)
        print(f"UpdateCurPlan result={ru.result_code}", flush=True)

        # 3) verify cur_plan now targets ROOM_ID
        r2 = await c.send_command("clean/cur_plan/get", b"", timeout=10)
        p2 = dec(r2.raw_payload).get("2", {}); a2 = p2.get("9"); a2 = a2[0] if isinstance(a2, list) else a2
        print("cur_plan after update, area zoneId =", (a2 or {}).get("1"), flush=True)

        # 4) StartWithPlan {1: planId=0, 2: mapId}
        sp = bbp.encode_message({"1": 0, "2": int(map_id)}, {"1": {"type": "int"}, "2": {"type": "int"}})
        rs = await c.send_command("clean/plan/start", sp, timeout=12)
        print(f"StartWithPlan(planId=0,mapId={map_id}) result={rs.result_code}", flush=True)

        # 5) watch
        loop = asyncio.get_event_loop(); end = loop.time() + 50; seen = object()
        while loop.time() < end:
            await asyncio.sleep(3)
            ws = getattr(c.state.working_status, "name", c.state.working_status)
            try:
                tr = await c.send_command("clean/current_clean_task/get", b"", timeout=6)
                td = dec(tr.raw_payload); e = td.get("2", {}).get("2") if tr.result_code == 1 else None
                e = e[0] if isinstance(e, list) else e
                room = (e or {}).get("1", {}).get("2") if e else None
            except Exception: room = "?"
            k = (ws, room)
            if k != seen: seen = k; print(f"  ws={ws} task_room={room}", flush=True)
    finally:
        await c.disconnect()

def _td(v):
    if isinstance(v, dict):
        return {k: ({"type": "message", "message_typedef": _td(sv)} if isinstance(sv, dict) else {"type": "int"}) for k, sv in v.items()}
    return {}

asyncio.run(main())
