#!/usr/bin/env python3
"""Extract protobuf field schemas from Blutter-disassembled .pb.dart files.

protobuf-dart builds each message's BuilderInfo by calling `BuilderInfo::<m>`
once per field. The tag number is the integer loaded immediately before the
field-name string (in r0+stack for generic a<T>()/pc(), or r2/r3 for the
specialized aOB/aOS/... helpers). We pair (int-before-name, name) and attribute
it to the next BuilderInfo:: call, capturing any submessage type seen nearby."""

from __future__ import annotations

import re
import sys
from pathlib import Path

CLASS_RE = re.compile(r"^\s*class (\w+) extends GeneratedMessage")
ENTER_I = re.compile(r"BuilderInfo _i\(\)")
# high-level annotation: `// 0xADDR: rN = VALUE`
REG_RE = re.compile(r"^\s*// 0x[0-9a-f]+: r\w+ = (.+?)\s*$")
INT_RE = re.compile(r"^(?:0x[0-9a-f]+|\d+)$")
STR_RE = re.compile(r'^"(.*)"$')
TYPEARG_RE = re.compile(r"^<(\w+)>$")
CALL_RE = re.compile(r"BuilderInfo::([A-Za-z]\w*)\b")
CLOSURE_RE = re.compile(r"=> (\w+)")

METHOD = {
    "aOS": "string", "aQS": "req string", "aOB": "bool", "aQB": "req bool",
    "aOM": "message", "aQM": "req message", "a": "scalar", "aInt64": "int64",
    "pc": "repeated message", "pPS": "repeated string", "p": "packed repeated",
    "e": "enum", "oo": "ONEOF", "m": "map<>", "aOF": "float", "aOD": "double",
}
PRIM = {"int", "String", "bool", "double", "Int64", "List"}


def parse(path: Path) -> list[str]:
    out: list[str] = []
    cls = None
    last_int = pend_num = pend_name = submsg = None
    for ln in path.read_text(errors="replace").splitlines():
        cm = CLASS_RE.match(ln)
        if cm:
            cls = cm.group(1)
            last_int = pend_num = pend_name = submsg = None
            out.append(f"\nmessage {cls} {{")
            continue
        if ENTER_I.search(ln):
            last_int = pend_num = pend_name = submsg = None
            continue
        rm = REG_RE.match(ln)
        if rm:
            v = rm.group(1)
            if INT_RE.match(v):
                last_int = int(v, 0)
            else:
                sm = STR_RE.match(v)
                if sm:
                    pend_name, pend_num = sm.group(1), last_int
                ta = TYPEARG_RE.match(v)
                if ta and ta.group(1) not in PRIM:
                    submsg = ta.group(1)
        cl = CLOSURE_RE.search(ln)
        if cl and cl.group(1) not in PRIM:
            submsg = cl.group(1)
        call = CALL_RE.search(ln)
        if call and cls:
            meth = call.group(1)
            if meth == "BuilderInfo":
                continue
            label = METHOD.get(meth, meth)
            num = pend_num if pend_num is not None else "?"
            name = pend_name or "-"
            ref = f" {submsg}" if submsg and ("message" in label or meth == "oo") else ""
            out.append(f"  {num:<4} {name:<26} {label}{ref}  ({meth})")
            pend_name = None
            if "message" in label:
                submsg = None
    if cls:
        out.append("}")
    return out


def main() -> None:
    for arg in sys.argv[1:]:
        print(f"\n========== {Path(arg).name} ==========")
        print("\n".join(parse(Path(arg))))


if __name__ == "__main__":
    main()
