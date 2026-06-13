#!/usr/bin/env python3
"""Poll the robot's active clean task while an app-driven room clean runs, to
capture the room-targeting structure. Read-only; coexists with HA."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "/service/home-assistant/custom_components/narwal")

import blackboxprotobuf as bbp  # noqa: E402
from narwal_client import NarwalClient  # noqa: E402

HOST = "narwal-test"
DEVICE_ID = "7228565170b34dd6a242d983f1fc0eeb"
PREFIX = "/iSuVlI1If2"
OUT = Path("/tmp/narwal-apk")
WATCH_SECONDS = 120


def fmt(v, depth=0):
    pad = "  " * depth
    out = []
    if isinstance(v, dict):
        for k, sub in v.items():
            if isinstance(sub, (dict, list)):
                out.append(f"{pad}{k}:")
                out.append(fmt(sub, depth + 1))
            elif isinstance(sub, bytes):
                out.append(f"{pad}{k}: bytes[{len(sub)}] {sub[:48].hex()}")
            else:
                out.append(f"{pad}{k}: {sub!r}")
    elif isinstance(v, list):
        for i, item in enumerate(v):
            out.append(f"{pad}[{i}]")
            out.append(fmt(item, depth + 1))
    else:
        out.append(f"{pad}{v!r}")
    return "\n".join(x for x in out if x)


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    client = NarwalClient(HOST, device_id=DEVICE_ID, topic_prefix=PREFIX)
    await client.connect()
    try:
        try:
            await client.discover_device_id(timeout=20.0)
        except Exception as e:
            print(f"wake note: {e!r}")
        print(">>> START THE OFFICE CLEAN IN THE APP ANY TIME NOW <<<", flush=True)
        loop = asyncio.get_event_loop()
        end = loop.time() + WATCH_SECONDS
        last = None
        captured = False
        while loop.time() < end:
            try:
                resp = await client.send_command("clean/current_clean_task/get", b"", timeout=8.0)
                raw = resp.raw_payload or b""
                if resp.result_code == 1 and raw:
                    if raw != last:
                        last = raw
                        (OUT / "active_clean_task.bin").write_bytes(raw)
                        d, _ = bbp.decode_message(raw)
                        print(f"\n=== ACTIVE TASK (result=1, {len(raw)} B) ===", flush=True)
                        print(fmt(d), flush=True)
                        captured = True
                else:
                    print(f"[poll] current_clean_task result={resp.result_code}", flush=True)
            except Exception as e:
                print(f"[poll] err {e!r}", flush=True)
            await asyncio.sleep(3)
        print(f"\n=== window ended (captured={captured}) ===", flush=True)
    finally:
        await client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
