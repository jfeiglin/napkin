"""The bugs that the audit after G2 found in the engine and the report (docs/design/decisions.md, change 19),
each on a small program built by hand, with its expected values worked by hand.

1. A move whose two ends name one store moves nothing: the equal debit and credit cancel.
2. A stage whose commit fails is discarded whole: its writes, its starts and its entry.
3. A stage that replaces a distribution draws from the new one: a stage sees its own writes.
4. Equivalent schedules give one moment: a step due within the time tolerance of a moment, when the
   moment begins, is due at it, so 0.1 h then 0.2 h is 0.3 h, at the horizon too.
5. A flow whose rate the record does not hold is not recorded, never "moved nothing".
6. An edit withdraws the never-falls proof of every value that rests on the edited one.
7. After a pause or a failure, a value is `Unavailable` on every path that reads one.
"""

from __future__ import annotations

import textwrap

import pytest

from napkin.engine.report import Lag, report
from napkin.engine.timeline import Plan, Run, read, run
from napkin.model.compile import compile_text
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    case,
    categorical,
    dist_of,
    draw,
    elapsed,
    event,
    flow,
    formula,
    local,
    move,
    named,
    param,
    q,
    ref_to,
    reset_when,
    start,
    switch,
    t,
    this,
    uniform,
    value,
    when,
)
from napkin.program.checkpoint import Breakpoint
from napkin.program.config import Configuration, Limits, Request
from napkin.program.record import Key, Unavailable
from tests.engine.test_checkpoints import SCENARIOS, UNITS, ticks
from tests.reference.from_program import run_of, value_at

# ---- 1. a move between two names of one store ---------------------------------------------------


def transfer(amount):
    """A crew moves `amount` L at 1 h from the tank of its first argument to the tank of its second,
    and both arguments name the tank `a`, which holds 8 L in [0 L, 20 L]."""
    b = Builder(UNITS)
    tank = b.template('Tank', value('water', 'L', 8, lower=0, upper=20))
    a, _ = b.member(tank, 'a'), b.member(tank, 'b')
    crew = b.entity(
        'crew',
        event(
            'transfer',
            param('origin', ref_to('Tank')),
            param('target', ref_to('Tank')),
            after(q(1, 'h'), move(q(amount, 'L'), local.origin.water, local.target.water)),
        ),
    )
    b.setup(start(crew.transfer, a, a))
    return b.finish(), Configuration(Request(2))


@pytest.mark.parametrize('amount', [3, 10])
def test_a_move_from_a_store_to_itself_leaves_it_as_it_was(amount):
    """The debit and the credit of one store cancel: the tank keeps its 8 L (not 8 + 3 = 11 L), also
    for a move of 10 L, more than it holds, since its resulting inventory is 8 L. The move is in the
    trace once, with its amount."""
    program, configuration = transfer(amount)
    record = run(program, configuration)
    assert record.failure is None
    water, other = read(record, program, ['a.water', 'b.water'], [0, 1, 2])
    assert water.values == (8, 8, 8) and other.values == (8, 8, 8)
    (entry,) = record.entries('move')
    assert (entry.t, entry.detail('amount'), entry.detail('source'), entry.detail('destination')) == (
        1,
        amount,
        'a.water',
        'a.water',
    )


# ---- 2. a stage whose commit fails ------------------------------------------------------------------


