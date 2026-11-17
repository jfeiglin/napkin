"""Parts and checks that only some sets of start states have.

The file has every entity and part in every run. The structure of a set of start-state profiles
leaves out the parts that cannot act from those start values, and an output reads zero for a stock
that it leaves out (docs/python-api.md, "The parts that cannot act"). A check that reads a start value
applies only with the profiles that set it.

They build MODELTEST (tests/model/modeltest.py): the attacker switches a service off at t = 0; with the
profile "Keeps access" it jams the switch `reaction_time` after the repair, unless the responders
remove it first. Every expectation is a closed form of inputs read from the model.
"""

from __future__ import annotations

import pytest

from napkin.core.expr import text as written
from napkin.engine import edits_for, evaluate_study
from napkin.engine.report import evaluate_outputs
from napkin.engine.runtime import simulate
from napkin.model import ModelError
from napkin.model.language import front
from napkin.model.language.resolve import arguments, resolve
from napkin.model.model import built
from napkin.model.runs import Runs
from tests.build import (
    append,
    block,
    check,
    edit,
    entity,
    event,
    formula,
    member,
    named,
    output,
    replace,
    stock,
)
from tests.model.modeltest import FIXTURE, LIB, build, run, times


def output_at(model, name, output, t, whole=False):
    """The value of an output of the file at time t in a run: of the run's structure, or of the whole
    structure of its start states, with every part (`whole`)."""
    if whole:
        numbers, errors = model.numbers(model.run_values(name))
        assert not errors
        every_part = model.whole[model.runs[name]['starts']]
        rs = model.resolve_in(every_part, numbers, f'whole {name}')
        trajectory = simulate(rs, LIB)
    else:
        rs, trajectory = run(model, name)
    (row,) = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, LIB, [t])
    return row['values'][model.outputs[output]]


def jam_time(model):
    values = model.run_values('slow_kept')
    return values['service.repair_time'] + values['attacker.reaction_time']


# ---- a stock that cannot change in the runs of a structure -------------------------------------------

# A tally of the hours the switch stays jammed, and an output that reads it.
WITH_JAM_HOURS = (
    member(
        'attacker',
        stock(
            'jam_hours',
            0,
            'h',
            minimum=None,
            size=None,
            kind='tally',
            doc='Hours the switch stays jammed',
            records='@ident',
            rate='1 if switch.position is "jammed" else 0',
        ),
    ),
    append(
        output('jammed', 'attacker.jam_hours', 'h', doc='Hours the switch stays jammed', records='@ident')
    ),
)


def test_a_structure_whose_runs_never_change_a_stock_runs_without_it(tmp_path):
    """Without the access the switch is never jammed, so the tally never grows."""
    model = build(tmp_path, *WITH_JAM_HOURS)
    assert 'attacker.jam_hours' in model.left_out[()]['quantities']
    assert 'attacker.jam_hours' not in model.structure_of('slow').quantities
    assert 'attacker.jam_hours' in model.structure_of('slow_kept').quantities
    assert not model.left_out[('Keeps access',)]['quantities']


def test_an_output_reads_zero_where_its_stock_is_left_out(tmp_path):
    model = build(tmp_path, *WITH_JAM_HOURS)
    assert written(model.structure_of('slow').outcomes[model.outputs['jammed']].expr) == "q(0, 'h')"
    removal = model.run_values('slow_kept')['responders.removal_time']
    # The jam lands before 120 h and the removal does not undo it.
    assert jam_time(model) < 120.0 < removal + 200
    for name, expected in (('slow', 0.0), ('slow_kept', 120.0 - jam_time(model))):
        assert output_at(model, name, 'jammed', 120.0) == pytest.approx(expected, abs=1e-6), name


