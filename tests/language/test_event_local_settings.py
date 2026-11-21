"""Settings on a store or a pipe declared by an event, through the text and the program."""

import random
from fractions import Fraction
from textwrap import dedent

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program.build import (
    SINK,
    Builder,
    after,
    assign,
    endpoint,
    event,
    flow,
    local,
    param,
    q,
    start,
    value,
)
from napkin.program.check import ProgramError
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.engine.test_named_collection_reports import tanks
from tests.program.examples import UNITS
from tests.reference.from_program import run_of, value_at


def text_program(job):
    text = 'w:\n    job = event(cap: L/h):\n'
    text += ''.join(f'        {line}\n' for line in dedent(job).strip('\n').splitlines())
    return compile_text(text + 'w.job.start(0.5 L/h)\n', UNITS).program


def builder_program(*parts):
    b = Builder(UNITS)
    w = b.entity('w', event('job', param('cap', 'L/h'), *parts))
    b.setup(start(w.job, q(0.5, 'L/h')))
    return b.finish()


def readings(program, samples):
    times = [0, 1, 2]
    config = Configuration(Request(times[-1]))
    record = run(program, config)
    assert record.failure is None, record.failure
    oracle, failure = run_of(program, config)
    assert failure is None, failure
    for path, expected in samples.items():
        key = Key('w.job#0', tuple(path.split('.')))
        assert read(record, program, [key], times)[0].values == expected
        assert tuple(value_at(oracle, program, key, Fraction(t)) for t in times) == expected


@pytest.mark.parametrize('author', ['text', 'builder'])
def test_an_occurrence_stock_serves_its_own_outflow_capacity(author):
    if author == 'text':
        program = text_program("""
            limit: L/h = cap
            stock: L = 10 L
                outflow.capacity = limit
            flow pipe: stock -> SINK
                request = 2 L/h
            after 3 h
        """)
    else:
        program = builder_program(
            value('limit', 'L/h', local.cap),
            value('stock', 'L', 10, outflow=endpoint(capacity=local.limit)),
            flow('pipe', local.stock, SINK, request=q(2, 'L/h')),
            after(q(3, 'h')),
        )
    readings(program, {'stock': (10, 9.5, 9), 'pipe.actual_rate': (0.5, 0.5, 0.5)})


@pytest.mark.parametrize('author', ['text', 'builder'])
def test_an_occurrence_pipe_starts_uncapped_then_accepts_its_first_capacity(author):
    if author == 'text':
        program = text_program("""
            stock: L = 10 L
            flow pipe: stock -> SINK
                request = 2 L/h
            after 1 h:
                pipe.capacity = cap
            after 2 h
        """)
    else:
        program = builder_program(
            value('stock', 'L', 10),
            flow('pipe', local.stock, SINK, request=q(2, 'L/h')),
            after(q(1, 'h'), assign(local.pipe.capacity, local.cap)),
            after(q(2, 'h')),
        )
    readings(program, {'stock': (10, 8, 7.5), 'pipe.actual_rate': (2, 0.5, 0.5)})


@pytest.mark.parametrize('author', ['text', 'builder'])
def test_a_plain_endpoint_setting_can_only_read_locals_initialized_by_its_entry(author):
    if author == 'text':
        with pytest.raises(LanguageError) as caught:
            text_program("""
                stock: L = 10 L
                    outflow.capacity = later
                later: L/h = cap
                after 3 h
            """)
    else:
        with pytest.raises(ProgramError) as caught:
            builder_program(
                value('stock', 'L', 10, outflow=endpoint(capacity=local.later)),
                value('later', 'L/h', local.cap),
                after(q(3, 'h')),
            )
    codes = caught.value.codes if author == 'text' else [item.code for item in caught.value.diagnostics]
    assert 'local_order' in codes


def test_a_retained_endpoint_setting_can_read_a_later_local():
    program = text_program("""
        stock: L = 10 L
            outflow.capacity = formula(later)
        later: L/h = cap
        flow pipe: stock -> SINK
            request = 2 L/h
        after 3 h
    """)
    readings(program, {'stock': (10, 9.5, 9)})


def test_plain_settings_can_read_their_store_and_priority_can_name_a_later_pipe():
    program = text_program("""
        stock: L = 10 L
            inflow.capacity = cap
            inflow.request = 2 L/h
            outflow.capacity = stock / 10 h
            outflow.request = 2 L/h
            outflow.allocation = priority(second)
        flow supply: SOURCE -> stock
            request = 2 L/h
        flow first: stock -> SINK
            request = 2 L/h
        flow second: stock -> SINK
            request = 2 L/h
        after 3 h
    """)
    readings(
        program,
        {
            'stock': (10, 9.5, 9),
            'supply.actual_rate': (0.5,) * 3,
            'first.actual_rate': (0,) * 3,
            'second.actual_rate': (1,) * 3,
            'stock.inflow.request': (2,) * 3,
            'stock.outflow.request': (2,) * 3,
        },
    )


def endpoint_transform(seed):
    """Move the generated tanks, their settings and pipes into events that start at zero."""
    rng = random.Random(seed)
    models = ([], [])
    expected = []
    for i, (_, _, water, fill, drain) in enumerate(tanks(rng)):
        name = f'tank{i}'
        into, out = (rng.choice((0.25, 0.5, 1, 1.5)) for _ in range(2))
        levels = tuple(water + t * (min(fill, into) - min(drain, out)) for t in (0, 1, 2))
        expected.append(levels)
        for lines, occurrence in zip(models, (False, True)):
            lines.append(f'{name}:')
            if occurrence:
                lines.append('    use = event():')
            tab = '        ' if occurrence else '    '
            stock = 'water' if occurrence else 'this.water'
            lines.extend(
                tab + line
                for line in (
                    f'water: L = {water} L',
                    f'    inflow.capacity = {into} L/h',
                    f'    outflow.capacity = {out} L/h',
                    f'flow fill: SOURCE -> {stock}',
                    f'    request = {fill} L/h',
                    f'flow drain: {stock} -> SINK',
                    f'    request = {drain} L/h',
                )
            )
            if occurrence:
                lines.extend([tab + 'after 3 h', f'{name}.use.start()'])
    for lines, occurrence in zip(models, (False, True)):
        program = compile_text('\n'.join(lines) + '\n', UNITS).program
        config = Configuration(Request(2))
        record = run(program, config)
        oracle, failed = run_of(program, config)
        assert record.failure is None and failed is None, (record.failure, failed)
        for i, levels in enumerate(expected):
            owner = f'tank{i}' + ('.use#0' if occurrence else '')
            key = Key(owner, ('water',))
            assert read(record, program, [key], [0, 1, 2])[0].values == levels
            assert tuple(value_at(oracle, program, key, Fraction(t)) for t in (0, 1, 2)) == levels


@pytest.mark.parametrize('seed', range(12))
def test_moving_a_configured_tank_into_an_event_keeps_its_rates(seed):
    endpoint_transform(seed)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(12, 72))
def test_more_configured_tanks_moved_into_events_keep_their_rates(seed):
    endpoint_transform(seed)