def ordering(where, failure):
    """At 1 h a stage of `order` (or, by `where`, the setup at 0 h) gives `pace` (orders + 1) the
    formula orders + 10, writes 5 orders and starts two children, of 3 L and of 9 L; or a trigger of
    the child at 1 h starts the two (a trigger only starts). The second start fails: its size is
    outside the child's range [0 L, 5 L], or (`failure` 'limit', with 4 L) the child may start once.
    `quiet` is the time since `orders` last changed."""
    b = Builder(UNITS)
    depot = this if where != 'setup' else named('depot')
    second = q(9, 'L') if failure == 'range' else q(4, 'L')
    body = (
        assign(depot.pace, formula(depot.orders + 10)),
        assign(depot.orders, 5),
        start(depot.child, q(3, 'L')),
        start(depot.child, second),
    )
    triggers = [when(t >= q(1, 'h'), *body[2:], reset=reset_when(False))] if where == 'firing' else []
    b.entity(
        'depot',
        value('orders', '', 0),
        value('pace', '', formula(this.orders + 1)),
        value('quiet', 'h', formula(elapsed(this.orders))),
        event(
            'child', param('size', 'L', lower=0, upper=5), after(q(1, 'h'), add(this.orders, 1)), *triggers
        ),
        *([event('order', after(q(1, 'h'), *body))] if where == 'stage' else []),
    )
    if where == 'stage':
        b.setup(start(named('depot').order))
    elif where == 'setup':
        b.setup(*body)
    limits = Limits(max_occurrences=1) if failure == 'limit' else Limits()
    return b.finish(), Configuration(Request(3), limits=limits)


@pytest.mark.parametrize('failure', ['range', 'limit'])
@pytest.mark.parametrize('where', ['stage', 'setup', 'firing'])
def test_a_stage_whose_second_start_fails_is_discarded_whole(where, failure):
    """The run fails when the second child starts (at 1 h, or at 0 h in the setup). Nothing of the
    stage is in its record: at the failure the orders stay 0, `pace` keeps its formula (0 + 1, not
    0 + 10) and `quiet` counts from the start; the first child never started, and the trace has no
    commit, firing or start of it; it ends with the failure."""
    program, configuration = ordering(where, failure)
    at = 0 if where == 'setup' else 1
    record = run(program, configuration)
    assert record.failure is not None and record.failure.t == at
    message = record.failure.detail('message')
    assert ('outside its range' if failure == 'range' else 'max_occurrences') in message
    found = read(record, program, ['depot.orders', 'depot.pace', 'depot.quiet'], [at])
    assert [reading.values for reading in found] == [(0,), (1,), (at,)]
    # The histories that the record holds say the same, read without the engine's reader.
    held = [record.value(Key('depot', (name,)), at) for name in ('orders', 'pace', 'quiet')]
    assert held == [0, 1, pytest.approx(at)]
    assert not record.entries('start', 'depot.child')
    assert not record.entries('commit', 'depot.order.step[0]') and not record.entries('fire')
    assert record.trace[-1] == record.failure
    assert not [history for history in record.histories if history.key.owner.startswith('depot.child#')]
    (size,) = read(record, program, ['depot.child#0.size'], [at])
    assert isinstance(size.values[0], Unavailable)


def test_an_edit_in_a_stage_whose_commit_fails_is_discarded_with_it():
    """Stopped before its start, the stage at 1 h gets an edit of the tank, 8 L to 10 L, which joins
    its writes; resumed, its start of 9 L fails. The tank holds 8 L at the failure, its books hold no
    transfer from outside, and the trace has no edit and no commit."""
    b = Builder(UNITS)
    b.entity(
        'depot',
        value('water', 'L', 8, lower=0),
        value('count', '', 0),
        flow('drain', this.water, SINK, request=q(0, 'L/h')),
        event('child', param('size', 'L', lower=0, upper=5), after(q(1, 'h'))),
        event('order', after(q(1, 'h'), add(this.count, 1), start(this.child, q(9, 'L')))),
    )
    b.setup(start(named('depot').order))
    program, configuration = b.finish(), Configuration(Request(3))
    made = Run(Plan.of(program, configuration), (Breakpoint('depot.order.step[0].do[1]'),))
    made.run()
    made.edit('depot.water', 10)
    record = made.resume()
    assert record.failure is not None and record.failure.t == 1
    found = read(record, program, ['depot.water', 'depot.water.external', 'depot.count'], [1])
    assert [reading.values for reading in found] == [(8,), (0,), (0,)]
    assert not record.entries('edit') and not record.entries('commit')


# ---- 3. a draw from a distribution that the stage replaced ----------------------------------------


