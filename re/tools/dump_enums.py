#!/usr/bin/env python3
"""Extract every ProtobufEnum's value->name table from blutter's pp.txt.

Each enum constant renders as:
    [pp+0x..] Obj!<EnumType>@<addr> : {
      Super!ProtobufEnum : {
        off_8: int(0xN),
        off_10: "NAME"
      }
    }
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

PP = Path(sys.argv[1] if len(sys.argv) > 1 else
          "/home/josh/git/narwal/re/build/blutter-out/pp.txt")

obj_re = re.compile(r"^\[pp\+0x[0-9a-f]+\] Obj!([A-Za-z0-9_]+)@[0-9a-f]+ : \{")
val_re = re.compile(r"off_8: int\((0x[0-9a-f]+|\d+)\)")
name_re = re.compile(r'off_10: "([^"]*)"')

enums: dict[str, dict[int, str]] = defaultdict(dict)
lines = PP.read_text(errors="replace").splitlines()
i = 0
while i < len(lines):
    m = obj_re.match(lines[i])
    if m and i + 1 < len(lines) and "Super!ProtobufEnum" in lines[i + 1]:
        etype = m.group(1)
        val = name = None
        for j in range(i + 2, min(i + 6, len(lines))):
            vm = val_re.search(lines[j])
            nm = name_re.search(lines[j])
            if vm:
                val = int(vm.group(1), 0)
            if nm:
                name = nm.group(1)
        if val is not None and name:
            enums[etype][val] = name
    i += 1

want = set(a.lower() for a in sys.argv[2:])
for etype in sorted(enums):
    if want and not any(w in etype.lower() for w in want):
        continue
    table = enums[etype]
    print(f"\n{etype}  ({len(table)} values)")
    for v in sorted(table):
        print(f"  {v:>3} = {table[v]}")
print(f"\n[{len(enums)} enums total]", file=sys.stderr)
