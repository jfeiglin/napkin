"""E12: evidence lineage. Outcomes trace to the parts and records behind them; records are pinned by
digest; a review is bound to the value it reviewed; references and data are checked.

The evidence trail of a run reads the run's whole structure (`model.whole`) and the parts that the
run's structure leaves out (`model.left_out`): `napkin.engine.report.run_evidence`, which
the report of a study holds for each run.
"""

from __future__ import annotations

import copy

import pytest

import napkin.engine.report as report
from napkin.engine import evaluate_study, sample_result
from napkin.engine.runtime import simulate
from napkin.expressions import UnitSystem
from napkin.model import ModelError
from napkin.model.ir import thaw
from tests.acceptance.helpers import LIBRARY, RUN, fixture, model_of
from tests.build import (
    append,
    block,
    compiled,
    edit,
    event,
    in_place,
    library,
    member,
    named,
    named_event,
    parameter,
    replace,
    scenario,
)
from tests.evidence.support import resting


def trail_of(model, lib, run=RUN):
    """The evidence trail of one run of a model, with its own values."""
    rs = model.resolve(run)
    trajectory = simulate(rs, lib)
    return report.run_evidence(model, rs, trajectory, lib, UnitSystem(lib['units']))


# F5 with the operators' decision and the output `pumped` resting on an assumption of the library,
# T_VINTAGE; every other line keeps the identity record `fixture`.
VINTAGE = (
    replace('when count(notice) > 0:  @fixture', 'when count(notice) > 0:  @vintage'),
    replace('output pumped: L = basin.held  @fixture', 'output pumped: L = basin.held  @vintage'),
    append('record vintage: assumption T_VINTAGE "Synthetic decision and report lag."'),
)


def test_an_outcome_traces_to_rules_values_and_records():
    # pumped reads the water of the buckets, which the pumps take from the basin. The drain fills the
    # basin at its rate while it is open: the start opens it and the decision closes it, and the log
    # of a spill takes from the basin. In the run `closing` each of these rules fires.
    trail = sample_result(evaluate_study(model_of('F5', VINTAGE)), [9])['runs'][RUN]['evidence']
    pumped = trail['outcomes']['pumped']
    assert {
        'attacker.start',
        'operators.decide',
        'basin.log',
        'basin.water',
        'tank.drain_rate',
    } <= set(pumped['exercised'])
    assert pumped['basis']['assumption'] == 'T_VINTAGE'
    assert trail['parts']['operators.decide']['assumption'] == 'T_VINTAGE'
    assert trail['parts']['tank.water'] == {'name': 'fixture', 'kind': 'identity'}
    assert set(trail['records']) == {'T_VINTAGE'}


def test_a_rule_that_never_fired_is_possible_not_exercised():
    # The operators wait: their decision fired, with its outcome `wait`, and the log of a spill, which
    # only the outcome `close` fires, never did. The log takes from the basin.
    trail = trail_of(model_of('F5'), LIBRARY, 'waiting')['outcomes']['basin_water']
    assert 'operators.decide' in trail['exercised']
    assert 'basin.log' in trail['possible']


def delivered_trail(text):
    """The trail of the fixture's `delivered` output in its run `a`."""
    lib = library()
    return trail_of(compiled(text, lib), lib, 'a')['outcomes']['delivered']


def with_locked_stop(text, unlock=False):
    """An early stop that needs the service `locked`. Only a lock event, which happens after the
    horizon, could lock it. The stop and the early stop switch the service off with one event that only
    the lines that name it fire."""
    values = [named('lock', 'open', 'locked'), parameter('early', 6, 'h')]
    events = [
        event(
            'early_stop',
            'lock is "locked" and t >= early',
            'switch_off',
            once=False,
            transition='state "on" -> "off"',
            doc='Early stop',
        )
    ]
    if unlock:
        values.append(parameter('lock_time', 2 * compiled(text).time['horizon'], 'h'))
        events.append(
            event('lock_up', 't >= lock_time', once=False, transition='lock "open" -> "locked"', doc='Lock')
        )
    return edit(
        text,
        member('service/stop', 'switch_off'),
        member('service', *values, *events, named_event('switch_off', 'state = "off"', records=None)),
    )


def test_a_rule_that_can_never_fire_is_possible_with_what_only_it_reads():
    trail = delivered_trail(with_locked_stop(scenario()))
    assert {'service.early_stop', 'service.early'} <= set(trail['possible'])
    assert {'service.stop', 'service.end'} <= set(trail['exercised'])


def test_a_rule_that_could_fire_keeps_what_it_reads_when_it_does_not_fire():
    # Neither the lock nor the early stop fires before the horizon, but other inputs would let them.
    trail = delivered_trail(with_locked_stop(scenario(), unlock=True))
    assert {'service.early_stop', 'service.lock_up'} <= set(trail['possible'])
    assert {'service.early', 'service.lock_time'} <= set(trail['exercised'])