def replacing():
    """At 1 h a stage replaces `demand_of`, uniform(1 L, 3 L), by uniform(10 L, 20 L), then draws from
    it and reads its mean; and replaces `pick`, which always gives A, by one that always gives B,
    then switches on a draw of it."""
    b = Builder(UNITS)
    choice = b.enum('enum[A, B]', 'A', 'B')
    depot = b.entity(
        'depot',
        value('demand_of', dist_of('L'), uniform(1, 3, 'L')),
        value('pick', dist_of(choice), categorical(choice, A=1, B=0)),
        value('demand', 'L', 0),
        value('mean', 'L', 0),
        value('a', '', 0),
        value('b', '', 0),
        event(
            'order',
            after(
                q(1, 'h'),
                assign(this.demand_of, uniform(10, 20, 'L')),
                assign(this.demand, draw(this.demand_of)),
                assign(this.mean, this.demand_of.mean),
                assign(this.pick, categorical(choice, A=0, B=1)),
                switch(draw(this.pick), case(choice.A, add(this.a, 1)), case(choice.B, add(this.b, 1))),
            ),
        ),
    )
    b.setup(start(depot.order))
    return b.finish(), Configuration(Request(2))


def test_a_stage_draws_from_the_distribution_that_it_gave_a_value():
    """A median run draws the median of uniform(10 L, 20 L), 15 L (not 2 L), reads its mean, 15 L, and
    the switch takes B, the only outcome of the new distribution with a weight. The oracle agrees."""
    program, configuration = replacing()
    record = run(program, configuration)
    assert record.failure is None
    found = read(record, program, ['depot.demand', 'depot.mean', 'depot.a', 'depot.b'], [2])
    assert [reading.values for reading in found] == [(15,), (15,), (0,), (1,)]
    oracle, failure = run_of(program, configuration)
    assert failure is None
    exact = {name: value_at(oracle, program, Key('depot', (name,)), 2) for name in ('demand', 'mean', 'b')}
    assert exact == {'demand': 15, 'mean': 15, 'b': 1}


# ---- 4. equivalent schedules ----------------------------------------------------------------------


def schedules(horizon, chained_first):
    """`chained` waits 0.1 h and then 0.2 h and sets `last` to 1; `direct` waits 0.3 h and sets it to 2;
    each adds to `done` (1 and 10). The setup starts them in the order given."""
    b = Builder(UNITS)
    crew = b.entity(
        'crew',
        value('done', '', 0),
        value('last', '', 0),
        event('chained', after(q(0.1, 'h')), after(q(0.2, 'h'), add(this.done, 1), assign(this.last, 1))),
        event('direct', after(q(0.3, 'h'), add(this.done, 10), assign(this.last, 2))),
    )
    order = (start(crew.chained), start(crew.direct))
    b.setup(*(order if chained_first else order[::-1]))
    return b.finish(), Configuration(Request(horizon))


def test_a_step_due_by_two_waits_runs_at_the_horizon_as_one_due_by_one_wait():
    """0.1 h + 0.2 h is 0.3 h, the horizon: both stages run there, in one round (done = 11)."""
    program, configuration = schedules(0.3, True)
    record = run(program, configuration)
    (done,) = read(record, program, ['crew.done'], [0.3])
    assert done.values == (11,)
    commits = [(entry.t, entry.round) for entry in record.entries('commit') if entry.part.endswith('step[1]')]
    commits += [(entry.t, entry.round) for entry in record.entries('commit', 'crew.direct.step[0]')]
    assert commits == [(0.3, 1), (0.3, 1)]


@pytest.mark.parametrize('chained_first', [True, False])
def test_two_steps_due_at_one_time_by_different_sums_commit_in_one_round(chained_first):
    """Both stages are due at 0.3 h and commit in one round, in the order in which their occurrences
    were made (D5): the later one sets `last`. The oracle, in exact numbers, agrees."""
    program, configuration = schedules(1, chained_first)
    record = run(program, configuration)
    (last,) = read(record, program, ['crew.last'], [1])
    assert last.values == ((2,) if chained_first else (1,))
    oracle, failure = run_of(program, configuration)
    assert failure is None and value_at(oracle, program, Key('crew', ('last',)), 1) == last.values[0]