def test_leaving_out_a_part_that_cannot_act_changes_no_number(tmp_path):
    """A run of the whole structure, with every part, gives the run's own numbers."""
    model = build(tmp_path, *WITH_JAM_HOURS)
    for name in ('slow', 'slow_kept'):
        for output_name in ('jammed', 'service.served'):
            ran = output_at(model, name, output_name, 150.0)
            whole = output_at(model, name, output_name, 150.0, whole=True)
            assert ran == pytest.approx(whole, rel=1e-9, abs=1e-9), (name, output_name)


# ---- an entity that cannot act in the runs of a structure -------------------------------------------


def with_observer(*members):
    """An edit step: an observer that notes the jam, an entity that only the runs with access need,
    with `members` after its state."""
    observer = entity(
        'observer',
        named('seen', 'no', 'yes'),
        *members,
        event(
            'notes_jam',
            'switch.position is "jammed"',
            once=False,
            transition='seen "no" -> "yes"',
            doc='The observer sees the jam.',
            records='@ident',
        ),
        doc='Notes that the switch is jammed.',
        role='operator',
        records='@ident',
    )
    return replace('options "Response":', observer + '\n\noptions "Response":')


def test_a_structure_whose_runs_never_need_an_entity_leaves_it_out(tmp_path):
    model = build(tmp_path, with_observer())
    assert 'observer' in model.left_out[()]['entities']
    assert 'observer' not in model.structure_of('slow').entities
    assert 'observer' in model.structure_of('slow_kept').entities
    _, trajectory = run(model, 'slow_kept')
    assert times(trajectory, model.events['observer.notes_jam.done']) == pytest.approx([jam_time(model)])


def with_watcher(condition):
    """The steps of an edit: a watcher that looks at the switch at 150 h. Its first outcome notes
    the jam, and can happen only while `condition` holds; its chance is a formula, which is zero
    when the switch is not jammed. A tally counts the hours after the watcher noted the jam, and an
    output reads it."""
    watcher = entity(
        'watcher',
        named('noted', 'no', 'yes'),
        formula('share', '1 if switch.position is "jammed" else 0', 'fraction', records='@ident'),
        stock(
            'noted_hours',
            0,
            'h',
            minimum=None,
            size=None,
            kind='tally',
            doc='Hours since the watcher noted the jam',
            records='@ident',
            rate='1 if noted is "yes" else 0',
        ),
        block(
            'event look once when t >= 150 h:  @ident',
            '"The watcher looks at the switch."',
            block(f'sees share{condition}:', 'noted = "yes"'),
            block('misses else:'),
        ),
        doc='Looks at the switch one time.',
        role='operator',
        records='@ident',
    )
    reads = output('noted', 'watcher.noted_hours', 'h', doc='Hours since the jam was noted', records='@ident')
    return replace('options "Response":', watcher + '\n\noptions "Response":'), append(reads)


def test_an_outcome_that_can_never_be_available_cannot_happen(tmp_path):
    """The outcome `sees` can happen only while the switch is jammed (`when`). Without the access
    the switch is never jammed, so in that structure the outcome cannot happen, the watcher never
    notes a jam, and the tally of the hours after it is left out. With the access the tally is a
    part, and it counts the hours from the look at 150 h to the horizon of 200 h.

    The chance of the outcome is a formula, which says nothing to the reader of the start states:
    with no condition on the outcome, the structure without the access keeps the tally. In each
    run the numbers are the same with the condition and without it."""
    model = build(tmp_path, *with_watcher(' when switch.position is "jammed"'))
    assert 'watcher.noted_hours' in model.left_out[()]['quantities']
    assert 'watcher.noted_hours' not in model.structure_of('slow').quantities
    assert 'watcher.noted_hours' in model.structure_of('slow_kept').quantities
    (tmp_path / 'plain').mkdir()
    plain = build(tmp_path / 'plain', *with_watcher(''))
    assert 'watcher.noted_hours' not in plain.left_out[()]['quantities']
    assert 'watcher.noted_hours' in plain.structure_of('slow').quantities
    assert jam_time(model) < 150.0
    for name, hours in (('slow', 0.0), ('slow_kept', 50.0)):
        for built_model in (model, plain):
            assert output_at(built_model, name, 'noted', 200.0) == pytest.approx(hours, abs=1e-6), name


