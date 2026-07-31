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

### Map fetch on FW v01.08.01 (gotcha)
`map/get_map`, `map/get_matched_map`, `map/get_editable_map` with an **empty** payload all
return result=2 (NOT_APPLICABLE) on this firmware. The working paths:
- `map/get_all_reduced_maps` (no args) → all maps incl. rooms, but **no raster** (thumbnails).
- `map/get_editable_map` with `{1: mapId}` → **full map: raster + rooms + dims** (the fix).
`client.get_map()` now: try `get_map`; if no rooms, resolve active map id (base_status f30,
else from reduced-maps) and fetch `get_editable_map`. This surfaced after an HA restart cleared
the in-memory map cache that had been hiding the get_map failure (the map code itself was unchanged).

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
- **Reading proto field types from blutter:** the field NAME + TAG come from the `_i()`
  BuilderInfo, but the Dart `<double>` TypeArguments does NOT distinguish float32 from
  float64 (Dart has only `double`). The wire type is the `PbFieldType` int passed to
  `BuilderInfo::a` (the `mov x0,#0xNNN` after the name string): 0x80=double, 0x100=float32,
  0x200=enum, 0x800=int32, 0x1000=int64, 0x8000=uint32, 0x40=string, 0x200000=message.
  Both `batteryPercentage` and `coveredArea` are 0x100 (float32) → decode with `_to_float32`.
  No audited field is a true 0x80 double.
- `WorkingStatus` (status/working_status broadcast): `{1:workingProgress f32, 2:coveredArea
  f32 (m²), 3:timeConsuming s, 4:remainedTime s, 5:roomCleanedTimes[], 6:cleaningZoneId,
  7:taskExtra str, 8:dryingTime, 9:totalDryingTime, 10:dryingBagTime, 11:totalDryingBagTime,
  12:dryStationBagTime, 13:totalDryStationBagTime (18000=5h — the old "1.8 m²" bug),
  14:stationBagSterilizationTime, 15:total…, 16:dustBagDetectTime, 17:total…,
  18:dryMopWorkingStatus, 19:dryDustBagWorkingStatus, 20:videoCruise, 21:searchPet,
  22:waitUser, 23:cleanTaskRoomParamChangeTimestamp i64}`. Area sensor reads field 2.
