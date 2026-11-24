"""Stage targets keep their occurrence identity when another occurrence starts."""

import pytest

from napkin.engine.timeline import Plan, Run, read, resume
from napkin.model.compile import compile_text
from napkin.program.build import (
    SINK,
    Builder,
    after,
    assign,
    event,
    flow,
    local,
    occurrence_of,
    q,
    start,
    t,
    this,
    value,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.engine.resume_parity import assert_resume_parity
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
CONFIG = Configuration(Request(2))
SOURCE = """tank:
    drain = event():
        stock: L = 10 L in [0 L,]
        flow pipe: stock -> SINK
            request = 2 L/h
        after 4 h
    tune = event():
        after 0.5 h:
            this.drain.start()
        after 0.5 h:
            this.drain.occurrences.at(0 h).TARGET.capacity = 0.5 L/h
tank.drain.start()
tank.tune.start()
"""


def selected_program(form, target, selector):
    reference = {
        'past': 'this.drain.occurrences.at(0 h)',
        'captured': 'job',
        'current': 'this.drain.occurrences.at(t)',
    }[selector]
    if form == 'text':
        source = SOURCE.replace('this.drain.occurrences.at(0 h).TARGET', f'{reference}.{target}')
        if selector == 'captured':
            source = source.replace(
                '    tune = event():', '    tune = event():\n        job = this.drain.occurrences.at(t)'
            )
        return compile_text(source, UNITS).program
    b = Builder(UNITS)
    latest = this.drain.occurrences.at(t)
    owner = {'past': this.drain.occurrences.at(q(0, 'h')), 'captured': local.job, 'current': latest}[selector]
    field = owner.pipe if target == 'pipe' else owner.stock.outflow
    tank = b.entity(
        'tank',
        event(
            'drain',
            value('stock', 'L', 10, lower=0),
            flow('pipe', local.stock, SINK, request=q(2, 'L/h')),
            after(q(4, 'h')),
        ),
        event(
            'tune',
            *([value('job', occurrence_of('tank', 'drain'), latest)] if selector == 'captured' else []),
            after(q(0.5, 'h'), start(this.drain)),
            after(q(0.5, 'h'), assign(field.capacity, q(0.5, 'L/h'))),
        ),
    )
    b.setup(start(tank.drain), start(tank.tune))
    return b.finish()


@pytest.mark.parametrize('form', ['text', 'builder'])
@pytest.mark.parametrize('target', ['pipe', 'stock.outflow'])
@pytest.mark.parametrize('selector', ['past', 'captured', 'current'])
def test_first_cap_is_posted_to_the_selected_active_occurrence(form, target, selector):
    program = selected_program(form, target, selector)
    direct = Run(Plan.of(program, CONFIG)).run()
    assert direct.failure is None, direct.failure
    live = Run(Plan.of(program, CONFIG), (Breakpoint('tank.tune.step[1]'),))
    stopped = live.run()
    assert isinstance(stopped, Checkpoint)
    restored = resume(program, loads(dumps(stopped)))
    assert_resume_parity(program, CONFIG, direct, restored)
    keys = [Key(f'tank.drain#{i}', steps) for i in (0, 1) for steps in (('stock',), ('pipe', 'actual_rate'))]
    if selector == 'current':
        expected = [(8, 6), (2, 2), (9, 8.5), (0.5, 0.5)]
    else:
        expected = [(8, 7.5), (0.5, 0.5), (9, 7), (2, 2)]
    assert [r.values for r in read(restored, program, keys, [1, 2])] == expected
    oracle, failure = run_of(program, CONFIG)
    assert failure is None
    for key, values in zip(keys, expected, strict=True):
        assert tuple(value_at(oracle, program, key, time) for time in (1, 2)) == values


def test_writing_a_finished_occurrence_rolls_back_the_earlier_move_and_trace():
    source = """tank:
    money: L = 2 L
    held: L = 0 L
    drain = event():
        flow pipe: SOURCE -> SINK
            request = 0 L/h
        after 0.25 h
    tune = event():
        after 1 h:
            move 1 L from this.money to this.held
            this.drain.occurrences.at(0 h).pipe.capacity = 0.5 L/h
tank.drain.start()
tank.tune.start()
"""
    program = compile_text(source, UNITS).program
    record = Run(Plan.of(program, CONFIG)).run()
    assert record.failure is not None and record.failure.t == 1
    assert 'finished' in record.failure.detail('message') and 'tank.drain#0' in record.failure.detail(
        'message'
    )
    assert not record.entries('move')
    assert [r.values for r in read(record, program, ['tank.money', 'tank.held'], [1])] == [(2,), (0,)]


@pytest.mark.parametrize(
    'reference', ['job', 'this.drain.occurrences.at(t)', 'this.drain.occurrences.at(0 h)']
)
def test_readonly_protects_a_stored_binding_through_every_reference(reference):
    from napkin.model.language.problems import LanguageError

    source = (
        SOURCE.replace('stock: L = 10 L', 'readonly stock: L = 10 L')
        .replace('    tune = event():', '    tune = event():\n        job = this.drain.occurrences.at(t)')
        .replace('this.drain.occurrences.at(0 h).TARGET.capacity = 0.5 L/h', f'{reference}.stock = 0 L')
    )
    with pytest.raises(LanguageError) as error:
        compile_text(source, UNITS)
    assert error.value.codes == ['readonly_write']


def test_a_lookup_reads_prior_writes_to_its_key_in_the_same_stage():
    source = SOURCE.replace('tank:\n', 'tank:\n    pick: h = 1 h\n').replace(
        'this.drain.occurrences.at(0 h).TARGET.capacity = 0.5 L/h',
        'this.pick = 0 h\n'
        '            this.drain.occurrences.at(this.pick).pipe.capacity = 0.5 L/h\n'
        '            this.pick = 0.5 h\n'
        '            this.drain.occurrences.at(this.pick).pipe.capacity = 1.5 L/h',
    )
    program = compile_text(source, UNITS).program
    keys = [Key(f'tank.drain#{index}', ('stock',)) for index in (0, 1)]
    wanted = [(8, 7.5), (9, 7.5)]
    oracle, failure = run_of(program, CONFIG)
    assert failure is None
    assert [tuple(value_at(oracle, program, key, at) for at in (1, 2)) for key in keys] == wanted
    direct = Run(Plan.of(program, CONFIG)).run()
    assert direct.failure is None, direct.failure
    assert [row.values for row in read(direct, program, keys, [1, 2])] == wanted


def test_a_write_key_before_the_oldest_start_fails_and_discards_the_stage():
    source = (
        SOURCE.replace('tank:\n', 'tank:\n    pick: h = 1 h\n')
        .replace('\ntank.drain.start()', '')
        .replace(
            'this.drain.occurrences.at(0 h).TARGET.capacity = 0.5 L/h',
            'this.pick = 0 h\n            this.drain.occurrences.at(this.pick).pipe.capacity = 0.5 L/h',
        )
    )
    program = compile_text(source, UNITS).program
    oracle, failure = run_of(program, CONFIG)
    assert failure is not None and oracle.view.t == 1
    assert value_at(oracle, program, Key('tank', ('pick',)), 1) == 1
    direct = Run(Plan.of(program, CONFIG)).run()
    assert direct.failure is not None and direct.failure.t == 1
    assert [row.values for row in read(direct, program, ['tank.pick', 'tank.drain#0.stock'], [1])] == [
        (1,),
        (9,),
    ]


def test_a_late_child_failure_discards_the_endpoint_policy_and_first_capacity():
    from napkin.program.record import Unavailable

    source = """yard:
    water: L = 20 L in [0 L,]
        outflow.capacity = 3 L/h
        outflow.allocation = priority(this.second)
    flow first: this.water -> SINK
        request = 2 L/h
    flow second: this.water -> SINK
        request = 4 L/h
    child = event(size: L in [0 L, 5 L]):
        after 2 h
    change_policy = event():
        after 1 h:
            this.water.outflow.allocation = priority(this.first)
            this.first.capacity = 0.25 L/h
            this.child.start(9 L)
yard.change_policy.start()
"""
    program = compile_text(source, UNITS).program
    live = Run(Plan.of(program, CONFIG), (Breakpoint('yard.change_policy.step[0]'),))
    stop = live.run()
    restored = Run.restored(Plan.of(program, CONFIG), loads(dumps(stop)))
    for engine in (live, restored):
        before = dict(engine.plan.rankings)
        record = engine.resume()
        assert record.failure is not None and record.end == 1
        assert 'yard.child' in record.failure.detail('message')
        assert not any(e.kind == 'commit' and e.part == 'yard.change_policy.step[0]' for e in record.trace)
        assert engine.plan.rankings == before
        assert not any(entry[0] == 'allocate' for entry in engine.plan.log)
        left, right, ceiling = read(
            record,
            program,
            ['yard.first.actual_rate', 'yard.second.actual_rate', 'yard.first.capacity'],
            [0.5, 1],
        )
        assert (left.values, right.values) == ((0, 0), (3, 3))
        assert all(isinstance(capacity, Unavailable) for capacity in ceiling.values)


@pytest.mark.parametrize('key', ['this.pick', 'at_start', 'captured_key', 't - 1 h'])
def test_reference_captures_its_historical_key_once_and_replays_it(key):
    from napkin.program.artifact import loads as load_artifact

    text = f"""scenario "Remember a particular delivery"
    horizon 3 h
yard:
    pick: h = 0 h
    result: L = 0 L
    delivery = event(size: L):
        after 4 h
    observe = event(at_start: h):
        captured_key: h = at_start
        selected = this.delivery.occurrences.at({key})
        remember = formula(selected.size)
        after 1 h:
            this.result = selected.size
    dispatch = event():
        after 1 h:
            this.delivery.start(7 L)
            this.observe.start(0 h)
        after 0.5 h:
            this.pick = 1 h
yard.delivery.start(3 L)
yard.dispatch.start()
"""
    source = compile_text(text, UNITS)
    made = Run(Plan.of(source.program, source.configuration), (Breakpoint('yard.observe.step[0]'),))
    stop = made.run()
    assert isinstance(stop, Checkpoint) and stop.stop.t == 2
    loaded = load_artifact(source.artifact().data()).program
    fresh = Run.restored(Plan.of(loaded, source.configuration), loads(dumps(stop))).resume()
    assert_resume_parity(source.program, source.configuration, made.resume(), fresh)
    assert fresh.failure is None
    result, remembered = read(fresh, loaded, ['yard.result', 'yard.observe#0.remember'], [2, 3])
    assert result.values == remembered.values == (3, 3)


def test_priority_and_its_flows_select_the_same_older_occurrence_until_proportional_is_restored():
    text = """scenario "Select the older endpoint"
    horizon 3 h
yard:
    job = event():
        tank: L = 20 L
            outflow.capacity = 3 L/h
        flow first: tank -> SINK
            request = 2 L/h
        flow second: tank -> SINK
            request = 4 L/h
        after 4 h
    dispatch = event():
        after 0.5 h:
            this.job.start()
        after 0.5 h:
            this.job.occurrences.at(0 h).tank.outflow.allocation = priority(this.job.occurrences.at(0 h).first)
        after 1 h:
            this.job.occurrences.at(0 h).tank.outflow.allocation = proportional()
yard.job.start()
yard.dispatch.start()
"""
    source = compile_text(text, UNITS)
    live = Run(Plan.of(source.program, source.configuration), (Breakpoint('yard.dispatch.step[2]'),))
    stop = live.run()
    assert isinstance(stop, Checkpoint) and stop.stop.t == 2
    resumed = Run.restored(Plan.of(source.program, source.configuration), loads(dumps(stop))).resume()
    assert_resume_parity(source.program, source.configuration, live.resume(), resumed)
    assert resumed.failure is None
    keys = [f'yard.job#{index}.{name}.actual_rate' for index in (0, 1) for name in ('first', 'second')]
    assert [r.values for r in read(resumed, source.program, keys, [0.75, 1.5, 2.5])] == [
        (1, 2, 1),
        (2, 1, 2),
        (1, 1, 1),
        (2, 2, 2),
    ]
