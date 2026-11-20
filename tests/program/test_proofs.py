"""The proofs over a program and a configuration (`napkin/program/proofs.py`): that a value never falls
over a run (D10), and what a value reads. Each expected conclusion is worked by hand from the spec
("Formulas and the values a caller can read", "What a proof establishes") and the rules of the
module's docstring: which writers can take from what a value counts."""

from fractions import Fraction
from itertools import pairwise

import pytest

from napkin.program.build import (
    BOOL,
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    count,
    endpoint,
    event,
    flow,
    fmax,
    formula,
    fsum,
    given,
    ifelse,
    input_,
    item,
    local,
    minimize,
    move,
    named,
    param,
    q,
    ref_to,
    route,
    solve_for,
    solver,
    start,
    subtract,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, InputValue, Quantity, Request
from napkin.program.proofs import Part, never_falls, reads
from napkin.program.record import Key
from tests.program.examples import EXAMPLES, UNITS

RUN = Configuration(Request(10))


def proved(program, owner, *steps, configuration=RUN):
    return never_falls(program, configuration, Key(owner, steps))


def test_the_spec_volume_never_falls_and_the_rate_can():
    """Spec: `unserved_volume` qualifies, because only flows into tallies change it; `unserved_now`
    does not, because it falls when service returns."""
    example = EXAMPLES['water_service_returns']()
    volume = never_falls(example.program, example.configuration, Key('', ('unserved_volume',)))
    assert volume.holds, volume.reason
    assert 'Utility.count_unserved of north' in volume.reason
    now = never_falls(example.program, example.configuration, Key('', ('unserved_now',)))
    assert not now.holds
    assert 'actual_rate' in now.reason and 'rate of a flow' in now.reason


def _tank(**more):
    b = Builder(UNITS)
    tank = b.entity('tank', value('water', 'L', 8, lower=0), value('spilled', 'L', 0, lower=0), **more)
    b.entity(
        'pipe',
        flow('delivery', tank.water, SINK, request=q(1, 'L/h')),
        flow('spill', SOURCE, tank.spilled, request=q(2, 'L/h')),
    )
    return b


def test_a_store_that_a_flow_takes_from_can_fall_and_a_tally_never_does():
    program = _tank().finish()
    water = proved(program, 'tank', 'water')
    assert not water.holds and water.reason == 'pipe.delivery of pipe takes from what it counts'
    spilled = proved(program, 'tank', 'spilled')
    assert spilled.holds and 'pipe.spill of pipe' in spilled.reason


def test_an_input_is_fixed_and_a_rate_or_a_yes_no_is_no_tally():
    b = Builder(UNITS)
    b.entity('pump', input_('rate', 'L/h', q(2, 'L/h')), value('on', BOOL, True))
    b.entity('line', flow('feed', SOURCE, SINK, request=q(1, 'L/h')))
    program = b.finish()
    assert proved(program, 'pump', 'rate') == never_falls(program, RUN, Key('pump', ('rate',)))
    assert proved(program, 'pump', 'rate').holds
    assert not proved(program, 'pump', 'on').holds
    rate = proved(program, 'line', 'feed', 'actual_rate')
    assert not rate.holds and 'follows its sharing' in rate.reason


def _ward():
    """Susceptible people fall ill and the ill recover: S -> I -> R, with S drawn down."""
    b = Builder(UNITS)
    ward = b.entity(
        'ward',
        value('susceptible', 'person', 100, lower=0),
        value('ill', 'person', 0, lower=0),
        value('recovered', 'person', 0, lower=0),
    )
    b.entity(
        'spread',
        flow('infect', ward.susceptible, ward.ill, request=q(3, 'person/h')),
        flow('recover', ward.ill, ward.recovered, request=q(1, 'person/h')),
    )
    b.root(
        value('ever_ill', 'person', formula(ward.ill + ward.recovered)),
        value('doubled', 'person', formula(ward.ill * 2 + ward.recovered * 2)),
        value('lopsided', 'person', formula(ward.ill * 2 + ward.recovered)),
        value('still_well', 'person', formula(ward.susceptible + ward.ill)),
    )
    return b.finish()


def test_a_flow_between_two_counted_stores_cancels():
    """`ill + recovered` never falls while the ill recover (the old cumulative incidence); `ill`
    alone falls by recovery, and `2 ill + recovered` falls by one for each recovery."""
    program = _ward()
    ever = proved(program, '', 'ever_ill')
    assert ever.holds, ever.reason
    assert proved(program, '', 'doubled').holds
    assert not proved(program, 'ward', 'ill').holds
    lopsided = proved(program, '', 'lopsided')
    assert not lopsided.holds and lopsided.reason == 'spread.recover of spread takes from what it counts'
    assert not proved(program, '', 'still_well').holds


def test_a_route_needs_one_coefficient_at_both_ends():
    b = Builder(UNITS)
    west = b.entity('west', value('water', 'L', 5, lower=0))
    east = b.entity('east', value('water', 'L', 5, lower=0))
    b.entity('canal', route('link', west.water, east.water, capacity=q(1, 'L/h')))
    b.root(
        value('both', 'L', formula(west.water + east.water)),
        value('heavy_east', 'L', formula(west.water + east.water * 2)),
    )
    program = b.finish()
    assert proved(program, '', 'both').holds
    heavy = proved(program, '', 'heavy_east')
    assert not heavy.holds and 'moves either way' in heavy.reason
    assert not proved(program, 'west', 'water').holds


def _counter(*steps, amount=None):
    b = Builder(UNITS)
    b.entity(
        'clerk',
        value('tally', 'person', 0, lower=0),
        value('stock', 'person', 10, lower=0),
        value('change', 'person', 3, lower=0) if amount is None else amount,
        event('work', after(q(1, 'h'), *steps)),
    )
    b.setup(start(named('clerk').work))
    return b.finish()


@pytest.mark.parametrize(
    ('statement', 'holds', 'reason'),
    [
        (lambda: add(this.tally, q(1, 'person')), True, 'clerk.work.step[0].do[0] of clerk'),
        (lambda: add(this.tally, this.change), True, 'clerk.work.step[0].do[0] of clerk'),
        (lambda: subtract(this.tally, q(1, 'person')), False, 'takes from what it counts'),
        (lambda: assign(this.tally, q(0, 'person')), False, 'sets what it counts'),
        (lambda: move(q(2, 'person'), this.stock, this.tally), True, 'clerk.work.step[0].do[0] of clerk'),
        (lambda: move(q(2, 'person'), this.tally, this.stock), False, 'takes from what it counts'),
    ],
)
def test_a_stage_adds_moves_or_sets(statement, holds, reason):
    """`+=` of an amount from zero (a constant, a store bounded below by zero) adds; `-=` takes; `=`
    can set anything; a move into the tally adds and a move out of it takes."""
    found = proved(_counter(statement()), 'clerk', 'tally')
    assert found.holds is holds, found.reason
    assert reason in found.reason


def test_an_amount_of_no_known_sign_can_take():
    program = _counter(add(this.tally, this.change), amount=value('change', 'person', 3))
    found = proved(program, 'clerk', 'tally')
    assert not found.holds and 'no known sign' in found.reason


def test_the_setup_writes_before_any_read():
    """The setup is round zero at time 0: a read at time 0 already sees what it wrote."""
    b = Builder(UNITS)
    clerk = b.entity('clerk', value('tally', 'person', 5, lower=0))
    b.setup(assign(clerk.tally, q(0, 'person')))
    found = proved(b.finish(), 'clerk', 'tally')
    assert found.holds and found.reason == 'nothing changes what it counts during the run'


def _depot(enabled=True):
    """A depot whose deliveries each take from its stock through a flow of their own and count what
    they took in a shared tally; a recall, which only an enabled input starts, takes the tally back."""
    b = Builder(UNITS)
    b.entity(
        'depot',
        input_('recalls', BOOL, enabled),
        value('stock', 'L', 40, lower=0),
        value('delivered', 'L', 0, lower=0),
        event(
            'deliver',
            param('amount', 'L'),
            flow('truck', this.stock, this.delivered, request=q(10, 'L/h')),
            after(q(2, 'h')),
        ),
        event(
            'recall',
            when(this.recalls & (t >= q(1, 'h')), start(this.recall)),
            after(q(0, 'h'), move(q(1, 'L'), this.delivered, this.stock)),
        ),
    )
    b.setup(start(named('depot').deliver, q(5, 'L')))
    return b.finish()


def test_a_shared_store_that_another_occurrence_drains_can_fall():
    """Spec: a proof covers every place that can write the value, each flow declared in an event."""
    program = _depot()
    stock = proved(program, 'depot', 'stock')
    assert not stock.holds and stock.reason == 'depot.deliver.truck of depot takes from what it counts'
    delivered = proved(program, 'depot', 'delivered')
    assert not delivered.holds and 'depot.recall.step[0].do[0] of depot takes' in delivered.reason


def test_an_event_that_cannot_start_writes_nothing():
    """With recalls off, the recall's trigger cannot hold (D16), so the tally only gains, and the
    reason says why the recall does not count."""
    off = Configuration(Request(10), inputs=(InputValue('depot', 'recalls', False),))
    found = proved(_depot(), 'depot', 'delivered', configuration=off)
    assert found.holds, found.reason
    assert 'depot.recall cannot start' in found.reason


def test_the_time_and_counts_of_occurrences_rise():
    program = _depot()
    b = Builder(UNITS)
    b.root(
        value('clock', 'h', formula(t * 2)),
        value('countdown', 'h', formula(q(10, 'h') - t)),
    )
    clocks = b.finish()
    assert proved(clocks, '', 'clock').holds
    countdown = proved(clocks, '', 'countdown')
    assert not countdown.holds and countdown.reason == 'it falls as the time goes on'
    b = Builder(UNITS)
    depot = b.entity('depot', event('deliver', after(q(1, 'h'))))
    b.root(
        value('deliveries', '', formula(count(depot.deliver.occurrences))),
        value('finished', '', formula(count(depot.deliver.occurrences.done))),
        value('running', '', formula(count(depot.deliver.occurrences.active))),
    )
    program = b.finish()
    assert proved(program, '', 'deliveries').holds
    assert proved(program, '', 'finished').holds
    assert not proved(program, '', 'running').holds


def test_a_product_takes_the_sign_of_its_factor_under_the_configuration():
    b = Builder(UNITS)
    clinic = b.entity(
        'clinic',
        input_('weight', '', 2),
        value('seen', 'person', 0, lower=0),
        flow('arrive', SOURCE, this.seen, request=q(1, 'person/h')),
    )
    b.root(value('score', 'person', formula(clinic.seen * clinic.weight)))
    program = b.finish()
    assert proved(program, '', 'score').holds
    negative = Configuration(Request(10), inputs=(InputValue('clinic', 'weight', Quantity(-1)),))
    found = proved(program, '', 'score', configuration=negative)
    assert not found.holds and 'clinic.arrive of clinic takes' in found.reason


def test_min_and_max_of_what_never_falls_never_fall():
    b = Builder(UNITS)
    a = b.entity('a', value('tally', 'L', 0, lower=0), flow('fill', SOURCE, this.tally, request=q(1, 'L/h')))
    c = b.entity('c', value('tally', 'L', 0, lower=0), flow('fill', SOURCE, this.tally, request=q(2, 'L/h')))
    b.root(
        value('larger', 'L', formula(fmax(a.tally, c.tally))),
        value('rate_or_tally', 'L/h', formula(fmax(q(0, 'L/h'), a.fill.actual_rate))),
    )
    program = b.finish()
    assert proved(program, '', 'larger').holds
    assert not proved(program, '', 'rate_or_tally').holds


def test_a_sum_over_every_member_cancels_and_a_where_may_leave_a_member_out():
    """Moves between members of one template cancel in a sum over all of them; a member that a
    `where` may leave out has a coefficient of its own or zero, so a move away from it can fall."""
    b = Builder(UNITS)
    bin_ = b.template(
        'Bin',
        input_('north', BOOL, True),
        value('grain', 'g', 10, lower=0),
        event(
            'pass_on',
            param('other', ref_to('Bin')),
            after(q(1, 'h'), move(q(1, 'g'), this.grain, local.other.grain)),
        ),
    )
    first = b.member(bin_, 'first')
    second = b.member(bin_, 'second', north=False)
    b.setup(start(first.pass_on, second))
    b.root(
        value('all_grain', 'g', formula(fsum(bin_.instances.grain))),
        value('north_grain', 'g', formula(fsum(bin_.instances.where(item.north).grain))),
    )
    program = b.finish()
    assert proved(program, '', 'all_grain').holds
    assert not proved(program, '', 'north_grain').holds


def test_a_solver_that_determines_a_store_can_set_it():
    b = Builder(UNITS)
    b.entity(
        'battery',
        value('charge', 'Wh', 5, lower=0, upper=10),
        solver('plan', given('now', this.charge), solve_for(this.charge), minimize(this.charge)),
    )
    found = proved(b.finish(), 'battery', 'charge')
    assert not found.holds and found.reason == 'battery.plan of battery determines what it counts'


def test_a_formula_that_a_stage_redefines_can_fall():
    b = Builder(UNITS)
    b.entity(
        'gauge',
        value('reading', 'h', formula(t)),
        event('reset', after(q(1, 'h'), assign(this.reading, formula(q(0, 'h'))))),
    )
    b.setup(start(named('gauge').reset))
    found = proved(b.finish(), 'gauge', 'reading')
    assert (
        not found.holds
        and found.reason == 'gauge.reset.step[0].do[0] can give gauge.reading a new definition'
    )


def test_what_a_value_reads_reaches_its_writers_their_events_and_triggers():
    """The tally reads the flow that fills it, the flow its request, the request a store that a
    stage writes, the stage its event, and the event the trigger that starts it."""
    example = EXAMPLES['water_service_returns']()
    found = reads(example.program, example.configuration, Key('north', ('unserved',)))
    assert found.start == Part('value', 'Utility.unserved', 'north')
    chain = [
        Part('value', 'Utility.unserved', 'north'),
        Part('flow', 'Utility.count_unserved', 'north'),
        Part('value', 'Utility.unserved_rate', 'north'),
        Part('flow', 'Utility.delivery', 'north'),
        Part('value', 'Utility.online', 'north'),
        Part('stage', 'Utility.restore.step[0]', 'north'),
        Part('event', 'Utility.restore', 'north'),
        Part('trigger', 'Utility.restore.when[0]', 'north'),
    ]
    for part, then in pairwise(chain):
        assert then in found.edges[part], (part, then)
    assert not any(part.owner == 'south' for part in found.edges)
    assert found.blocked == {}


def test_a_stage_that_sets_a_flow_s_request_is_part_of_what_its_store_reads():
    """The tank drains at 1 L/h until a stage at 2 h sets the drain's request to 0 L/h: the water
    reads the flow, and the flow the stage that sets it and so the stage's event."""
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        flow('drain', this.water, SINK, request=q(1, 'L/h')),
        event('stop', after(q(2, 'h'), assign(this.drain.request, q(0, 'L/h')))),
    )
    b.setup(start(tank.stop))
    found = reads(b.finish(), Configuration(Request(4)), Key('tank', ('water',)))
    chain = [
        Part('value', 'tank.water', 'tank'),
        Part('flow', 'tank.drain', 'tank'),
        Part('stage', 'tank.stop.step[0]', 'tank'),
        Part('event', 'tank.stop', 'tank'),
    ]
    for part, then in pairwise(chain):
        assert then in found.edges[part], (part, then)


