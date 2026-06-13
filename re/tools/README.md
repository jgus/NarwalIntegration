# RE / live-test tools

Scripts for probing the Narwal Flow 2 over its LAN WebSocket (`ws://<host>:9002`,
unauthenticated, **one connection per client IP**). Run them from the **s2 host**,
not inside the HA container — the host has a different IP so it coexists with the
integration's live connection.

Deps: `websockets` + `blackboxprotobuf` — provided by the flake devShell
(`nix develop`, or direnv). They import the in-repo `narwal_client`.

The robot identity defaults (host `narwal-test`, device id, topic prefix
`/iSuVlI1If2`) are baked in; override via `NARWAL_HOST` / `NARWAL_DEVICE_ID` /
`NARWAL_PREFIX`.

| script | what it does |
|---|---|
| `room_clean.py [room_id...]` | **Validated** room clean via `/clean/start_clean`; confirms targeting, then cancels + redocks. Proof behind #25/#37. |
| `clean_read.py` | dump current clean task / plan / status |
| `clean_watch.py` | stream status broadcasts |
| `clean_topic_test.py` | fire an arbitrary clean topic/payload (env-driven) |
| `setstart_test.py` | update_cur_plan → start experiments |
| `clean_test.py` | older end-to-end clean probe |
| `parse_pb.py`, `show_msg.py` | blackboxprotobuf decode helpers |

Result codes: `1`=success, `2`=NOT_APPLICABLE (malformed/invalid room), `3`=CONFLICT
(busy/wash), `4`=NOT_READY (robot in STANDBY — must be docked). See
[../../project_history.md](../../project_history.md) for the full protocol.
