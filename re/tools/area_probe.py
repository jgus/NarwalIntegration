#!/usr/bin/env python3
"""Capture working_status / base_status broadcasts and dump all fields, to find
which field actually carries the live cleaning area. Read-only."""

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
WATCH_SECONDS = 90

seen: dict[str, bytes] = {}


def on_message(msg) -> None:
    st = msg.short_topic
    if st not in ("status/working_status", "status/robot_base_status"):
        return
    raw = msg.payload or b""
    if seen.get(st) == raw:
        return
    seen[st] = raw
    try:
        d, _ = bbp.decode_message(raw)
    except Exception as e:
        print(f"{st}: decode error {e!r}")
        return
    print(f"\n=== {st} ({len(raw)} B) ===", flush=True)
    for k, v in d.items():
        if isinstance(v, bytes):
            print(f"  {k}: bytes[{len(v)}] {v[:32].hex()}")
        elif isinstance(v, (dict, list)):
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: {v!r}")


async def main() -> int:
    client = NarwalClient(HOST, device_id=DEVICE_ID, topic_prefix=PREFIX)
    client.on_message = on_message
    await client.connect()
    try:
        try:
            await client.discover_device_id(timeout=20.0)
        except Exception as e:
            print(f"wake note: {e!r}")
        await client.subscribe_to_topics()
        print(f">>> watching {WATCH_SECONDS}s — start/stop a clean to see field 13 change <<<", flush=True)
        await asyncio.sleep(WATCH_SECONDS)
    finally:
        await client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