def test_an_event_that_cannot_start_is_blocked_with_its_reason():
    off = Configuration(Request(10), inputs=(InputValue('depot', 'recalls', False),))
    found = reads(_depot(), off, Key('depot', ('delivered',)))
    recall = Part('event', 'depot.recall', 'depot')
    assert recall in found.edges
    assert 'nothing that can happen starts it' in found.blocked[recall]


def test_endpoint_settings_are_read_by_the_flows_that_meet_them():
    b = Builder(UNITS)
    b.entity(
        'reservoir',
        input_('limit', 'L/h', q(10, 'L/h')),
        value('water', 'L', 20, lower=0, outflow=endpoint(capacity=this.limit)),
    )
    b.entity('garden', flow('delivery', named('reservoir').water, SINK, request=q(12, 'L/h')))
    found = reads(b.finish(), RUN, Key('reservoir', ('water',)))
    assert (
        Part('value', 'reservoir.limit', 'reservoir')
        in found.edges[Part('flow', 'garden.delivery', 'garden')]
    )


# ---- what the agent of units left to the proofs (scratch/rewrite/b1/audit2-d/STATE.md, "For C") -----


def spans(given=None):
    """A member whose input `span` is 2.4 h, or as a configuration gives it; a tally that a pump fills
    and a stock that a drain empties; `picked` counts the tally when the span equals 0.1 day and 6 min
    equals 0.1 h, and the stock when either does not."""
    b = Builder(
        {
            'h': {'time': 1},
            'day': ({'time': 1}, 24),
            'min': ({'time': 1}, Fraction(1, 60)),
            'L': {'volume': 1},
        }
    )
    b.entity(
        'm',
        input_('span', 'h', q(2.4, 'h')),
        value('tally', 'L', 0, lower=0),
        value('stock', 'L', 10, lower=0),
        flow('pump', SOURCE, this.tally, request=q(1, 'L/h')),
        flow('drain', this.stock, SINK, request=q(1, 'L/h')),
        value(
            'picked',
            'L',
            formula(
                ifelse((this.span == q(0.1, 'day')) & (q(6, 'min') == q(0.1, 'h')), this.tally, this.stock)
            ),
        ),
    )
    inputs = () if given is None else (InputValue('m', 'span', Quantity(*given)),)
    return b.finish(), Configuration(Request(10), inputs=inputs)


