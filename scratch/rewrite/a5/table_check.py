#!/usr/bin/env python
"""Check that `migration-table.md` has a row for each key of `census.json`, used or never used.

    /home/user/napkin/.venv/bin/python table_check.py

A row covers the keys in backticks in its first column; a name that ends in `*` covers each key
that starts with it. Exit 1 when a key has no row or a row names a key that the census lacks.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main():
    census = json.loads((HERE / 'census.json').read_text(encoding='utf-8'))
    keys = set(census['keys']) | set(census['absent'])
    rows = []
    for line in (HERE / 'migration-table.md').read_text(encoding='utf-8').splitlines():
        if line.startswith('| `'):
            first = line.split(' | ')[0]
            rows.append((re.findall(r'`([^`]+)`', first), line))
    covered, bad = {}, []
    for patterns, line in rows:
        for pattern in patterns:
            if pattern.endswith('*'):
                hit = {k for k in keys if k.startswith(pattern[:-1])}
            else:
                hit = {pattern} & keys
            if not hit:
                bad.append(pattern)
            for k in hit:
                covered.setdefault(k, pattern)
    missing = sorted(keys - set(covered))
    print(f'{len(rows)} rows, {len(keys)} keys ({len(census["absent"])} never used), {len(covered)} covered')
    for k in missing:
        print(f'  NO ROW: {k}')
    for p in bad:
        print(f'  ROW NAMES NO KEY: {p}')
    return 1 if missing or bad else 0


if __name__ == '__main__':
    sys.exit(main())