def test_the_parts_left_out_are_in_name_order(tmp_path):
    """Each section of `left_out` lists its parts in name order: the same in every process, although
    the members of an entity that is left out are a set, whose order differs between processes. The
    observer has formulas that nothing else reads: they go with it."""
    formulas = [
        formula(name, '1 if seen is "yes" else 0', 'fraction', records='@ident')
        for name in ('zeta', 'eta', 'theta', 'iota', 'kappa', 'lambda_', 'mu', 'nu')
    ]
    model = build(tmp_path, with_observer(*formulas))
    left = model.left_out[()]
    assert 'observer' in left['entities'] and {'observer.zeta', 'observer.nu'} <= set(left['computed'])
    for starts, sections in model.left_out.items():
        for section, parts in sections.items():
            assert list(parts) == sorted(parts), (starts, section)


# ---- checks that apply only with some profiles ----------------------------------------------------


def with_check(condition):
    """An edit step: a check at the top level. It reads inputs and named states only, so it runs
    before the run; one that reads a state as it changes runs at every step."""
    return append(check(condition, 'The attacker reacts within 50 hours.', records='@ident'))


ONLY_WITH_ACCESS = 'attacker.access is "none" or attacker.reaction_time <= 50 h'


def admitted(model, name, reaction):
    edits = edits_for(model, {'runs': {name: {'attacker.reaction_time': reaction}}})
    return evaluate_study(model, edits, runs=[name]).admissible


def test_a_check_that_reads_a_start_value_applies_only_with_the_options_that_set_it(tmp_path):
    model = build(tmp_path, with_check(ONLY_WITH_ACCESS))
    # The first check at the top level is `simulate.0`.
    assert 'simulate.0' not in model.structure_of('slow').input_checks
    kept = model.structure_of('slow_kept').input_checks['simulate.0']
    assert written(kept.expr) == "attacker.reaction_time <= q(50, 'h')"
    assert admitted(model, 'slow', 60)
    assert not admitted(model, 'slow_kept', 60)
    assert admitted(model, 'slow_kept', 40)


def test_a_check_with_no_start_value_applies_to_every_structure(tmp_path):
    model = build(tmp_path, with_check('attacker.reaction_time <= 50 h'))
    for structure in model.structures.values():
        assert written(structure.input_checks['simulate.0'].expr) == "attacker.reaction_time <= q(50, 'h')"


def unproved(text):
    """{start profiles: structure} of a model text, as the build reads them into typed parts, before
    it checks and proves them (`napkin.model.model.built`)."""
    file = front.read(text, 'MODELTEST.scn')

    def declare():
        scenario, resolver = resolve(file, LIB)
        table = Runs.from_scenario(scenario, LIB).table
        return arguments(scenario, table, resolver), table

    return built(declare, file.lines, 'MODELTEST.scn', LIB)[1]


def test_a_check_during_the_run_reads_a_state_that_changes_as_it_is():
    """The responders change the attacker's access during a run, so its start value settles nothing.
    The structures are read before the compiler proves them: a check with `or` is never proved during
    a run, and this test is about where the builder places the check."""
    condition = 'attacker.access is not "removed" or abs(service.waiting + service.served - service.users) <= 0.001 people'
    structures = unproved(edit(FIXTURE, with_check(condition)))
    assert set(structures) == {(), ('Keeps access',)}
    for structure in structures.values():
        assert "attacker.access != 'removed'" in written(structure.state_checks['simulate.0'].expr)


def test_a_check_that_fails_at_the_start_of_every_run_of_a_structure_is_an_error(tmp_path):
    with pytest.raises(ModelError, match='fails at the start'):
        build(tmp_path, with_check('attacker.access is "kept" and attacker.reaction_time <= 50 h'))