@pytest.mark.parametrize('given', [None, (2.4, 'h'), (0.1, 'day')], ids=['default', 'in hours', 'in days'])
def test_a_proof_reads_each_quantity_at_its_exact_scale(given):
    """0.1 day is 2.4 h and 6 min is 0.1 h exactly, however a default or a configuration writes them (in
    floats, 0.1 * 24 is 2.4000000000000004 h, and 6 times the float of 1/60 is 0.09999999999999999 h):
    `picked` is the tally, which never falls."""
    program, configuration = spans(given)
    proof = never_falls(program, configuration, Key('m', ('picked',)))
    assert proof.holds, proof.reason


def test_a_never_falls_proof_compares_an_expression_at_its_inputs_scale():
    """An input of 1e-12 L with the same declared scale exceeds zero.
    The selected stock drains at 1 L/h. Adding zero to the input must still select it."""
    from napkin.model.compile import compile_text

    model = compile_text(
        """scenario "A stock at a fine resolution"
    horizon 1 h

plant:
    input signal: L = 1e-12 L scale 1e-12 L
    stock: L = 2 L in [0,]
    flow drain: this.stock -> SINK
        request = 1 L/h
    direct = formula(this.stock if this.signal > 0 L else 0 L)
    wrapped = formula(this.stock if this.signal + 0 L > 0 L else 0 L)
""",
        UNITS,
    )
    for name in ('direct', 'wrapped'):
        proof = proved(model.program, 'plant', name, configuration=model.configuration)
        assert not proof.holds, (name, proof.reason)
        assert 'plant.drain' in proof.reason


def test_a_read_through_a_reference_to_an_occurrence_reads_that_occurrence():
    """A check saves a reference to the newest repair and writes the repair's amount into `held`
    through it: what `held` reads is the writing stage and the amount of the repair's occurrences, and
    a lag of the reference is refused by what it is."""
    from tests.language.test_events import LIVES, program_of

    program = program_of(LIVES.format(stage='                this.held = job.amount'))
    found = reads(program, RUN, Key('crew', ('held',)))
    assert Part('stage', 'crew.check.step[0]', 'crew') in found.edges
    assert (
        Part('value', 'crew.repair.amount', 'crew.repair#')
        in found.edges[Part('stage', 'crew.check.step[0]', 'crew')]
    )
    proof = never_falls(program, RUN, Key('crew.check#', ('job',)))
    assert not proof.holds and 'a reference to an occurrence of crew.repair' in proof.reason
