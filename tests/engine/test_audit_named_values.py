"""Read, report and serialize each kind of value at the times its definition holds."""

from dataclasses import replace

import pytest

from napkin.engine import read, run
from napkin.engine.report import report
from napkin.engine.timeline import Plan, Run
from napkin.model.compile import load_scenario
from napkin.program.checkpoint import Breakpoint, dumps, loads
from napkin.program.record import Key, Unavailable
from tests.commands.call import UNITS, napkin, package


def fixture(tmp_path, text):
    folder = package(tmp_path, 'scenario "Audit"\n    horizon 4 h\n' + text, {'L': UNITS['L']})
    model = load_scenario(folder / 'model.scn')
    return model, folder


@pytest.mark.parametrize('target', ['pipe.capacity', 'water.outflow.capacity'])
@pytest.mark.parametrize('initial', [None, 5])
def test_report_follows_a_capacity_first_set_at_hour_one(tmp_path, capsys, target, initial):
    setting = '' if initial is None else f'        capacity = {initial} L/h\n'
    outflow = (
        setting.replace('capacity', 'outflow.capacity') if setting and target.startswith('water') else ''
    )
    flow_cap = setting if target.startswith('pipe') else ''
    model, folder = fixture(
        tmp_path,
        f"""
plant:
    water: L = 10 L in [0 L,]
{outflow}    flow pipe: this.water -> SINK
        request = 2 L/h
{flow_cap}    change_cap = event():
        after 1 h:
            this.{target} = 1 L/h

plant.change_cap.start()
""",
    )
    path = f'plant.{target}'
    times = [0, 1, 2]
    for everything in (True, False):
        key = Key('plant', tuple(target.split('.')))
        config = replace(
            model.configuration,
            request=replace(
                model.configuration.request, everything=everything, keys=() if everything else (key,)
            ),
        )
        record = run(model.program, config)
        assert record.failure is None
        (value,) = report(record, model.program, config, [path], times).values
        assert value.values[1:] == (1, 1)
        if initial is None:
            assert isinstance(value.values[0], Unavailable) and 'no ceiling' in value.values[0].reason
        else:
            assert value.values[0] == initial
    flags = ['--value', path, '--at', '2h']
    assert napkin(capsys, 'run', folder, *flags, '--json').doc['values'][path]['values'] == [1]
    output = napkin(capsys, 'run', folder, *flags)
    assert output.code == 0 and '1' in output.out.splitlines()[-1].split()


OCCURRENCE = """
plant:
    measured: L = 1 L @weighed
    fallback: L = 9 L @guess
    use_measurement: bool = true
    job = event():
        sample = formula(this.measured if this.use_measurement else this.fallback)
        after 0.5 h
    schedule = event():
        after 1.5 h:
            this.job.start()
        after 1 h:
            this.use_measurement = false
            this.measured = 5 L

plant.schedule.start()

record weighed: source "The measured amount."
record guess: assumption "A fallback estimate."
"""


def test_report_preserves_occurrence_lifecycle_values_and_units(tmp_path, capsys):
    model, folder = fixture(tmp_path, OCCURRENCE)
    paths = [f'plant.job#0.{name}' for name in ('started', 'active', 'done')]
    record = run(model.program, model.configuration)
    assert record.failure is None
    times = (1.5, 2, 3)
    for values in (
        read(record, model.program, paths, times),
        report(record, model.program, model.configuration, paths, times).values,
    ):
        assert [(v.unit, v.values) for v in values] == [
            ('h', (1.5, 1.5, 1.5)),
            ('', (True, False, False)),
            ('', (False, True, True)),
        ]
    for path, expected in zip(paths, (1.5, False, True)):
        text = napkin(capsys, 'run', folder, '--value', path, '--at', '2h')
        assert text.code == 0 and str(expected).lower() in text.out.lower()
        assert napkin(capsys, 'run', folder, '--value', path, '--at', '2h', '--json').doc['values'][path][
            'values'
        ] == [expected]


@pytest.mark.parametrize('everything', [True, False])
def test_frozen_formula_keeps_its_finish_time_evidence(tmp_path, everything):
    model, _ = fixture(tmp_path, OCCURRENCE)
    path = 'plant.job#0.sample'
    config = replace(
        model.configuration,
        request=replace(
            model.configuration.request,
            everything=everything,
            keys=() if everything else (Key('plant.job#0', ('sample',)),),
        ),
    )
    record = run(model.program, config)
    assert record.failure is None
    machine = Run(Plan.of(model.program, config), (Breakpoint('plant.schedule.step[1]'),))
    checkpoint = machine.run()
    resumed = Run.restored(Plan.of(model.program, config), loads(dumps(checkpoint))).resume()
    for held, time in [(record, 1.75), (record, 2), (record, 3), (resumed, 3)]:
        (value,) = report(held, model.program, config, [path], [time], model=model.declared).values
        assert value.values == (1,)
        evidence = {e.origin: e for e in value.trail}
        assert evidence['plant.measured'].exercised is True
        assert evidence['plant.fallback'].exercised is not True


def test_live_and_frozen_reports_at_the_same_time_follow_their_own_reads(tmp_path):
    text = OCCURRENCE.replace(
        '    job = event():\n        sample = formula(this.measured if this.use_measurement else this.fallback)',
        '    selected = formula(this.measured if this.use_measurement else this.fallback)\n'
        '    job = event():\n        sample = formula(this.selected)',
    ).replace('        after 1 h:', '        after 0.5 h\n        after 0 h:')
    model, _ = fixture(tmp_path, text)
    result = run(model.program, model.configuration)
    assert result.failure is None
    # Both paths visit plant.selected at 2 h. The occurrence finished before the switch in
    # the next round at that same time. The live reader follows the new branch.
    paths = ['plant.selected', 'plant.job#0.sample']
    for asked in (paths, paths[::-1]):
        shown = report(result, model.program, model.configuration, asked, [2], model=model.declared)
        for name, reading in zip(asked, shown.values, strict=True):
            live = name == 'plant.selected'
            assert reading.values == ((9,) if live else (1,))
            evidence = {each.origin: each.exercised for each in reading.trail}
            assert evidence['plant.measured'] is (not live)
            assert evidence['plant.fallback'] is live
