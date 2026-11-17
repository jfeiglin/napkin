"""The evidence trail of a run reads the model's whole structure (docs/engine.md, "The evidence trail").

A synthetic attacker with kept access switches a service off after its reaction time; responders
switch it back on a notice delay after that. Without kept access, the attacker's trigger cannot fire,
and the responders' trigger waits for an event that never happens: the run's structure leaves both
out. The trail must still show their evidence as possible, not used, and must not count what only
they read as used. The service serves one person an hour while it is on, so with kept access it serves
horizon - notice_delay people.
"""

from __future__ import annotations

import textwrap

import pytest

from napkin.engine import evaluate_study, sample_result
from napkin.engine.report import evidence_trail, firing_rules
from napkin.expressions import UnitSystem
from napkin.model.ir import thaw
from napkin.model.structure import Resolved
from tests.build import compiled, evidence_library, flow, output, parameter, stock, system

LIBRARY = evidence_library()
# A selected assumption of the library supports the attacker's move, so the trail cites a record.
ASSUMPTION = LIBRARY['assumptions'][0]['id']

FIXTURE = textwrap.dedent(
    """\
    scenario "Trail fixture"
        summary "A synthetic attacker switches a service off. A fixture for tests only."
        horizon 48 h
        scope "Synthetic people."

    switch:  @ident
        "The switch that feeds the service."
        role operator
        var position: "on" | "off" = "on"
        event turn_on:
            position = "on"

    service:  @ident
        "A service that serves while its switch is on."
        role operator
        var served: people = 0  @ident
            "People served"
        output served
        flow serve: -> served at 1 people/h while switch.position is "on"  @ident
            "The service serves."

    attacker:  @ident
        "A synthetic attacker."
        role operator
        var access: "none" | "kept" = "none"
        input reaction_time = 6 h in 1 h to 12 h  @ident
            "Time to react"
        event jam_switch once when access is "kept" and t >= reaction_time:  @attack
            "The attacker switches the service off."
            switch.position = "off"

    responders:  @ident
        "Responders who switch the service back on."
        role responder
        input notice_delay = 10 h in 1 h to 24 h  @ident
            "Time to notice"
        event restore once when count(attacker.jam_switch) > 0 and since(attacker.jam_switch) >= notice_delay:
            @ident
            "Responders switch the service back on."
            switch.turn_on

    options "Response":
        "Default":
            "The defaults."

    options "Access":
        "No access":
            "The attacker cannot act."
        "Keeps access":
            "The attacker keeps its access."
            attacker.access = "kept"  @ident

    runs:
        plain = "Default" + "No access"
        kept = "Default" + "Keeps access"

    record ident: identity "Synthetic test fixture."
    record attack: assumption ASSUMPTION "Synthetic move."
"""
).replace('ASSUMPTION', ASSUMPTION)
LEFT_OUT = {'attacker.jam_switch', 'responders.restore'}
READ_ONLY_BY_THEM = {'attacker.reaction_time', 'responders.notice_delay'}


@pytest.fixture(scope='module')
def model():
    return compiled(FIXTURE, LIBRARY, 'trail.scn')


@pytest.fixture(scope='module')
def report(model):
    study = evaluate_study(model)
    assert study.admissible, study.diagnostics
    return study, sample_result(study)


def served(model, run):
    return model.outputs['service.served']


def test_the_structure_without_access_leaves_out_both_triggers(model):
    """The precondition of this file: the builder leaves both triggers out of the run without access,
    and the engine's own firing analysis of the whole structure lets the responders' trigger fire,
    because it follows no events."""
    starts = model.runs['plain']['starts']
    assert set(model.left_out[starts]['rules']) >= LEFT_OUT
    assert set(model.whole[starts].rules) >= LEFT_OUT
    assert 'responders.restore' in firing_rules(model.whole[starts])
    assert not LEFT_OUT & set(model.left_out[model.runs['kept']['starts']].get('rules', {}))


def test_the_run_without_access_shows_the_evidence_of_what_it_leaves_out_as_possible(model, report):
    _, sampled = report
    trail = sampled['runs']['plain']['evidence']['outcomes'][served(model, 'plain')]
    assert set(trail['possible']) >= LEFT_OUT | READ_ONLY_BY_THEM
    assert not (LEFT_OUT | READ_ONLY_BY_THEM) & set(trail['exercised'])
    assert ASSUMPTION in sampled['runs']['plain']['evidence']['records']
    # The service's own flow and switch did act: a flow from outside is the rate of its tally.
    assert {'service.served', 'switch.position'} <= set(trail['exercised'])


def test_the_run_with_access_uses_the_same_parts(model, report):
    study, sampled = report
    trail = sampled['runs']['kept']['evidence']['outcomes'][served(model, 'kept')]
    assert set(trail['exercised']) >= LEFT_OUT | READ_ONLY_BY_THEM
    values = study.runs['kept']['resolved'].parameter_values
    final = sampled['runs']['kept']['reporting_points']['final']['values'][served(model, 'kept')]
    assert final == pytest.approx(model.time['horizon'] - values['responders.notice_delay'], rel=1e-9)


def test_without_the_rule_the_trail_would_count_a_part_left_out_as_used(model, report):
    """The counterexample: over the whole structure without the parts left out, the engine's firing
    analysis keeps the responders' trigger, and the trail counts the notice delay, which only that
    trigger reads, as used. The rule of the parts left out makes it possible."""
    study, sampled = report
    completed = study.runs['plain']
    starts = model.runs['plain']['starts']
    whole = Resolved.of({**completed['resolved'].plain(), **model.whole[starts].plain()})
    units = UnitSystem(LIBRARY['units'])
    oid = served(model, 'plain')
    without = evidence_trail(whole, completed['trajectory'], LIBRARY, units)['outcomes'][oid]
    assert 'responders.notice_delay' in without['exercised']
    assert (
        sampled['runs']['plain']['evidence']['outcomes'][oid]
        == evidence_trail(whole, completed['trajectory'], LIBRARY, units, thaw(model.left_out[starts]))[
            'outcomes'
        ][oid]
    )


def test_an_outcome_rests_on_the_inputs_that_the_bounds_of_its_stock_read():
    """A stock is held between two inputs, `low` and `cap`. A resolved run has the number of each
    bound; the evidence of a run reads the whole structure, where each bound is the expression of
    the file. So the output of that stock rests on both inputs, and not on an input that no part
    reads; the output of a stock with no such bound rests on none of the three."""
    source = system(
        parameter('cap', 40, 'people', 10, 80, doc='Cap'),
        parameter('low', 0, 'people', 0, 5, doc='Low'),
        parameter('other', 3, 'people', 0, 5, doc='Other'),
        stock('held', 20, minimum='low', maximum='cap', doc='Held'),
        stock('free', 20, doc='Free'),
        flow('fill', '-> held', '1 people/h'),
        horizon=5,
        outputs=(
            output('held', 's.held', 'people', 'level', doc='Held'),
            output('free', 's.free', 'people', 'level', doc='Free'),
        ),
    )
    outcomes = sample_result(evaluate_study(compiled(source)))['runs']['a']['evidence']['outcomes']

    def rests_on(name):
        return set(outcomes[name]['exercised']) | set(outcomes[name]['possible'])

    assert {'s.low', 's.cap'} <= rests_on('held') and 's.other' not in rests_on('held')
    assert not {'s.low', 's.cap', 's.other'} & rests_on('free')
