# Narwal Flow 2 — Project History & Working Notes

Working fork of [sjmotew/NarwalIntegration](https://github.com/sjmotew/NarwalIntegration)
(Home Assistant custom integration for Narwal robot vacuums). This file is the
durable memory for the project — read it first. Running **TODO list at the foot.**

`origin` = `jgus/NarwalIntegration` (this fork), `upstream` = `sjmotew/NarwalIntegration`.
Our work lives on the **`working`** branch; per-PR feature branches are cut from `master`.

---

## Goal

Two intertwined efforts:
1. **Dogfood:** run a new Narwal Flow 2 ("Narwal Test", `vacuum.narwal_test_vacuum`)
   as the main-floor vacuum, replacing two Valetudo robots (Frodo + Sam). Tracked in
   the HA config repo, not here.
2. **Upstream:** fix the integration's broken room labels and room cleaning on the
   Flow 2, and add the missing per-clean settings — then hand working PRs upstream.

## The unit & environment

- **Robot:** Narwal Flow 2. product_key **`iSuVlI1If2`**, firmware **v01.08.01.00**,
  device_id `7228565170b34dd6a242d983f1fc0eeb`. LAN: host `narwal-test`
  (172.21.40.15:**9002**), **unauthenticated plaintext WebSocket**, **one connection
  per client IP**. Proto package `app_protol`; app codename "pita"/"octopus".
- **Run RE/test tools from the s2 host** (its own IP) so they coexist with the HA
  container's live connection. Running inside the container conflicts ("connection
  with same ip, close old one").
- **Live integration** is deployed at `/service/home-assistant/custom_components/narwal`
  (was `root:ha` and unwritable; made group-writable so `nix run .#dogfood` can sync).
- **HA** runs in podman container `home-assistant`, managed by `home-assistant.service`.
  REST/WS API via `$HASS_HOST` / `$HASS_TOKEN`. Custom-component code changes need a
  **full HA restart** (re-import) — `homeassistant.restart`, or `podman restart
  home-assistant`. Note: a pre-existing **empty `secrets.yaml`** (a NixOS-config bug)
  once blocked `homeassistant.restart`'s strict `check_config`; being fixed separately.
- The repo keeps **two synced copies** of the client: top-level `narwal_client/` and
  `custom_components/narwal/narwal_client/`. **Apply code changes to both.**

## Reverse-engineering method

App is Flutter AOT. Pipeline (automated by `nix run .#disassemble`, output gitignored
under `re/build/`):

XAPK `com.narwal.pita_global` → `config.arm64_v8a.apk` → `lib/arm64-v8a/{libapp.so,
libflutter.so}` → **blutter** ([worawit/blutter](https://github.com/worawit/blutter),
builds a matching Dart VM) → readable Dart pseudo-source under `blutter-out/asm/...`.

Gotcha: blutter `#include <capstone.h>` but nixpkgs ships `include/capstone/capstone.h`
— the flake sets `CPATH` to the capstone include dir to fix it.

Key dump paths (under `blutter-out/asm/`):
- `app_protol/proto/core/CleanTask.pb.dart` — CleanTask/CleanItem/ZoneOption/CleanParam/TaskOption
- `app_protol/proto/core/CleanOption.pb.dart`, `CleanPlan.pb.dart`
- `app_protol/proto/core/CleanTask.pbenum.dart`, `mqtt/msg/map/MapBaseType.pbenum.dart` (enums)
- `app_protol/proto/mqtt/srv/clean/...` (StartClean, plan/StartWithPlan, plan/UpdateCurPlan)
- `nr_pita_pro/sections/app_main/utils/clean_task_2_clean_plan_convert_util.dart` — **the Rosetta stone**: converts CleanParam → named CleanAreaOption sub-options
- `nr_pita_pro/.../repository/service/nr_pita_home_service_data_source_impl.dart.dart` — publishes the clean topics
- `map_engine/src/configs/map_engine_i18n_configer.dart` — room-type name switch

---

## Protocol reference (RE'd, much of it live-validated)

### Topics (clean)
- **`/clean/start_clean`** = `StartClean{1: task CleanTask}` — the real ad-hoc clean
  (`EasyCleanMQttServiceImpl::startEasyClean` → for this model sends the CleanTask raw).
  **Only works when docked** (else result 4).
- `/clean/plan/start` = `StartWithPlan{1: planId, 2: mapId}` — starts a **saved plan by
  id, ignores any room payload**. The integration wrongly used this for room cleaning
  (root cause of #25/#37). J3/Flow-2 strategy uses GetCleanPlans + StartWithPlan.
- `/clean/plan/update_cur_plan` = `UpdateCurPlan{1: repeated CleanAreaOption}` — **live
  param edit** of the running plan (e.g. `setWorkingFanLevel`), not a start path; returns
  2 when cur_plan is empty.
- Reads: `/clean/current_clean_task/get`, `/clean/cur_plan/get`, `/map/get_map`.

### Result codes (`ServiceResult`, 33 values, names stripped)
`1` SUCCESS · `2` NOT_APPLICABLE (malformed task / invalid-or-non-cleanable room) ·
`3` CONFLICT (busy / post-clean wash) · `4` **NOT_READY** (robot in STANDBY / not docked).
Empirically nailed: the *same* task returns 4 from STANDBY and 1 once CHARGED/docked.

### Validated room-clean request (live-confirmed, room 2 = Office)
`StartClean_Request{1: CleanTask}` with:
```
CleanTask  = {1: <active mapId>, 2: [CleanItem], 3: {} (TaskOption), 5: 3 (taskType)}
CleanItem  = {1: ZoneOption{1: 1 (zoneType=room), 2: <roomId>}, 2: CleanParam, 3: <order, 1-based>}
CleanParam = {1:5, 2:2, 3:1, 4:3, 5:1, 6:2, 8:2}   # app's values; semantics partly unknown
```
Wrapped wire bytes for room 2, mapId 2:
`0a20080212180a0408011002120e080510021801200328013002400218011a002803`
Active mapId comes from `map/get_map` field 2.1 (= 2 on this unit).

### Schemas
- `CleanTask{1:mapId, 2:items[CleanItem], 3:option TaskOption, 5:taskType, 8:excludedRoomIds}`
- `CleanItem{1:zone ZoneOption, 2:param CleanParam, 3:order}`; `ZoneOption{1:zoneType, 2:zoneId, 8:overlapLevel}`
- `CleanParam` named-ctor args (alphabetical, **field tags not yet mapped**): enableSmartMode,
  fanLevel, mode, mopHumidity, mopStrengthLevel, mopTime, overlapLevel, sweepMopSyncTime, sweepTime
- `CleanPlan{1:id, 2:mapId, 3:cleanMode, 7:performTimes, 8:order, 9:cleanAreaOptions[CleanAreaOption], 10:cleanParam}`
- `CleanAreaOption{1:zoneId, 2:cleanZoneType, 4:sweepAreaOption, 5:mopAreaOption, 6:sweepMopSync, 7:sweepThenMopAreaOption}`
- `SweepAreaOption{1:sweepFanLevel, 2:cleanCount}`; `MopAreaOption{1:mopStrengthLevel, 2:mopHumidityLevel, 3:cleanCount}`
- enums (CleanTask.pbenum.dart): FanLevel (6 values), MopHumidity, MopStrengthLevel,
  CleanMode, OverlapLevel (3), ZoneType, TaskType — **values not yet labelled**.

### Live room table (active map id = 2)
Named (field 3): 1 Laundry · 2 Office · 3 Main Bath · 4 Hallway · 5 Mudroom ·
6 Pool Cubby · 7 Pool Bath · 9 Music Room · 10 Entry.
Type-defaulted (unnamed, resolved by the #22 fix): 8 (sub_type 4) Kitchen ·
11 (sub_type 11) Study · 12 (sub_type 3) Living Room · 13 (sub_type 8) Dining Room.
(Note: room 9 returned result 2 in one test despite being valid — minor unexplained quirk.)

### ROOM_TYPE enum → name (authoritative; the #22 fix)
One shared app switch (`map_engine_i18n_configer.dart` over `MapBaseType.RoomType`,
16 values 0–15) drives all models:
`0 Room · 1 Master Bedroom · 2 Second Bedroom · 3 Living Room · 4 Kitchen · 5 Bathroom ·
6 Toilet · 7 Balcony · 8 Dining Room · 9 Cloak Room · 10 Corridor · 11 Study ·
12 Children's Room · 13 Recreation Room · 14 Utility Room · 15 Other`.

---

## Fixes (done, deployed live, validated)

**#22 room labels.** The integration's base `ROOM_TYPE_NAMES` was mis-derived from index
5 on; the per-product_key override was a band-aid for the same misalignment. Rewrote the
base to the shared app enum above; emptied the override map (kept as a hook). Validated
in production — HA showed a "rooms changed" remap and the names are correct (Study,
Dining Room, etc.).

**#25/#37 room clean.** Switched `start_rooms()` from `/clean/plan/start` to
`/clean/start_clean` with a real CleanTask; track the active `map_id` (`MapData.map_id`,
get_map field 2.1); added `CommandResult.NOT_READY=4` + a docked-readiness retry.
Generated request is byte-identical to a captured app clean; live room-2 clean confirmed
(robot targeted Office). Removed the dead `_build_room_clean_payload`; whole-house
`start()` (which uses `/clean/plan/start` + a default payload, and works) is unchanged.

Both changes are on `working` here and currently deployed to the live instance.

## Open RE / next features

- **CleanParam field semantics (blocks PR quality).** `_ROOM_CLEAN_PARAM` in
  `client.py` is an opaque captured blob `{1:5,2:2,3:1,4:3,5:1,6:2,8:2}`. Decode each tag
  via `clean_task_2_clean_plan_convert_util.dart` (it reads CleanParam fields and writes
  named SweepAreaOption/MopAreaOption fields) + the CleanParam BuilderInfo. Then label
  the enums (FanLevel, MopHumidity, MopStrengthLevel, CleanMode, OverlapLevel, ...).
- **Missing settings in the integration** (user wants these): mop water level, coverage /
  passes (clean count), clean **mode** (vacuum / mop / both / sweep-then-mop). Only fan
  power is exposed today. Decode how the app's settings UI
  (`set_clean_params_controller.dart`, `clean_task_util.dart`) builds these, then surface
  via HA (fan_speed already; mop level + mode + passes via select/number entities or
  clean_area params).

## How to work in this repo

- `nix develop` (or direnv via `.envrc`) → dev shell with python (websockets, bbpb,
  pyelftools, protobuf, …) + RE/build tools.
- `nix run .#disassemble` → pulls the XAPK + runs blutter into `re/build/blutter-out`
  (gitignored, recreatable). First run builds a Dart VM (slow, network). If auto-download
  fails, drop the XAPK at `re/build/narwal.xapk`.
- `nix run .#dogfood` → rsync `custom_components/narwal` to the live HA instance + restart.
  Override target with `NARWAL_DEPLOY_TARGET`; needs `$HASS_HOST`/`$HASS_TOKEN` (or restart
  manually).
- Live-test tools: `re/tools/` (run from the s2 host). `room_clean.py 2` is the validated
  room-clean tester.
- Commit policy: don't push without being asked. PRs go upstream as focused branches off
  `master` (one per issue), not the whole `working` branch.

---

## TODO

- [ ] **CleanParam field decode** — map tags 1–8 to fanLevel/mode/mopHumidity/mopStrengthLevel/
      mopTime/sweepTime/cleanCount/etc. via the convert util; replace the opaque
      `_ROOM_CLEAN_PARAM` blob with named, documented values. (PR blocker for #25/#37.)
- [ ] **Enum labels** — FanLevel(6), MopHumidity, MopStrengthLevel, CleanMode, OverlapLevel(3),
      ZoneType, TaskType.
- [ ] **New settings** — expose mop water level, coverage/passes, and clean mode
      (vacuum/mop/both) in the integration; wire each to the right CleanParam field.
- [ ] **Open PRs upstream** — #22 (room labels) and #25/#37 (room clean), as separate
      branches off `master`. Not yet pushed.
- [ ] **Secondary issue reports** — segment-change log spam (re-fires every poll);
      now-obsolete product_key override gap (subsumed by the #22 base fix).
- [ ] **Investigate room-9 quirk** — valid Music Room returned result 2 once; confirm
      whether some rooms/categories need different handling before relying on every room.
- [ ] **CleanParam request vs. readback** — confirm whether any captured fields are
      output-only; the readback task worked as a request once docked, but double-check
      across modes.
