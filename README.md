# Narwal Robot Vacuum — Home Assistant Integration

A fully **local, cloud-independent** [Home Assistant](https://www.home-assistant.io/) custom integration for Narwal robot vacuums. Communicates directly with your vacuum over your local network via WebSocket — no cloud account or internet connection required.

> **v1.0.1** — Vacuum control, sensors, live map with room labels, and obstacle overlay. Available via HACS.

> ### ⚠️ Known broken in v1.0.1
>
> Community reverse-engineering in July 2026 found that **room-specific cleaning has never worked correctly**. The integration sends clean commands to `clean/plan/start`, which ignores the payload and runs whatever plan is stored on the robot. Three contributors confirmed this independently ([#37](https://github.com/sjmotew/NarwalIntegration/issues/37)).
>
> | Issue | Impact | Fix |
> |---|---|---|
> | **Room cleaning ignores your selection** | The robot cleans its last plan or your first Narwal-app shortcut instead of the rooms you picked. On **Flow 2** it can also clear the map stored on the robot, which you then have to reopen manually in the Narwal app ([#55](https://github.com/sjmotew/NarwalIntegration/issues/55)) | [#49](https://github.com/sjmotew/NarwalIntegration/pull/49) |
> | **Wrong room type labels** | Unnamed rooms show incorrect types on all models. The lookup table is misaligned from index 5 — e.g. a bathroom may display as "Study". Rooms you have named in the Narwal app are unaffected. The fix is written but its enum ordering is not yet confirmed, so it is deliberately held back rather than shipped wrong twice | [#48](https://github.com/sjmotew/NarwalIntegration/pull/48) |
>
> **Fixed in v1.0.1:** the cleaning-area sensor now reports real covered area instead of a constant 1.8 m² ([#51](https://github.com/sjmotew/NarwalIntegration/pull/51)).
>
> **Until the room-clean fix ships, start cleans from the Narwal app rather than Home Assistant if you are on a Flow 2.** Whole-house `vacuum.start` is also affected on newer firmware — it reports success and does nothing ([#69](https://github.com/sjmotew/NarwalIntegration/issues/69)). Status, sensors, and the map are unaffected. Progress is tracked in [#66](https://github.com/sjmotew/NarwalIntegration/issues/66).

## Device Compatibility

This integration uses a **local WebSocket connection on port 9002**. Only models that expose this port are supported.

| Model | Status | Notes |
|-------|--------|-------|
| **Narwal Flow** (AX12) | **Working** | Primary development target. On firmware v01.07.22+, `vacuum.start` needs a loaded map ([#36](https://github.com/sjmotew/NarwalIntegration/issues/36)). |
| **Narwal Flow 2** (QxMSPG6VSO) | **Working** | See the room-cleaning warning above before using `vacuum.clean_area` |
| **Freo Z10 Ultra** (CX4) | **Working** | Community confirmed |
| **Freo Z10 Pro / Turbo** (AX26) | **Working** | Same product key and firmware (v01.02.00.15) reported under both names ([#40](https://github.com/sjmotew/NarwalIntegration/issues/40), [#70](https://github.com/sjmotew/NarwalIntegration/issues/70)). Room cleaning confirmed working with [#49](https://github.com/sjmotew/NarwalIntegration/pull/49). |
| **Freo X10 Pro** (AX15) | **Working** | Community confirmed ([#12](https://github.com/sjmotew/NarwalIntegration/issues/12)) |
| **Narwal JX** | **Unconfirmed** | Product key known, no working report yet — testers welcome ([#42](https://github.com/sjmotew/NarwalIntegration/issues/42)) |
| **Freo Z Ultra** (CX7) | **Not Compatible** | Port 9002 open but no local broadcasts; cloud-only ([#5](https://github.com/sjmotew/NarwalIntegration/issues/5), confirmed by @Folg0re) |
| **Freo X Ultra** (AX18/AX19) | **Not Compatible** | Uses ZeroMQ (port 6789) + Tuya cloud, not WebSocket ([#4](https://github.com/sjmotew/NarwalIntegration/issues/4)) |
| **Freo X Plus** | **Not Compatible** | Cloud-only — no local API |
| **Narwal J-series** (J1/J4/J5) | **Not Compatible** | J1: HTTP-only (port 8080); J4/J5: cloud-only (Tuya) |

Models marked **Not Compatible** use a different protocol or are cloud-only. This is a hardware/firmware limitation.

**Other models?** Check with `nmap -p 9002 <your-vacuum-ip>`. If open, [open an issue](https://github.com/sjmotew/NarwalIntegration/issues/new/choose) with your model and results.

## Features

### Vacuum Control
- **Start / Stop / Pause / Resume** — validated on hardware (see the note above for `start` on newer Flow firmware)
- **Return to dock** / **Locate** (robot announces "Robot is here")
- **Fan speed** — Quiet, Normal, Strong, Max (set-only; robot doesn't broadcast current level)
- **Room-specific cleaning** — exposed in the HA UI (requires HA 2026.3+), but **currently broken** — see the warning above

### Sensors
- Battery level, cleaning time, firmware version
- Docked status (binary sensor), charging state (Charging / Fully Charged / Not Charging)
- Cleaning area — present but **currently reports a fixed 1.8 m²** ([#51](https://github.com/sjmotew/NarwalIntegration/pull/51))

### Live Map
- Color-coded floor plan with room labels (all rooms — user-named and auto-generated)
- Furniture/obstacle overlay from the robot's stored map data
- Dock marker and live robot trail during cleaning (~1.5s refresh)

### Connectivity
- Real-time WebSocket push updates
- Auto-reconnect with exponential backoff
- Wake system for sleeping robots + keepalive heartbeat
- 60-second polling fallback

## Installation

### HACS (Recommended)

1. Open **HACS** > three-dot menu > **Custom repositories**
2. Add: `https://github.com/sjmotew/NarwalIntegration` (category: Integration)
3. Find **Narwal Flow Robot Vacuum** and click **Download**
4. **Restart Home Assistant**

### Manual

1. Copy `custom_components/narwal/` to your HA `config/custom_components/` directory
2. **Restart Home Assistant**

### Setup

1. **Settings > Devices & Services > Add Integration** > search "Narwal"
2. Enter your vacuum's IP address and select your model
3. Entities are created automatically

> **Tip:** Assign a static IP to your vacuum in your router.

## Requirements

- Narwal vacuum on the same local network as Home Assistant
- Port 9002 reachable (no firewall blocking)
- Home Assistant 2025.1.0+ / Python 3.12+

## Known Limitations

- **Wake from deep sleep is unreliable** — robot may not respond after long idle periods. Opening the Narwal app briefly can help.
- **Single connection** — close the Narwal app before using HA to avoid conflicts.
- **Fan speed is set-only** — robot doesn't broadcast its current level.
- **Default clean settings** — start and room-specific clean use max suction, wet mop, single pass. Per-room customization is not yet available.
- **Map may be stale** — robot can return an old map. A new clean cycle typically refreshes it.

## Future Features (On Hold)

These features have been researched and probed but are **on hold** pending further reverse engineering:

| Feature | Status | Blocker |
|---------|--------|---------|
| **Camera snapshots** | Client method works (robot returns ~170KB) | Image data is **AES-encrypted** — APK reverse engineering needed for decryption key |
| **Camera LED control** | Partial response from robot | Correct payload format unconfirmed; needs idle-state testing |
| **Vision obstacle overlay** | Built, tested, and removed | Robot broadcasts raw AI candidates (3-6x more than app shows), not confirmed detections. Unusable for map overlay. |
| **Patrol / cruise mode** | Topics identified in APK | Not yet probed; depends on camera working first |
| **Custom clean settings** | Protocol known | Not yet exposed in HA UI |

Camera snapshot and LED entities will be added once the AES decryption key is extracted from the Narwal APK.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Cannot connect" during setup | Verify IP and that port 9002 is reachable. If it still fails, **open the Narwal app on your phone the moment you press Submit** — a sleeping robot may not answer within the setup timeout ([#40](https://github.com/sjmotew/NarwalIntegration/issues/40)). |
| Room cleaning runs the wrong rooms | Known bug — see the warning at the top of this page ([#37](https://github.com/sjmotew/NarwalIntegration/issues/37)). |
| Entities show "Unavailable" | Robot may be asleep. Open Narwal app briefly to wake it. |
| Map not showing | Map loads after robot wakes. A new clean refreshes a stale map. |
| Commands not responding | Close the Narwal app — only one WebSocket connection at a time. |
| Z10 Ultra disconnects | Re-add the integration with the correct model selected. |

## Reporting Issues

Use the [issue templates](https://github.com/sjmotew/NarwalIntegration/issues/new/choose) — they collect your HA version, model, and debug logs for faster diagnosis.

## Disclaimer

This is an **unofficial**, community-developed integration — not affiliated with or endorsed by Narwal. The local protocol was reverse-engineered from network traffic and the Narwal mobile application.

- **Use at your own risk.** No warranty.
- **No cloud dependency.** No external data transmission.
- **Firmware updates** from Narwal may break this integration at any time.

## Contributing

Contributions and testing welcome! If you have a non-Flow Narwal model, testing reports are especially valuable.

## License

MIT
