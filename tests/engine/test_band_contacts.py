"""Only the physically related contacts may disappear when a marked firing stops a stock early."""

from dataclasses import replace

import pytest

from napkin.engine.timeline import Plan
from napkin.engine.timeline.record import Reader
from napkin.model.compile import compile_text
from napkin.program.record import Entry, History, Manifest, Piece, Record
from tests.engine.band_contacts import band_preemptions, compared_fire_details, paired_fire_details


@pytest.fixture
def pair():
    model = compile_text(
        """scenario "A draining tank"
    horizon 4 h
tank:
    level: L = 2 L in [0 L,]
    flow drain: this.level -> SINK
        request = formula(1 L/h if this.level > 0 L else 0 L/h)
    flow other: this.level -> SINK
        request = 0 L/h
    empty = event():
        when this.level <= 0 L:
            this.empty.start()
        after 0 h
""",
        {'L': {'volume': 1}, 'h': {'time': 1}},
    )
    plan = Plan.of(model.program, model.configuration)
    trigger = plan.triggers[0]
    stock = 'tank.level'
    bound_time = 2.0
    band_time = bound_time - 5e-8
    gap = bound_time - band_time
    mark = ((trigger.origin, 'tank.level <= 0 L', gap, 1e-7),)
    fire = Entry(bound_time, 1, 'fire', trigger.origin, 'tank')
    later = Entry(3, 1, 'finish', 'tank.empty', 'tank.empty#0')

    def contact(name, kind):
        near = ((name, f'{kind} of {name} and the moment at 2 h', 0.0, 1e-8),)
        return Entry(bound_time, 1, 'contact', name, 'tank', (('near', near), ('located', bound_time)))

    def record(time, trace):
        stock_pieces = (Piece(0, 2.0, -1.0), Piece(time, bound_time - time))
        flow_pieces = (Piece(0, 1.0), Piece(time, 0.0))
        return Record(
            Manifest(4),
            (
                History(plan.values[stock].key, stock_pieces),
                History(plan.values['tank.drain.actual_rate'].key, flow_pieces),
            ),
            trace,
        )

    old = record(bound_time, (contact(stock, 'lower bound'), contact('tank.drain', 'switch'), fire, later))
    firing = replace(fire, t=band_time, details=(('near', mark), ('band_entry', mark)))
    new = record(band_time, (firing, later))
    return model.program, old, new


def prove(program, before, after):
    return band_preemptions(before.trace, after.trace, Reader(before, program), Reader(after, program), 1e-8)


def test_only_the_stopped_stock_and_its_switch_are_exempt(pair):
    program, before, after = pair
    (found,) = prove(program, before, after)
    assert (found.contact_side, found.contact_indices, found.stock, found.switches) == (
        'before',
        (0, 1),
        'tank.level',
        ('tank.drain',),
    )
    assert found.remainder == 2.0 - after.trace[0].t
    (reverse,) = prove(program, after, before)
    assert reverse.contact_side == 'after'
    assert not prove(program, before, replace(after, trace=after.trace[:-1]))
    missing_evidence = replace(after.trace[0], details=(after.trace[0].details[0],))
    assert not prove(program, before, replace(after, trace=(missing_evidence, *after.trace[1:])))

    unrelated = replace(
        before.trace[1],
        part='tank.other',
        details=(
            ('near', (('tank.other', 'switch of tank.other and the moment at 2 h', 0.0, 1e-8),)),
            ('located', 2.0),
        ),
    )
    assert not prove(program, replace(before, trace=(before.trace[0], unrelated, *before.trace[2:])), after)


def test_the_firing_must_end_motion_inside_the_band(pair):
    program, before, after = pair
    # This trace lacks the switch, so it must be possible to prove a lone bound strictly on its stock.
    before = replace(before, trace=(before.trace[0], *before.trace[2:]))
    assert len(prove(program, before, after)) == 1
    stock, flow = after.histories
    opening, landed = stock.pieces
    for pieces in [
        (replace(opening, value=landed.value, rate=0), landed),  # already held
        (opening, replace(landed, rate=-1)),  # continued beyond the firing
        (opening, replace(landed, value=9e-8)),  # marker does not match accepted balance
    ]:
        assert not prove(program, before, replace(after, histories=(replace(stock, pieces=pieces), flow)))
    fire = after.trace[0]
    origin, expr, gap, band = fire.detail('band_entry')[0]
    for bad in [(origin, expr, gap, 0.0), (origin, expr, band * 2, band), (origin, expr, 0.0, band)]:
        with pytest.raises(ValueError, match='invalid band_entry'):
            compared_fire_details(replace(fire, details=(('near', (bad,)), ('band_entry', (bad,)))))


def test_only_annotated_new_near_rows_are_metadata(pair):
    _, before, after = pair
    left, right = before.trace[2], after.trace[0]
    assert paired_fire_details(left, right) == ((), ())
    rows = right.detail('near')
    old = replace(left, details=(('near', rows),))
    assert paired_fire_details(old, right) == (old.details, old.details)
    unrelated = (left.part, 'other comparison', 1e-12, 1e-9)
    extra = replace(right, details=(('near', (*rows, unrelated)), ('band_entry', rows)))
    assert paired_fire_details(left, extra) == ((), (('near', (unrelated,)),))
    large = ((left.part, 'a wide comparison', '3e400', '4e400'),)
    assert compared_fire_details(replace(right, details=(('near', large), ('band_entry', large)))) == (
        ('near', large),
    )