# ---- 5. a flow that the record does not hold -------------------------------------------------------

TANK = """
    scenario "Tank"
        horizon 2 h
    tank:
        water: kL = 8 kL in [0 kL,]
    clinic:
        flow delivery: tank.water -> SINK
            request = 1.5 kL/h
    """


@pytest.mark.parametrize('everything', [True, False])
def test_a_flow_that_the_record_does_not_hold_is_not_recorded(everything):
    """The tank falls from 8 kL to 5 kL in 2 h. With every value recorded, the delivery moved material;
    with only the tank recorded, its rate is not in the record: the trail says that it is not
    recorded, and claims neither way."""
    model = compile_text(textwrap.dedent(TANK), {**UNITS, 'kL': ({'volume': 1}, 1000)})
    keys = () if everything else (Key('tank', ('water',)),)
    configuration = Configuration(Request(2, everything, keys))
    record = run(model.program, configuration)
    (water,) = report(record, model.program, configuration, ['tank.water'], [2], model=model.declared).values
    assert water.values == pytest.approx((5,))
    (delivery,) = [used for used in water.trail if (used.kind, used.origin) == ('flow', 'clinic.delivery')]
    if everything:
        assert (delivery.exercised, delivery.why) == (True, 'it moved material')
    else:
        assert delivery.exercised is None and delivery.why.startswith('not recorded')
        assert 'moved nothing' not in delivery.why


# ---- 6. an edit withdraws the proofs that rest on the edited value --------------------------------


