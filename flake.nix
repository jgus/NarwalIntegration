{
  description = "Narwal Flow 2 Home Assistant integration — dev shell + reverse-engineering tooling";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      py = pkgs.python3;

      # blackboxprotobuf (PyPI "bbpb") — not in nixpkgs; the integration and the
      # RE test tools decode/encode the robot's schema-less protobuf with it.
      bbpb = py.pkgs.buildPythonPackage rec {
        pname = "bbpb";
        version = "1.4.2";
        pyproject = true;
        src = pkgs.fetchPypi {
          inherit pname version;
          sha256 = "03446991bc500cfc9dd2049e6cc9489979e157c5ecb793e27936ab3d579d3496";
        };
        build-system = [ py.pkgs.poetry-core ];
        propagatedBuildInputs = with py.pkgs; [ six protobuf ];
        doCheck = false;
        pythonImportsCheck = [ "blackboxprotobuf" ];
      };

      pythonEnv = py.withPackages (ps: [
        ps.websockets   # robot LAN WebSocket
        ps.requests     # APK fetch / misc
        ps.pyelftools   # blutter dep
        ps.protobuf
        ps.pillow       # integration dep (map images)
        ps.aiohttp
        ps.pytest
        ps.pytest-asyncio   # async test suite (asyncio_mode=auto in pyproject.toml)
        bbpb
      ]);

      # blutter #includes <capstone.h>, but nixpkgs puts it at include/capstone/capstone.h
      capstoneInclude = "${pkgs.lib.getDev pkgs.capstone}/include/capstone";

      # Tools for the RE pipeline (APK extract + blutter build) and general work.
      reTools = with pkgs; [
        git gh jq ripgrep rsync curl
        unzip p7zip
        cmake ninja gcc pkg-config icu capstone
      ];

      disassemble = pkgs.writeShellScriptBin "narwal-disassemble" ''
        export PATH=${pkgs.lib.makeBinPath ([ pythonEnv ] ++ reTools)}:$PATH
        export CPATH=${capstoneInclude}''${CPATH:+:$CPATH}
        set -euo pipefail

        # Pulls the Narwal app XAPK and runs blutter to recover the Dart/Flutter
        # AOT source. Output and intermediates live under re/build (gitignored),
        # so this is fully recreatable. ~GBs + a Dart VM build on first run.
        PKG=com.narwal.pita_global
        ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
        BUILD="''${NARWAL_RE_BUILD:-$ROOT/re/build}"
        XAPK="''${NARWAL_XAPK:-$BUILD/narwal.xapk}"
        OUT="$BUILD/blutter-out"
        mkdir -p "$BUILD"

        if [ ! -f "$XAPK" ]; then
          if [ -f /service/home-assistant/tmp/narwal.xapk ]; then
            echo ">> using cached XAPK from /service/home-assistant/tmp/narwal.xapk"
            cp /service/home-assistant/tmp/narwal.xapk "$XAPK"
          else
            echo ">> fetching $PKG XAPK from apkpure"
            # apkpure's download endpoint; brittle — if it fails, drop the XAPK at $XAPK manually.
            curl -fL --retry 3 -A 'Mozilla/5.0' \
              "https://d.apkpure.com/b/XAPK/$PKG?version=latest" -o "$XAPK" || {
                echo "!! auto-download failed. Manually fetch the $PKG XAPK"
                echo "   (e.g. https://apkpure.com/p/$PKG) and save it to: $XAPK"
                exit 1
              }
          fi
        fi

        echo ">> extracting arm64 split + native libs"
        WORK="$BUILD/extract"; rm -rf "$WORK"; mkdir -p "$WORK"
        unzip -o "$XAPK" 'config.arm64_v8a.apk' -d "$WORK" >/dev/null
        unzip -o "$WORK/config.arm64_v8a.apk" 'lib/arm64-v8a/*' -d "$WORK/split" >/dev/null
        LIBDIR="$BUILD/lib"; rm -rf "$LIBDIR"; mkdir -p "$LIBDIR"
        cp "$WORK/split/lib/arm64-v8a/libapp.so" "$LIBDIR/"
        cp "$WORK/split/lib/arm64-v8a/libflutter.so" "$LIBDIR/"

        echo ">> ensuring blutter checkout"
        BLUTTER="$BUILD/blutter"
        if [ ! -d "$BLUTTER/.git" ]; then
          git clone --depth 1 https://github.com/worawit/blutter "$BLUTTER"
        fi

        echo ">> running blutter (builds a matching Dart VM on first run)"
        rm -rf "$OUT"
        python3 "$BLUTTER/blutter.py" "$LIBDIR" "$OUT"
        echo ">> done: $OUT"
      '';

      dogfood = pkgs.writeShellScriptBin "narwal-dogfood" ''
        export PATH=${pkgs.lib.makeBinPath [ pkgs.rsync pkgs.curl ]}:$PATH
        set -euo pipefail

        # Deploys this repo's custom_components/narwal to the live HA instance and
        # restarts HA so the new code is imported. Target must be writable.
        ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
        SRC="$ROOT/custom_components/narwal"
        TARGET="''${NARWAL_DEPLOY_TARGET:-/service/home-assistant/custom_components/narwal}"

        [ -d "$SRC" ] || { echo "!! missing $SRC"; exit 1; }
        [ -d "$TARGET" ] || { echo "!! deploy target not found: $TARGET"; exit 1; }
        [ -w "$TARGET" ] || { echo "!! deploy target not writable: $TARGET (fix ownership/perms)"; exit 1; }

        echo ">> deploying $SRC -> $TARGET"
        # Target is group-writable but owned by another user (ha:ha), so we can write
        # content but cannot chown/chgrp/chmod the existing dirs or set their times.
        # Skip all that metadata; new files take the umask default (022 -> 644, which
        # HA can read). Otherwise rsync exits non-zero and set -e skips the restart.
        rsync -a --no-owner --no-group --no-perms --omit-dir-times --delete \
          --exclude='__pycache__' --exclude='*.pyc' "$SRC/" "$TARGET/"

        if [ -n "''${HASS_HOST:-}" ] && [ -n "''${HASS_TOKEN:-}" ]; then
          echo ">> restarting HA via API"
          code=$(curl -s -m 30 -o /dev/null -w '%{http_code}' -X POST \
            -H "Authorization: Bearer $HASS_TOKEN" -H 'Content-Type: application/json' \
            "$HASS_HOST/api/services/homeassistant/restart" -d '{}' || true)
          if [ "$code" = "200" ]; then
            echo ">> restart requested OK"
          else
            echo "!! restart API returned '$code'. Restart manually: podman restart home-assistant"
          fi
        else
          echo ">> set HASS_HOST/HASS_TOKEN to auto-restart, or: podman restart home-assistant"
        fi
      '';
    in {
      packages.${system} = {
        inherit bbpb;
        default = pythonEnv;
      };

      devShells.${system}.default = pkgs.mkShell {
        packages = [ pythonEnv ] ++ reTools;
        env.CPATH = capstoneInclude;
        shellHook = ''
          echo "narwal dev shell — see project_history.md"
          echo "  nix run .#disassemble   pull APK + blutter -> re/build/blutter-out (gitignored)"
          echo "  nix run .#dogfood       deploy custom_components/narwal to live HA + restart"
        '';
      };

      apps.${system} = {
        disassemble = { type = "app"; program = "${disassemble}/bin/narwal-disassemble"; };
        dogfood = { type = "app"; program = "${dogfood}/bin/narwal-dogfood"; };
        default = self.apps.${system}.dogfood;
      };
    };
}
