"""Coverage of the explicit-time rate check, through definition changes and cutoffs."""

import json
from bisect import bisect_left
from dataclasses import replace

from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, dumps, loads
from napkin.program.record import Key

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}

SCOPE = """scenario "Rate inputs at installation"
    horizon 4 h
Table:
    input hour: h = 0 h
    input pace: L/h = 1 L/h
first: Table
yard:
    input factor = 2
    setting = 1
    source: L = 30 L
    sink: L = 0 L
    clock_rate = formula(this.factor * (t / (1 h)) * 1 L/h)
    mixed = formula(this.setting * this.clock_rate)
    flow pipe: this.source -> this.sink
        request = formula(this.clock_rate)
        capacity = formula(this.clock_rate + 1 L/h)
    flow tabulated: SOURCE -> this.sink
        request = formula(Table.instances.by(hour).at(t).pace)
    flow held: SOURCE -> this.sink
        request = formula(this.setting * 1 L/h)
    work = event():
        flow extra: SOURCE -> this.sink
            request = formula(this.mixed)
        after 0.5 h
    controls = event():
        after 1 h:
            this.pipe.request = formula(this.mixed)
            this.work.start()
        after 1 h:
            this.pipe.request = formula(this.clock_rate)
        after 1 h
yard.controls.start()
"""


def test_scope_covers_only_clock_settings_and_counts_distinct_omissions():
    model = compile_text(SCOPE, UNITS)
    live = Run(Plan.of(model.program, model.configuration))
    record = live.run()
    assert record.failure is None
    assert dict(record.manifest.unchecked_time_rates) == {
        'yard.tabulated.request': 0,
        'yard.pipe.request': 1,
        'yard.work#0.extra.request': 1,
    }
    assert 'excluded 3 time-dependent settings' in record.rate_guard_note
    assert {name: set(stocks) for name, stocks in live.ways.instance_of('yard.pipe').clock_rates.items()} == {
        'yard.pipe.request': {'yard.sink', 'yard.source'},
        'yard.pipe.capacity': {'yard.sink', 'yard.source'},
    }


def test_budget_cutoff_excludes_a_rate_first_installed_at_that_time():
    model = compile_text(SCOPE, UNITS)
    key = Key('yard', ('pipe', 'request'))
    selected = replace(model.configuration.request, everything=False, keys=(key,))
    configuration = replace(model.configuration, request=selected)
    record = Run(Plan.of(model.program, configuration)).run()
    pipe = record.history(key)
    starts = sorted(row.t for row in pipe.pieces[: pipe.charged_pieces()])
    budget = bisect_left(starts, 1)
    assert starts[budget] == 1
    small = replace(configuration, request=replace(selected, pieces=budget))
    limited = Run(Plan.of(model.program, small)).run()
    assert limited.end == 1 and limited.failure.detail('budget') == budget
    assert limited.manifest.unchecked_time_rates == record.within(budget).manifest.unchecked_time_rates
    assert limited.manifest.unchecked_time_rates == (('yard.tabulated.request', 0),)


def test_checkpoint_keeps_the_omission_from_a_finished_occurrence():
    model = compile_text(SCOPE, UNITS)

    def make():
        return Plan.of(model.program, model.configuration)

    live = Run(make(), (Breakpoint('yard.controls.step[2]'),))
    checkpoint = live.run()
    assert checkpoint.stop.t == 3
    restored = Run.restored(make(), loads(dumps(checkpoint))).resume()
    straight = Run(make()).run()
    assert live.resume().manifest == restored.manifest == straight.manifest == checkpoint.record.manifest
    assert 'excluded 3 time-dependent settings' in restored.rate_guard_note


def test_an_older_checkpoint_without_coverage_loads_with_an_empty_note():
    model = compile_text(SCOPE, UNITS)
    live = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.controls.step[2]'),))
    checkpoint = live.run()
    header, body = dumps(checkpoint).split(b'\n', 1)
    earlier = json.loads(body)
    del earlier['record']['manifest']['unchecked_time_rates']
    restored = loads(header + b'\n' + json.dumps(earlier).encode())
    assert 'excluded 0 time-dependent settings' in restored.record.rate_guard_note
    result = Run.restored(Plan.of(model.program, model.configuration), restored).resume()
    assert result.failure is None
    assert result.manifest.unchecked_time_rates == (('yard.tabulated.request', checkpoint.stop.t),)
