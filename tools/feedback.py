"""Run the report-only feedback check (`napkin.engine.feedback`) over the catalogue and print what a
modeller would see: python -m tools.feedback [--runs] [--json PATH].

Each flag is traced to the authored rules: the value that holds each switch, by its part's origin
(`Utility.delivery_rate`) with its file and line, the flows that carry each influence, and the
members where one shared rule applies. Flags of one shared rule are one warning. The check changes
nothing that a run does; this tool only reads and times it."""

import argparse
import collections
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from napkin import load_scenario  # noqa: E402
from napkin.engine import feedback  # noqa: E402
from napkin.engine.timeline import Plan  # noqa: E402
from napkin.engine.timeline.record import declaration  # noqa: E402
from tools import catalogue  # noqa: E402

SIGN = {1: 'raises', -1: 'lowers', 0: 'leaves'}


def _where(model, plan, name):
    """(origin, 'file:line', member) of an engine name, or (name, '', '')."""
    value = plan.values.get(name)
    key = value.key if value is not None else None
    if key is None:
        flow = plan.flows.get(name)
        key = getattr(plan.values.get(f'{name}.actual_rate'), 'key', None) if flow is not None else None
    if key is None:
        return name, '', ''
    try:
        part = declaration(model.program, key).part
        origin = part.origin
    except (KeyError, AttributeError):
        return name, '', key.owner
    try:
        location = model.table.location(origin)
        place = f'{Path(location.file).name}:{location.line}'
    except KeyError:
        place = ''
    return origin, place, key.owner


def _general(text, member):
    """A switch's text with its member's name written `this`, so that members of one rule agree."""
    return re.sub(rf'\b{re.escape(member)}\.', 'this.', text) if member else text


def _signs(signs):
    found = sorted(signs - {0})
    return (
        'raises' if found == [1] else 'lowers' if found == [-1] else 'raises or lowers' if found else 'leaves'
    )


def describe(model, plan, report):
    """The warnings of one plan: [(key, warning)], where the key names the authored rules."""
    found = []
    for part, circuit, reason in report.flagged:
        steps, rules = [], []
        edges = circuit[1] if circuit else []
        for edge in edges:
            origin, place, member = _where(model, plan, edge.source.owner)
            target_origin, _, target_member = _where(model, plan, edge.target.owner)
            flows = []
            for flow, through in edge.via:
                if flow == 'nested':
                    flows.append('its value, which the next condition reads')
                    continue
                flow_origin, flow_place, _ = _where(model, plan, flow)
                flows.append(
                    f'{flow_origin} ({flow_place}) into {through}' if flow_place else f'{flow} into {through}'
                )
            steps.append(
                {
                    'condition': _general(edge.source.text, member),
                    'rule': origin,
                    'line': place,
                    'member': member,
                    'effect': _signs(edge.signs),
                    'next': _general(edge.target.text, target_member),
                    'next rule': target_origin,
                    'through': sorted(set(flows))[:6],
                    'only in a shortage': edge.shortage,
                }
            )
            rules.append((origin, _general(edge.source.text, member)))
        key = (reason, tuple(sorted(set(rules))))
        found.append(
            (
                key,
                {
                    'reason': reason,
                    'switches': len(part),
                    'members': sorted({s['member'] for s in steps if s['member']}),
                    'chain': steps,
                },
            )
        )
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        '--runs', action='store_true', help='check every run of each model, not only its default'
    )
    parser.add_argument('--json', help='write the warnings and timings to this file')
    args = parser.parse_args()
    warnings, timing, cleared, runtime = {}, [], collections.Counter(), collections.Counter()
    where = collections.defaultdict(set)
    counts = collections.Counter()
    for owner, entry in catalogue.entries(catalogue.ROOT).items():
        started = time.perf_counter()
        model = load_scenario(str(entry))
        loaded = time.perf_counter() - started
        runs = [None, *(run.name for run in model.declared.runs)] if args.runs else [None]
        for run in runs:
            started = time.perf_counter()
            configuration = model.configuration if run is None else model.configure(run)
            plan = Plan.of(model.program, configuration)
            planned = time.perf_counter() - started
            started = time.perf_counter()
            report = feedback.check(plan)
            checked = time.perf_counter() - started
            label = owner if run is None else f'{owner}:{run}'
            timing.append((label, loaded if run is None else 0.0, planned, checked))
            counts['plans'] += 1
            counts['switches'] += len(report.switches)
            counts['kinks'] += sum(1 for s in report.switches if s.kind == feedback.KINK)
            counts['flagged sets'] += len(report.flagged)
            counts['cleared sets'] += len(report.cleared)
            for _, reason in report.cleared:
                cleared[reason.split(':')[0]] += 1
            runtime['kink owners'] += len(report.runtime)
            for key, warning in describe(model, plan, report):
                kept = warnings.setdefault(key, warning)
                kept['members'] = sorted(set(kept['members']) | set(warning['members']))
                where[key].add(label)
    print(f'# Feedback between switch choices: {counts["plans"]} plans of the catalogue\n')
    print(
        f'switches {counts["switches"]} (kinks {counts["kinks"]}); sets with a circuit: '
        f'{counts["flagged sets"]} flagged, {counts["cleared sets"]} cleared; '
        f'distinct warnings: {len(warnings)}'
    )
    print('cleared because:', dict(cleared))
    total_load = sum(t[1] for t in timing)
    total_plan = sum(t[2] for t in timing)
    total_check = sum(t[3] for t in timing)
    print(
        f'time: load {total_load:.2f} s, plan {total_plan:.2f} s, check {total_check:.2f} s '
        f'({100 * total_check / max(total_load + total_plan, 1e-9):.0f}% of load and plan)'
    )
    slowest = sorted(timing, key=lambda t: -t[3])[:5]
    print('slowest checks:', [(label, round(check, 2)) for label, _, _, check in slowest])
    for k, (key, warning) in enumerate(sorted(warnings.items(), key=lambda item: item[0]), 1):
        print(f'\n## Warning {k}: {warning["reason"]}')
        print(
            f'applies in {len(where[key])} plans; {len(warning["members"])} members: {", ".join(warning["members"][:30])}'
        )
        for step in warning['chain']:
            print(
                f'- `{step["condition"]}` in {step["rule"]} ({step["line"]}): its upper side '
                f'{step["effect"]} the gap of `{step["next"]}` in {step["next rule"]}'
                + (' (only when a store runs short)' if step['only in a shortage'] else '')
            )
            for through in step['through']:
                print(f'    through {through}')
    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    'counts': counts,
                    'cleared': cleared,
                    'timing': timing,
                    'warnings': [
                        {**warning, 'plans': sorted(where[key])} for key, warning in sorted(warnings.items())
                    ],
                },
                indent=1,
                default=str,
            )
        )


if __name__ == '__main__':
    main()
