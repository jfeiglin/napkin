"""Read pytest JUnit XML for the port corpus and enforce its seed and near-tie gates."""

import argparse
import collections
import re
import xml.etree.ElementTree as ET


def summarize(tier, files):
    seen, affected = set(), collections.defaultdict(set)
    failures = []
    name = 'test_all_port_transforms' if tier == 'deep' else 'test_port_transform'
    limit = 2000 if tier == 'deep' else 300
    for path in files:
        for case in ET.parse(path).iter('testcase'):
            match = re.fullmatch(rf'{name}\[(\d+)\]', case.get('name', ''))
            if not match:
                continue
            seed = int(match[1])
            if seed in seen:
                raise ValueError(f'duplicate {tier} seed {seed}')
            seen.add(seed)
            if any(case.find(kind) is not None for kind in ('failure', 'error', 'skipped')):
                failures.append(seed)
            for prop in case.findall('properties/property'):
                field = prop.get('name', '')
                if field.startswith('near-tie-'):
                    transform = field.removeprefix('near-tie-')
                    affected[transform].add(seed)
                    print(f'  seed {seed} {transform}: {prop.get("value")}')
    distinct = set().union(*affected.values())
    missing = set(range(limit)) - seen
    comparisons = len(seen) * (8 if tier == 'deep' else 1)
    truncated = sum(map(len, affected.values()))
    print(f'{tier}: {len(seen)}/{limit} seeds, {truncated}/{comparisons} transformed pairs truncated; '
          f'{len(distinct)}/{len(seen)} seeds affected; {dict(sorted((k, len(v)) for k,v in affected.items()))}')
    if failures or missing or seen != set(range(limit)):
        raise ValueError(f'{tier}: failures/skips {sorted(failures)[:20]}, missing {sorted(missing)[:20]}')
    if len(distinct) > limit // 100 or (tier == 'deep' and any(len(seeds) > 20 for seeds in affected.values())):
        raise ValueError(f'{tier}: near-tie frequency exceeds threshold; repair generator and rerun original seeds')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tier', choices=('regular', 'deep'))
    parser.add_argument('files', nargs='+')
    args = parser.parse_args()
    summarize(args.tier, args.files)
