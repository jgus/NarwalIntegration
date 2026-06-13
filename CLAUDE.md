# CLAUDE.md — narwal (working fork)

**Read [project_history.md](project_history.md) first.** It is the durable memory for
this project: the robot/environment, the RE'd protocol, what's fixed, what's open, and a
running TODO. Update it (and its TODO) as work progresses.

## What this is

A working fork of `sjmotew/NarwalIntegration` (Home Assistant integration for Narwal
vacuums). `origin` = `jgus/NarwalIntegration`, `upstream` = `sjmotew/NarwalIntegration`.
Our work is on **`working`**; upstream PRs are focused branches cut from `master`.

## Repo facts that bite

- **Two synced copies of the client**: top-level `narwal_client/` and
  `custom_components/narwal/narwal_client/`. Apply every code change to **both**.
- RE output and the APK live under `re/build/` (gitignored) — recreate with
  `nix run .#disassemble`. Live-test scripts are in `re/tools/`.

## Working here

- `nix develop` (or direnv; `.envrc` is `use flake`) → python (websockets, bbpb,
  pyelftools, protobuf, …) + RE/build tools.
- `nix run .#disassemble` → APK → blutter → `re/build/blutter-out`.
- `nix run .#dogfood` → deploy `custom_components/narwal` to the live HA instance + restart.
- **Run robot test tools from the s2 host**, not inside the HA container — the robot allows
  one WebSocket per client IP, and the integration already holds the container's.
- Robot/HA access: defaults baked into `re/tools/` scripts; HA API via `$HASS_HOST` /
  `$HASS_TOKEN`.

## Conventions

- **Don't `git push` or open PRs without being asked.** Local commits on `working` and
  temp branches are fine. Upstream PRs = one focused branch per issue off `master`.
- NixOS: never install globally; quote flake specs; `nix build` with
  `--option post-build-hook ""`; reference SOPS secrets by path only, never decrypt them.
- Comments: brief, one physical line per paragraph; say what a thing is, not who calls it.
- Python: idiomatic and reviewed for Pythonic quality (the maintainer-of-record here is
  not a Python specialist).