- `RobotBaseStatus` (status/robot_base_status broadcast) — key fields, several live-validated
  on dock: `1:errorCode[] (empty=ok), 2:batteryPercentage f32, 3:robotTaskStatus{1:task,
  2:pauseStatus,7:returning,10:recall,11:charging,12:washAndDry}, 5:supplyDrainModule,
  11:stationContactType, 12:detergentState, 13:bindedUuid str, 15:terminateReason,
  20:dustBoxState, 21:dustBagState, 23:cleanWaterTankState, 24:sewageTankState, 25:statusCodes,
  26:fanLevel(active), 29:mopHumidity(active), 30:mapId, 35:stationBagHealthScore f32 %,
  36:stationBagHealthResetTime epoch, 38:curingAgentConsumptionPercent, 39:stationBagStatus,
  40:heavyDetergentStatus, 41:heavyDetergentRemainPercent, 44:hasStation, 45:isRobotAtOrigin,
  47:chargingStatus, 49:batteryCooling, 50:ambientLightStatus}`. Most state fields are enums
  whose value→label tables are not yet decoded. Capture: `re/tools/base_status_probe.py`.
  Audit fixed mislabels: field 13 was `session_id` (it's bindedUuid), 36 was `timestamp`
  (stationBagHealthResetTime), 38 was `battery_health "always 100"` (curingAgentConsumptionPercent).
  Added sensors: dust bag health (f35), detergent remaining (f41), error/problem (f1).
- **Error detail**: base_status f1 `ErrorCode` = `{1:identityCode, 2:level(uint32), 3:debugDetail str}`,
  repeated; empty `{}` = no fault. There is NO local code→text table — the app opens a web help
  page (`goHelpCenterByCode` → `help.narwal.com/...?code=<n>&lang=`; base is a runtime i18n value).
  The error sensor exposes `codes`/`level`/`detail` + a best-effort `help_url` (template inferred,
  in const `ERROR_HELP_URL_TEMPLATE` — correct if a real fault opens a different path).
- **Last clean result**: base_status f15 `terminateReason` = `TaskResult` enum (live 1=NORMAL_END).
  Result codes appear stable across FW (unlike f3.1/f47). Sensor `last_clean_result`.
- **Consumables**: per-part life % is CLOUD-only (`supportConsumablesOnCloud`). LAN
  `consumable/get_consumable_info` → `{1:ConsumableInfoPayload{1:maintainItems[], 2:replaceItems[]}}`
  = alert lists only (enums in re/ENUMS.md). Queried (not broadcast); coordinator polls every ~30 min.
  Sensors `maintenance_required` / `replacement_required` (item names in attributes).
- `OTAUpgradeStatus` (upgrade/upgrade_status): `1:type, 2:status, 3:progress, 4:stage,
  5:errorCode, 6:detailErrorCode, 7:currentVersion str, 8:targetVersion str`. Was reading
  f4 (stage) as status; corrected to f2 status + f4 stage.
- `DownloadStatus` (status/download_status, voice/timbre pack): `1:type, 2:progress, 3:state,
  4:errorCode, 5:language, 6:timbreId`. Was reading f1 (type) as status; corrected to f3 state.

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
Ordering proven beyond switch order (2026-07-30, for the PR #48 revert): blutter's
`pp.txt` pool dump (lines ~48138–48250) shows each `RoomType` instance's
`ProtobufEnum.value` (`off_8`) + proto name (`off_10`) — e.g. 11=`ROOM_TYPE_STUDY`→
`map_room_name_study_room`. Proto names use master's vocabulary at different ints
(`ROOM_TYPE_SHOWER_ROOM`=5→"Bathroom", `ROOM_TYPE_UTILITY_ROOM`=14→"Storage room"),
which is what misled master; the en-US.json JSON key order is also not enum order.

### Room clean order (app/cloud-side — not exposed on the LAN)
The app's configured whole-house clean order is **not readable over the local protocol**.
Checked exhaustively (2026-06): reduced map and full `get_editable_map` (rooms carry only
id/sub_type/name/category; `editConfig` is `{1:50}`); `cur_plan`/`plan/get`; and the order
topics — `/clean/update_clean_order` and `/map/updateTaskOrder` both live in
`sort_shortcut_task_requester.dart`, i.e. they reorder **scheduled shortcut tasks**, not the
room sequence. The app holds the order app/cloud-side and sends rooms pre-sorted; the robot
just executes the `CleanTask`'s per-item order (`CleanItem` field 3, live-confirmed not
reordered). So **HA must own room ordering** — see the in-HA ordering TODO.

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
(robot targeted Office). Removed the dead `_build_room_clean_payload`.

**Whole-house start.** `async_start` used `/clean/plan/start` (StartWithPlan), which replays
the saved current plan — i.e. the last room selection — so a whole-house Start re-ran the
previous room-subset clean. Now enumerates every cleanable room and cleans via `start_rooms`
(`/clean/start_clean`), falling back to the saved-plan `start()` only when no map rooms are
known. Live-confirmed kicking off an all-rooms clean. Commit `766909e` on `feat/clean-settings`
(needs that branch's `clean_settings`), merged to `working`. Cleans in **map order**, not the
app's custom order — see the room-clean-order note and the in-HA ordering TODO.

These changes are on `working` here and currently deployed to the live instance.

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
- [x] **Enum labels** — DONE. Decoded all 225 enums (names survive in pp.txt's constant pool
      even though `_omitEnumNames` stripped them from the pbenum). Tables in [ENUMS.md](re/ENUMS.md),
      regen with `re/tools/dump_enums.py`. Caveat: value 1 (healthy state) is omitted for some
      tank/bag enums; f47 chargingStatus decodes to {0,5} but live=3 (app/FW mismatch).
- [x] **Station problem sensors** — DONE. clean-water/sewage tank, dust box/bag, station bag
      (f23/24/20/21/39) as `problem` binary_sensors, gated on field presence; error (f1). Plus
      dust-bag health (f35) and detergent (f41) % sensors.
- [ ] **Remaining base_status sensors** — charging status (f47, blocked on the FW mismatch
      above — validate live across charge cycles before trusting), active fan/water (f26/29 →
      let vacuum fan_speed / water select reflect live state, not just pending).
- [ ] **Cleaning-session sensors** — progress % (working_status f1, validate 0..1 vs 0..100),
      time remaining (f4) — only populated during a clean; capture with `re/tools/area_probe.py`.
      Also confirm coveredArea (f2) units against a known-area clean.
- [ ] **True battery health** — `info/get_battery_info` (f8 healthState, f2 chargeCycleCount,
      f5/6/7 temp/voltage/current). Needs a new periodic coordinator query; units unvalidated.
- [ ] **Per-clean history** — `report/clean_report` (area/duration/result/error, persists after
      a clean ends); confirm push-vs-query delivery via a live capture on s2.
- [ ] **New settings** — expose mop water level, coverage/passes, and clean mode
      (vacuum/mop/both) in the integration; wire each to the right CleanParam field.
- [ ] **In-HA room ordering** — HA has no native whole-house clean-order concept (Segment =
      `{id,name,group}`, no order field; `vacuum.clean_area`'s area selector is `reorder: true`
      and preserves order into `async_clean_segments`, but that's the on-demand action, not the
      Start button). Deployed HA 2026.5.4 (Segment API since 2026.3). Plan: a config-entry
      OptionsFlow ordered room list; `vacuum._all_room_ids()` builds the whole-house list from
      it (∩ known rooms, map-order fallback); reuse the segment-change repair flow for stale ids.
      The wire already carries order (`CleanItem` field 3) and the robot honors it, so this
      changes the physical clean order. Stacks on `766909e` (`feat/clean-settings`).
- [ ] **Open PRs upstream** — #22 (room labels) and #25/#37 (room clean), as separate
      branches off `master`. Room labels went up as **upstream PR #48**: merged, then
      reverted pre-release (`8f6d50f`) — maintainer confirmed the strings but wanted the
      decompiled `roomTypei18nKey` body to prove ordering at 8–11 (comment 5133778732).
      Evidence produced 2026-07-30 (see the pool-dump note in the ROOM_TYPE section);
      once posted, maintainer relands in 1.0.2.
- [ ] **Secondary issue reports** — segment-change log spam (re-fires every poll);
      now-obsolete product_key override gap (subsumed by the #22 base fix).
- [ ] **Investigate room-9 quirk** — valid Music Room returned result 2 once; confirm
      whether some rooms/categories need different handling before relying on every room.
- [ ] **CleanParam request vs. readback** — confirm whether any captured fields are
      output-only; the readback task worked as a request once docked, but double-check
      across modes.
