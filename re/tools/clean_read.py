#!/usr/bin/env python3
"""READ the Narwal robot's current clean plan / active clean task, to learn the
real /clean/plan/start payload schema the app uses. Read-only.

Runs from the host (coexists with the HA integration — WS slot is per-client-IP)."""

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

READ_TOPICS = [
    ("clean/cur_plan/get", b""),
    ("clean/current_clean_task/get", b""),
    ("clean/plan/get", b""),
]


def show(v, depth=0, maxb=48):
    pad = "  " * depth
    if isinstance(v, dict):
        for k, sub in v.items():
            if isinstance(sub, (dict, list)):
                print(f"{pad}{k}:")
                show(sub, depth + 1, maxb)
            elif isinstance(sub, bytes):
                print(f"{pad}{k}: bytes[{len(sub)}] {sub[:maxb].hex()}")
            else:
                print(f"{pad}{k}: {sub!r}")
    elif isinstance(v, list):
        for i, item in enumerate(v):
            if isinstance(item, (dict, list)):
                print(f"{pad}[{i}]")
                show(item, depth + 1, maxb)
            else:
                print(f"{pad}[{i}] {item!r}")
    else:
        print(f"{pad}{v!r}")


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    client = NarwalClient(HOST, device_id=DEVICE_ID, topic_prefix=PREFIX)
    await client.connect()
    print(f"connected to {HOST}")
    try:
        try:
            did = await client.discover_device_id(timeout=20.0)
            print(f"woke, device_id={did}")
        except Exception as e:
            print(f"wake note: {e!r}")
        for topic, payload in READ_TOPICS:
            try:
                resp = await client.send_command(topic, payload, timeout=15.0)
                raw = resp.raw_payload
                (OUT / (topic.replace("/", "_") + ".bin")).write_bytes(raw or b"")
                print(f"\n===== {topic}  result={resp.result_code}  bytes={len(raw or b'')} =====")
                if raw:
                    try:
                        d, _ = bbp.decode_message(raw)
                        show(d)
                    except Exception as e:
                        print(f"  decode error: {e!r}  hex={raw[:80].hex()}")
            except Exception as e:
                print(f"\n===== {topic}  ERROR: {e!r}")
    finally:
        await client.disconnect()
        print("\ndisconnected")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
