"""Read pytest JUnit XML for the port corpus and enforce its seed and near-tie gates."""

import argparse
import collections
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def summarize(tier, files, full_suite=False):
    # Running this file as a script puts the audit folder on sys.path.
    if __package__ in (None, ''):
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from tests.engine.test_port_invariance import TRANSFORMS

    seen, affected = set(), collections.defaultdict(set)
    failures = []
    name = 'test_all_port_transforms' if tier == 'deep' else 'test_port_transform'
    limit = 2000 if tier == 'deep' else 300
    expected = {
        (seed, transform)
        for seed in range(limit)
        for transform in (TRANSFORMS if tier == 'deep' else (TRANSFORMS[seed % len(TRANSFORMS)],))
    }
    if full_suite and (tier != 'regular' or len(files) != 1):
        raise ValueError('the regular wall-time gate takes one complete four-worker pytest report')
    for path in files:
        xml = ET.parse(path)
        if full_suite:
            (suite,) = xml.iter('testsuite')
            seconds = float(suite.attrib['time'])
            print(f'Full regular suite: {seconds:.3f} s, budget 180 s')
            if not math.isfinite(seconds) or not 0 <= seconds <= 180:
                raise ValueError(f'full regular pytest time {seconds} is outside its 180-second budget')
            if int(suite.attrib['errors']) or int(suite.attrib['failures']):
                raise ValueError('full regular pytest run contains errors or failures')
        for case in xml.iter('testcase'):
            match = re.fullmatch(rf'{name}\[(\d+)(?:-([a-z_]+))?\]', case.get('name', ''))
            if not match:
                continue
            seed = int(match[1])
            if tier == 'deep' and match[2] is None:
                raise ValueError('deep coverage needs one reported result per seed and transformation')
            transform = match[2]
            if tier == 'regular':
                property_ = case.find("properties/property[@name='transform']")
                if property_ is None:
                    raise ValueError(f'regular seed {seed} is missing its recorded transformation')
                transform = property_.get('value')
            pair = seed, transform
            if pair in seen:
                raise ValueError(f'duplicate {tier} case {pair}')
            seen.add(pair)
            if any(case.find(kind) is not None for kind in ('failure', 'error', 'skipped')):
                failures.append(pair)
            for prop in case.findall('properties/property'):
                field = prop.get('name', '')
                if field.startswith('near-tie-'):
                    label = field.removeprefix('near-tie-')
                    affected[label].add(seed)
                    print(f'  seed {seed} {label}: {prop.get("value")}')
    distinct = set().union(*affected.values())
    seeds = {seed for seed, _ in seen}
    missing = expected - seen
    extra = seen - expected
    # Each original roundoff pair is checked twice, at both signs of the displacement.
    comparisons = sum(2 if transform == 'roundoff' else 1 for _, transform in seen)
    truncated = sum(map(len, affected.values()))
    print(f'{tier}: {len(seeds)}/{limit} seeds, {len(seen)}/{len(expected)} transformation cases, '
          f'{truncated}/{comparisons} transformed pairs truncated; {len(distinct)} seeds affected; '
          f'{dict(sorted((k, len(v)) for k,v in affected.items()))}')
    if failures or missing or extra:
        raise ValueError(f'{tier}: failures/skips {sorted(failures)[:20]}, missing {sorted(missing)[:20]}, '
                         f'unexpected {sorted(extra)[:20]}')
    if len(distinct) > limit // 100 or (tier == 'deep' and any(len(seeds) > 20 for seeds in affected.values())):
        raise ValueError(f'{tier}: near-tie frequency exceeds threshold; repair generator and rerun original seeds')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tier', choices=('regular', 'deep'))
    parser.add_argument('files', nargs='+')
    parser.add_argument(
        '--full-suite', action='store_true', help='check the complete four-worker regular suite against 180 s'
    )
    args = parser.parse_args()
    summarize(args.tier, args.files, args.full_suite)
