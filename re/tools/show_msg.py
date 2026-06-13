#!/usr/bin/env python3
"""Print named message blocks from SCHEMA.txt."""
import sys
from pathlib import Path

want = set(sys.argv[1:])
block, name, printing = [], None, False
for ln in Path("/tmp/blutter-out/SCHEMA.txt").read_text().splitlines():
    if ln.startswith("message "):
        name = ln.split()[1]
        printing = name in want
    if printing:
        print(ln)
    if ln == "}":
        printing = False
