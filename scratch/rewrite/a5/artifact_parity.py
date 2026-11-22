"""Compare source and source-free execution of the ported scenarios and reservoir example.

From the checkout, run `python scratch/rewrite/a5/artifact_parity.py`. Each fresh consumer starts
in an empty directory containing only the artifact and serialized run configuration. It may import
Napkin, but attempts to open scenario inputs, including package evidence and unit files, fail.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Case:
    entry: str
    run: str | None
    paths: tuple
    times: tuple
    edits: dict = field(default_factory=dict)
    required_starts: tuple = ()
    expected_path: tuple = ()


CASES = (
    Case('examples/reservoir', None, ('reservoir.water', 'reservoir.spilled'), (0, 40, 120)),
    Case(
        'scenarios/water_controls_wipe/variants/juneau',
        'delayed_none',
        ('unserved_volume', 'work_remaining', 'restored_share'),
        (0, 24, 220),
    ),
    Case(
        'scenarios/iv_fluid_shortage',
        'subpar',
        ('release_team.work_done', 'deliveries.state', 'resuscitation_reserve.held'),
        (0, 3, 4, 28, 32),
        {
            'manufacturer.containment_time': '2 h',
            'manufacturer.time_to_find': '24 h',
            'hospitals.start_delay': '0.5 h',
            'release_team.ordinary_work': '24 work_h',
            'release_team.pace': '8 work_h/h',
            'records.released_lot': 'NEEDS_CHECK',
        },
        ('release_team.restart_release', 'records.review_pending', 'manufacturer.discrepancy_confirmed'),
    ),
    Case(
        'scenarios/cyber_learning_loop',
        None,
        ('observations.pressure', 'defender_attention'),
        (0, 1, 2, 3, 4),
        {
            'observations.during': 5,
            'observations.later': 0.5,
            'observations.change_at': '1 h',
            'observations.duration': '2 h',
        },
        expected_path=('observations.pressure', (1, 5, 5, 0.5, 0.5)),
    ),
    Case(
        'scenarios/heat_wave_blackout',
        'standard',
        ('supply.resident_hours', 'incident.paused'),
        (0, 0.125, 0.25, 0.5, 0.75),
        {'incident.hold': True, 'incident.hold_at': '0.25 h', 'incident.hold_duration': '0.25 h'},
        ('incident.hold_begins',),
        ('incident.paused', (False, False, True, False, False)),
    ),
)


def observations(program, config, table, paths, times):
    import napkin

    record = napkin.run(program, config)
    if record.stop is not None or record.end != config.request.horizon:
        raise RuntimeError(f'run stopped at {record.end} of {config.request.horizon} h: {record.stop}')
    readings, definitions = [], {}
    for at in times:
        report = napkin.report(record, program, config, paths, [at], table=table)
        for value in report.values:
            if not isinstance(value.values[0], (int, float, str, bool)):
                raise ValueError(f'{value.path} at {at} h is unavailable: {value.values[0]!r}')
            credited = sorted({name for part in value.trail if part.exercised for name in part.records})
            readings.append([value.path, at, value.unit, value.values[0], credited])
        definitions.update({name: (kind, text) for name, kind, text in report.records})
    return {
        'readings': readings,
        'definitions': [[name, *definition] for name, definition in sorted(definitions.items())],
        'starts': [[e.t, e.owner] for e in record.entries('start')],
    }


def consume():
    denied = []

    def deny_sources(event, args):
        if event != 'open' or isinstance(args[0], int):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        if path.suffix == '.scn' or any(
            path.is_relative_to(ROOT / name) for name in ('scenarios', 'examples')
        ):
            denied.append(path)
            raise PermissionError(f'source read denied: {path}')

    sys.addaudithook(deny_sources)
    for probe in (ROOT / 'examples/reservoir/model.scn', ROOT / 'scenarios/water_controls_wipe/units.json'):
        try:
            probe.read_bytes()
        except PermissionError:
            continue
        raise AssertionError(f'the source-access control accepted {probe}')
    denied.clear()
    from napkin.program.artifact import load, value_of

    artifact = load('program.npk')
    config = value_of(Path('configuration').read_bytes())
    paths, times = json.load(sys.stdin)
    result = observations(artifact.program, config, artifact.table, paths, times)
    if denied:
        raise AssertionError(f'the artifact consumer attempted a source read: {denied}')
    print(json.dumps(result, allow_nan=False))


def compare(case):
    import napkin
    from napkin.engine import edits_for
    from napkin.program.canonical import value_bytes

    model = napkin.load_scenario(ROOT / case.entry)
    config = model.configure(case.run, edits=edits_for(model, {'set': case.edits}))
    config = replace(config, request=replace(config.request, horizon=case.times[-1]))
    expected = observations(model.program, config, model.table, case.paths, case.times)
    owners = [owner.split('#')[0] for _, owner in expected['starts']]
    for name in case.required_starts:
        if name not in owners:
            raise AssertionError(f'{case.entry}: missing intended transition {name}; observed {owners}')
    if case.expected_path:
        path, values = case.expected_path
        actual = tuple(row[3] for row in expected['readings'] if row[0] == path)
        if actual != values:
            raise AssertionError(f'{case.entry}: {path} was {actual}, expected {values}')

    with TemporaryDirectory(prefix='napkin-artifact-') as folder:
        target = Path(folder)
        (target / 'program.npk').write_bytes(model.artifact().data())
        (target / 'configuration').write_bytes(value_bytes(config))
        result = subprocess.run(
            [sys.executable, '-I', str(Path(__file__).resolve()), '--consumer'],
            cwd=folder,
            env={**os.environ, 'NAPKIN_STORE': 'off'},
            input=json.dumps([case.paths, case.times]),
            text=True,
            stdout=subprocess.PIPE,
            check=True,
            timeout=120,
        )
    actual = json.loads(result.stdout)
    for group in ('readings', 'definitions', 'starts'):
        if len(expected[group]) != len(actual[group]):
            raise AssertionError(
                f'{case.entry}: {group} count {len(actual[group])}, expected {len(expected[group])}'
            )
        for wanted, found in zip(expected[group], actual[group], strict=True):
            if wanted != found:
                raise AssertionError(f'{case.entry}: {group} expected {wanted!r}, got {found!r}')
    counts = len(actual['readings']), len(actual['starts'])
    print(f'{case.entry}: {counts[0]} readings with evidence, {counts[1]} ordered event starts', flush=True)
    return counts


def main():
    if sys.argv[1:] == ['--consumer']:
        consume()
    elif not sys.argv[1:]:
        os.environ['NAPKIN_STORE'] = 'off'
        counts = [compare(case) for case in CASES]
        print(
            f'{sum(r for r, _ in counts)} readings, {sum(s for _, s in counts)} ordered event starts matched'
        )
    else:
        raise SystemExit('usage: python scratch/rewrite/a5/artifact_parity.py')


if __name__ == '__main__':
    main()
