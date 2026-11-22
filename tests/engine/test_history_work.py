"""Count history and validation work as the number of synthetic occurrences or samples doubles."""

import gc
from dataclasses import replace

import pytest

from napkin.engine import run
from napkin.engine.timeline.collections import dynamic_value
from napkin.engine.timeline.plan import Plan
from napkin.engine.timeline.record import Reader, key_of
from napkin.engine.uncertainty import Sample, _drawn
from napkin.model.compile import compile_text
from napkin.program.config import ConfigurationError, InputValue, Quantity

SIZES = (32, 64, 128)
SOURCE = """scenario "Occurrence history"
    horizon 130 h
yard:
    job = event(amount: L):
        after 1 h
    first = formula(this.job.occurrences.at(0 h).amount)
    latest = formula(this.job.occurrences.at(t).amount)
"""
UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


@pytest.mark.parametrize('n', SIZES)
def test_an_early_key_does_not_read_every_later_start(n):
    model = compile_text(SOURCE, UNITS)
    plan = Plan.of(model.program, model.configuration)
    dynamic = next(d for d in plan.dynamic.values() if d.op == 'at' and d.key is not None)
    values, starts = {}, []

    def read(name):
        if name.endswith('.started'):
            starts.append(name)
        return values[name]

    for i in range(n):
        # The first two starts tie at zero. The second wins even after many later starts.
        t = max(i - 1, 0)
        plan.occurrence('yard', 'job', i, (i,), t)
        values[f'yard.job#{i}.started'] = t
        values[f'yard.job#{i}.amount'] = i
        assert dynamic_value(dynamic, plan.members(dynamic.source), plan, read, t, plan.units) == min(i, 1)
    assert len(starts) <= 2 * n, f'{len(starts)} start-time reads for {n} lookups'


@pytest.mark.parametrize('n', SIZES)
def test_members_reuses_points_already_present(n):
    model = compile_text(SOURCE, UNITS)
    plan = Plan.of(model.program, model.configuration)
    source = ('occurrences', 'yard', 'job')
    previous = ()
    rebuilt = 0
    for i in range(n):
        plan.occurrence('yard', 'job', i, (i,), i)
        members = plan.members(source)
        assert members[-1] == ('occurrence', f'yard.job#{i}')
        if previous and members[0] is not previous[0]:
            rebuilt += i
        previous = members
    assert rebuilt <= n, f'{rebuilt} previously present points rebuilt over {n} starts'


def test_unchanged_active_endpoint_members_reuse_their_points():
    source = """scenario "Endpoint membership"
    horizon 1 h
yard:
    stock: L = 20 L
    flow tap: this.stock -> SINK
        request = 1 L/h
    visit = event():
        flow extra: this.stock -> SINK
            request = 1 L/h
        after 1 h
"""
    model = compile_text(source, UNITS)
    plan = Plan.of(model.program, model.configuration)
    outlet = ('flows', 'yard.stock', 'outflow')
    first = plan.members(outlet)
    assert list(first) == [('flow', 'yard.tap')]
    rebuilt = sum(plan.members(outlet)[0] is not first[0] for _ in range(128))
    assert rebuilt <= 1, f'{rebuilt} rebuilds of the same unchanged endpoint'


@pytest.mark.parametrize('n', SIZES)
def test_recorder_and_fresh_reader_visit_only_starts_they_need(n, monkeypatch):
    # Two entries share time 0. A later one starts each hour. Each field checks its chosen amount.
    stages = ''.join(f'        after 1 h:\n            this.job.start({i} L)\n' for i in range(2, n))
    source = SOURCE + '    launch = event():\n' + stages
    source += 'yard.job.start(0 L)\nyard.job.start(1 L)\nyard.launch.start()\n'
    model = compile_text(source, UNITS)
    program, cfg = model.program, model.configuration
    fields = ('yard.first', 'yard.latest')
    keys = tuple(key_of(program, name) for name in fields)
    cfg = replace(cfg, request=replace(cfg.request, keys=keys, everything=False))
    membership_reads = 0
    original = Plan.members_at

    def counted(plan, source, read, *args, **kwargs):
        def value(name):
            nonlocal membership_reads
            if name.endswith('.started'):
                membership_reads += 1
            return read(name)

        return original(plan, source, value, *args, **kwargs)

    monkeypatch.setattr(Plan, 'members_at', counted)
    record = run(program, cfg)
    assert record.failure is None, record.failure
    recording = membership_reads
    reader = Reader(record, program)
    stored_reads = 0
    stored = reader._stored

    def count_stored(value):
        nonlocal stored_reads
        if value.name.endswith('.started'):
            stored_reads += 1
        return stored(value)

    monkeypatch.setattr(reader, '_stored', count_stored)
    for i in reversed(range(n - 1)):
        assert [reader.at(name, i + 0.25) for name in fields] == [1, i + 1]
    counts = recording, membership_reads - recording, stored_reads
    assert max(counts) <= 12 * n, f'{counts} recorder, membership and stored start reads for {n} instances'


@pytest.mark.parametrize('n', SIZES)
def test_input_duplicate_detection_checks_each_key_a_bounded_number_of_times(n):
    comparisons = 0

    class Name(str):
        __hash__ = str.__hash__

        def __eq__(self, other):
            nonlocal comparisons
            comparisons += 1
            return super().__eq__(other)

    cfg = compile_text(SOURCE, UNITS).configuration
    inputs = tuple(InputValue('yard', Name(str(i)), Quantity(i)) for i in range(n))
    replace(cfg, inputs=inputs)
    with pytest.raises(
        ConfigurationError, match=r"an input is given twice: \('yard', '0'\), \('yard', '2'\)"
    ):
        replace(cfg, inputs=(*inputs, inputs[2], inputs[0], inputs[2]))
    assert comparisons <= 8 * n, f'{comparisons} name equality comparisons for {n} inputs'


@pytest.mark.parametrize('n', SIZES)
def test_draw_collection_does_not_copy_completed_prefixes(n):
    class FirstDraw(float):
        pass

    first = FirstDraw(0)
    copies = 0

    def samples():
        nonlocal copies
        previous = None
        for i in range(n):
            draws = [('daily', 'yard', first if i == 0 else i), ('choice', 'yard', bool(i % 2))]
            if i != 2:
                draws.append(('missing', 'yard', i))
            draws += [('twice', 'yard', i)] * (2 if i == 1 else 1)
            yield Sample(i, (), tuple(draws), 0, None)
            # Observe the numeric series retaining the first draw between successive samples.
            # A new list of length k with the same first object copied its k-1 retained draws.
            lists = [
                s
                for s in gc.get_referrers(first)
                if isinstance(s, list) and len(s) == i + 1 and s[0] is first
            ]
            if lists and lists[0] is not previous:
                copies += i
                previous = lists[0]

    series = _drawn(samples())
    assert series == {('daily', 'yard'): list(range(n)), ('choice', 'yard'): [bool(i % 2) for i in range(n)]}
    assert copies <= n, f'{copies} prior draw entries copied across {n} samples'