def pouring():
    """1 L/h pours from `full` (10 L) into a tally `served` (0 L); `gap = served - full` and
    `doubled = 2 served` never fall. A tick at 2 h, where a breakpoint stops the run."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('full', 'L', 10, lower=0),
        value('served', 'L', 0, lower=0),
        value('gap', 'L', formula(this.served - this.full)),
        value('doubled', 'L', formula(this.served * 2)),
        value('ticks', '', 0),
        flow('pour', this.full, this.served, request=q(1, 'L/h')),
        ticks(2),
    )
    b.setup(start(named('tank').tick))
    return b.finish(), Configuration(Request(4))


def edited(program, configuration, target, new):
    """The record of the run edited at its stop at 2 h: `target` takes `new` L."""
    made = Run(Plan.of(program, configuration), (Breakpoint('tank.tick.step[0]'),))
    made.run()
    made.edit(target, new)
    return made.resume()


LAGS = {'tank.gap': Lag(0.5, 1), 'tank.doubled': Lag(0.5, 1)}


def lagged(record, program, configuration):
    return report(record, program, configuration, list(LAGS), [4], LAGS).values


def test_a_lag_of_a_formula_holds_while_no_edit_breaks_what_it_rests_on():
    """Untouched, both formulas never fall: their lags hold. At 4 h `gap` = 4 - 6 = -2 L, lagged over
    [3 h, 3.5 h]: its mean, -2 - 2 * 0.75 = -3.5 L; `doubled` = 2 * 3.25 = 6.5 L."""
    program, configuration = pouring()
    gap, doubled = lagged(run(program, configuration), program, configuration)
    assert gap.lag == doubled.lag == Lag(0.5, 1)
    assert gap.values == pytest.approx((-3.5,)) and doubled.values == pytest.approx((6.5,))


@pytest.mark.parametrize(
    ('target', 'new', 'refused'),
    [
        ('tank.served', 1, {'tank.gap': 'lowered tank.served from 2 to 1 L', 'tank.doubled': 'lowered'}),
        ('tank.served', 3, {'tank.gap': None, 'tank.doubled': None}),
        ('tank.full', 7, {'tank.gap': None, 'tank.doubled': None}),
        ('tank.full', 9, {'tank.gap': 'raised tank.full from 8 to 9 L', 'tank.doubled': None}),
    ],
)
def test_an_edit_withdraws_the_proof_of_each_formula_that_rests_on_it(target, new, refused):
    """At 2 h `full` holds 8 L and `served` 2 L. An edit that lowers `served`, which both formulas count,
    or raises `full`, which `gap` subtracts, withdraws their proofs for the run, and the note says which
    edit; one that raises `served` or lowers `full` keeps every proof. A refused lag is the plain read."""
    program, configuration = pouring()
    record = edited(program, configuration, target, new)
    full, served = {'tank.full': (new, 2), 'tank.served': (8, new)}[target]
    plain = {'tank.gap': (served + 2) - (full - 2), 'tank.doubled': 2 * (served + 2)}
    for found in lagged(record, program, configuration):
        why = refused[found.path]
        if why is None:
            assert found.lag == Lag(0.5, 1)
        else:
            assert found.lag is None and found.values == pytest.approx((plain[found.path],))
            assert f'{found.path} can fall: an edit at 2 h, at tank.tick.step[0], ' in found.note
            assert why in found.note


# ---- 7. a value after a pause or a failure ---------------------------------------------------------


def test_a_value_after_a_pause_is_unavailable_on_every_path():
    """The family's tank of 10 L drains at 2 L/h; the run stops at its tick at 2 h, with 6 L. At 1 h and
    2 h it holds 8 L and 6 L; at 4 h `read`, a formula and the record itself give `Unavailable` with
    the reason, not the 6 L held at the stop."""
    case_ = SCENARIOS['family']()
    stopped = run(case_.program, case_.configuration, (Breakpoint('tank.tick.step[1]'),))
    record = stopped.record
    water, external = read(record, case_.program, ['tank.water', 'tank.water.external'], [1, 2, 4])
    assert water.values[:2] == pytest.approx((8, 6)) and external.values[:2] == (0, 0)
    for found in (water.values[2], external.values[2], record.value(Key('tank', ('water',)), 4)):
        assert isinstance(found, Unavailable)
        assert found.reason.startswith('the run stopped at 2 h at the breakpoint tank.tick.step[1]')
    assert record.value(Key('tank', ('water',)), 2) == pytest.approx(6)


def test_a_value_after_a_failure_is_unavailable():
    """A tank of 0 L fills at 1 L/h, and at 5 h a stage gives it -1 L, outside its range: the run fails.
    At 4 h and 5 h it holds 4 L and 5 L; at 6 h a read is unavailable with the failure."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 0, lower=0),
        value('doubled', 'L', formula(this.water * 2)),
        flow('fill', SOURCE, this.water, request=q(1, 'L/h')),
        event('check', after(q(5, 'h'), assign(this.water, q(-1, 'L')))),
    )
    b.setup(start(named('tank').check))
    program = b.finish()
    record = run(program, Configuration(Request(8)))
    assert record.failure is not None and record.failure.t == 5
    water, doubled = read(record, program, ['tank.water', 'tank.doubled'], [4, 5, 6])
    assert water.values[:2] == pytest.approx((4, 5)) and doubled.values[:2] == pytest.approx((8, 10))
    for found in (water.values[2], doubled.values[2], record.value(Key('tank', ('water',)), 6)):
        assert isinstance(found, Unavailable) and found.reason.startswith('the run failed at 5 h: ')


def test_a_drain_with_no_pause_reads_to_its_horizon():
    """A run to its horizon reads every time up to it: 10 L draining at 2 L/h holds 2 L at 4 h."""
    b = Builder(UNITS)
    b.entity('tank', value('water', 'L', 10, lower=0), flow('drain', this.water, SINK, request=q(2, 'L/h')))
    program = b.finish()
    record = run(program, Configuration(Request(4)))
    assert read(record, program, ['tank.water'], [4])[0].values == pytest.approx((2,))
    assert record.value(Key('tank', ('water',)), 4) == pytest.approx(2)