def test_an_input_that_keeps_a_flow_still_is_exercised():
    text = edit(
        scenario(),
        replace('= rate if state is "on"', '= rate * share if state is "on"'),
        member('service', parameter('share', 0, 'fraction')),
    )
    trail = delivered_trail(text)
    assert 'service.serve' in trail['possible']
    assert 'service.share' in trail['exercised']


def test_a_record_revision_changes_its_digest_and_nothing_else():
    revised = copy.deepcopy(LIBRARY)
    next(a for a in revised['assumptions'] if a['id'] == 'T_VINTAGE')['statement'] += ' Revised.'
    before = trail_of(model_of('F5', VINTAGE), LIBRARY)
    after = trail_of(model_of('F5', VINTAGE, library=revised), revised)
    assert before['records']['T_VINTAGE'] != after['records']['T_VINTAGE']
    assert before['library'] != after['library']
    assert before['outcomes'] == after['outcomes']


def test_a_record_has_no_review_of_its_applicability():
    """A record is its kind, its explanation and its claims: a line `applicability:` under it is not a
    line of the language."""
    record = block(
        in_place('identity', 'Analytic contract fixture.'), block('applicability:', 'fingerprint: x')
    )
    with pytest.raises(ModelError, match='claims:') as raised:
        compiled(resting(scenario(), 'service/end', record))
    assert [d['code'] for d in raised.value.diagnostics] == ['syntax']


@pytest.mark.parametrize(
    'basis',
    [
        in_place('source', 'Cites a missing claim.', 'T_MISSING'),
        in_place('assumption', 'Cites a missing assumption.', assumption='T_MISSING'),
    ],
    ids=['basis0', 'basis1'],
)
def test_a_missing_record_is_rejected_with_its_location(basis):
    with pytest.raises(ModelError) as caught:
        model_of(resting(fixture('F5'), 'tank/drain_rate', basis))
    found = [d for d in caught.value.diagnostics if d['code'] == 'provenance']
    assert found and found[0]['path'].startswith('tank/drain_rate') and found[0].get('line')


# The fixture's service with the title Service, its name on the pages under any other name.
TITLED = replace('    role operator\n', '    title "Service"\n    role operator\n')


def test_a_name_that_a_file_chooses_never_holds_a_basis():
    """Only the lines of the language hold records. A value, an event, a profile, an entity, an output
    and a run named `basis`, `distinct`, `together` or `before` are ordinary names: with them, each use
    of a record stays where it was, and no name becomes a use. Both files give the entity the title
    Service, so that it keeps its label and each line keeps its row."""
    base = edit(scenario(), TITLED)
    text = edit(
        base,
        replace('\nservice:', '\ndistinct:'),
        replace('input n:', 'input basis:'),
        replace('input rate:', 'input distinct:'),
        replace('input end:', 'input together:'),
        replace('var stock: people = n ', 'var stock: people = basis '),
        replace('= rate if', '= distinct if'),
        replace('event stop when', 'event before when'),
        replace('t >= end:', 't >= together:'),
        replace('served is n ', 'served is basis '),
        replace('assert service.end', 'assert distinct.together'),
        replace('output delivered: people = service.served', 'output together: people = distinct.served'),
        replace('"Half rate":', '"basis":'),
        replace('service.rate =', 'distinct.distinct ='),
        replace('b = "Default" + "Half rate"', 'before = "Default" + "basis"'),
    )
    renamed = {
        'distinct': 'service',
        'distinct/basis': 'service/n',
        'distinct/distinct': 'service/rate',
        'distinct/together': 'service/end',
        'distinct/stock': 'service/stock',
        'distinct/served': 'service/served',
        'distinct/delivery': 'service/delivery',
        'distinct/before': 'service/stop',
        'distinct/serve': 'service/serve',
        'distinct/assert:/0': 'service/assert:/0',
        'output:/together': 'output:/delivered',
        'options:/Rate/basis/distinct.distinct': 'options:/Rate/Half rate/service.rate',
    }
    uses = [
        {**use, 'part': renamed.get(use['part'], use['part'])} for use in thaw(compiled(text).index)['uses']
    ]
    assert uses == thaw(compiled(base).index)['uses']


def _datum_source(value, unit):
    """F5 with a fixed inventory whose record cites the exact datum `inventory` of a claim."""
    datum = in_place('source', 'The synthetic exact inventory datum.', block('T_DATUM', 'datum: inventory'))
    return edit(fixture('F5'), member('tank', block(f'let inventory = {value} {unit}', datum)))


def test_a_datum_matches_after_unit_conversion_only():
    model_of(_datum_source(0.1, 'm3'))
    model_of(_datum_source(100, 'L'))
    with pytest.raises(ModelError) as caught:
        model_of(_datum_source(80, 'L'))
    assert any(d['code'] == 'evidence_value' for d in caught.value.diagnostics)
