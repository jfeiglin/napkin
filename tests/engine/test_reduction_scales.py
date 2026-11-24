"""A sum, minimum or maximum over selected members compares at their scales (change 29)."""

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    BOOL,
    SINK,
    Builder,
    after,
    assign,
    event,
    flow,
    fmax,
    fmin,
    formula,
    fsum,
    ifelse,
    input_,
    item,
    q,
    start,
    this,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.comparison_bands import band_samples
from tests.reference.from_program import run_of, value_at

# Both samples fit inside the coarse unit band and exceed the fine declared scale's band.
FINE_SCALE = 1e-12
SMALL, LARGER = band_samples(Configuration(Request(1)), 1, multiples=(0.125, 0.25))


def check(program, reader, keys, times, expected):
    cfg = Configuration(Request(max(1, *times)))
    if reader == 'reference':
        oracle, failure = run_of(program, cfg)
        assert failure is None
        found = [[value_at(oracle, program, key, t) for t in times] for key in keys]
    else:
        record = run(program, cfg)
        assert record.failure is None
        for key, row in zip(keys, expected, strict=True):
            assert [record.history(key).at(t) for t in times] == row
        found = [list(h.values) for h in read(record, program, keys, times)]
    assert found == expected


@pytest.mark.parametrize('filtered', [False, True], ids=['all', 'where'])
@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_a_reduction_compares_with_the_same_scale_as_its_members(reader, filtered):
    """The small and larger samples both differ from zero at the fine declared scale.
    Their sum has the same scale as a+b. A filtered-out 1 L scale cannot widen it."""
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    cell = b.template(
        'Cell',
        input_('kept', BOOL, True),
        input_('size', 'L', FINE_SCALE),
        input_('initial', 'L', SMALL),
        input_('divisor', '', 1),
        value('c', 'L', formula(this.initial / this.divisor), scale=this.size),
    )
    a = b.member(cell, 'a')
    second = b.member(cell, 'b', initial=LARGER)
    if filtered:
        b.member(cell, 'excluded', size=1, kept=False, divisor=0)
    members = cell.instances.where(item.kept) if filtered else cell.instances
    zero = q(0, 'L')
    pairs = [
        ('sum', fsum(members.c), a.c + second.c),
        ('min', fmin(members.c), fmin(a.c, second.c)),
        ('max', fmax(members.c), fmax(a.c, second.c)),
    ]
    b.entity(
        'report',
        *(
            value(name + form, BOOL, formula(expression == zero))
            for name, reduced, explicit in pairs
            for form, expression in [('Members', reduced), ('Explicit', explicit)]
        ),
    )
    keys = [Key('report', (name + form,)) for name, _, _ in pairs for form in ['Members', 'Explicit']]
    check(b.finish(), reader, keys, [1], [[False]] * len(keys))


@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_occurrence_sum_uses_the_members_present_at_the_read(reader):
    """The first sample keeps its fine scale after it freezes. When the coarse sample
    starts at hour two, their sum falls inside the wider band."""
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    plant = b.entity(
        'plant',
        value('fine', 'L', SMALL, scale=FINE_SCALE),
        value('coarse', 'L', SMALL, scale=1),
        value('selectFine', BOOL, True),
        event(
            'sample',
            value('c', 'L', formula(ifelse(this.selectFine, this.fine, this.coarse))),
            after(q(1, 'h')),
        ),
        event('again', after(q(2, 'h'), assign(this.selectFine, False), start(this.sample))),
        value('near', BOOL, formula(fsum(this.sample.occurrences.c) == q(0, 'L'))),
    )
    b.setup(start(plant.sample), start(plant.again))
    check(b.finish(), reader, [Key('plant', ('near',))], [3, 0, 1, 2], [[True, False, False, True]])


@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_subtracting_a_member_cancels_its_scale_in_a_sum(reader):
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    cell = b.template('Cell', input_('size', 'L', FINE_SCALE), value('c', 'L', SMALL, scale=this.size))
    a = b.member(cell, 'a', size=1)
    b.member(cell, 'b')
    b.entity('report', value('near', BOOL, formula(fsum(cell.instances.c) - a.c == q(0, 'L'))))
    check(b.finish(), reader, [Key('report', ('near',))], [0], [[False]])


@pytest.mark.parametrize('reader', ['engine', 'reference'])
@pytest.mark.parametrize('outside', [False, True], ids=['equal-stores', 'outside-sink'])
def test_an_endpoint_reduction_uses_only_its_present_filtered_flows(reader, outside):
    """A fine request alone differs from zero, including after a coarse temporary
    request leaves. Both destination stores start at zero. The filter distinguishes them
    by identity and keeps a temporary pipe to either the included store or the outside SINK."""
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    other = b.entity('other', value('stock', 'L', 0, lower=0))
    sink = b.entity('sink', value('stock', 'L', 0, lower=0))
    destination = SINK if outside else sink.stock
    kept = this.stock.outflow.flows.where(item.source == this.stock).where(other.stock != item.sink)
    plant = b.entity(
        'plant',
        value('stock', 'L', 1, lower=0),
        value('fine', 'L/h', SMALL, scale=FINE_SCALE),
        value('coarse', 'L/h', SMALL, scale=1),
        flow('base', this.stock, sink.stock, request=formula(this.fine)),
        flow('other', this.stock, other.stock, request=formula(this.coarse)),
        event('extra', flow('pipe', this.stock, destination, request=formula(this.coarse)), after(q(1, 'h'))),
        event('add', after(q(1, 'h'), start(this.extra))),
        value(
            'near',
            BOOL,
            formula(fsum(kept.request) == q(0, 'L/h')),
        ),
    )
    b.setup(start(plant.add))
    check(b.finish(), reader, [Key('plant', ('near',))], [3, 0, 1, 2], [[False, False, True, False]])
