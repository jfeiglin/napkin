"""The public contract of a study (`napkin/engine/study.py`) and three time integrals of the engine.

A study runs one program under the configurations of a model's named runs, under one edit document
that the front end checks whole, in every run, before any run starts. Its records are the engine's
records of those configurations, in this process or in a pool. The expected values are worked by
hand: a plant fills at its rate for 4 h, so it holds four times the rate; a pulse
A exp(-((t - 2 h) / w)^2) holds A w sqrt(pi) once it has passed; a window of 2 L/h from 1 h to 3 h
holds 4 L.
"""

from __future__ import annotations

import math
import textwrap

import pytest

from napkin import SCHEMA_VERSION, store
from napkin.engine import read
from napkin.engine.study import configurations, edits_for, run_all, study
from napkin.engine.timeline import run
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program.config import InputValue, Quantity
from tests.program.examples import UNITS

PLANT = textwrap.dedent("""\
    scenario "Plant"
        horizon 4 h
    plant:
        input rate: L/h = 2 L/h in [1 L/h, 8 L/h]  @ident
        held: L = 0 L in [0 L,]
            "Water held"
        flow fill: SOURCE -> this.held
            request = this.rate
    options "Pace":
        "Slow":
            "The plant fills slowly."
        "Fast":
            "The plant fills fast."
            plant.rate = 4 L/h  @ident
    runs:
        slow = "Slow"
        fast = "Fast"
    record ident: assumption "A synthetic test fixture."
    """)


def compiled(text=PLANT):
    return compile_text(text, UNITS)


def held(model, record, t=4):
    return read(record, model.program, ['plant.held'], [t])[0].values[0]


def test_a_study_runs_each_declared_run_in_its_order():
    model = compiled()
    found = study(model)
    assert list(found) == ['slow', 'fast']
    assert [held(model, record) for record in found.values()] == pytest.approx([8, 16])


def test_a_model_with_no_named_run_has_its_default_run():
    model = compiled(
        PLANT[: PLANT.index('options')] + 'record ident: assumption "A synthetic test fixture."\n'
    )
    ((name, record),) = study(model).items()
    assert name is None and held(model, record) == pytest.approx(8)


def test_a_study_of_named_runs_runs_those_only_and_each_record_is_the_engine_s(monkeypatch):
    model = compiled()
    asked = []
    plain = store.run
    monkeypatch.setattr(
        store,
        'run',
        lambda program, configuration: asked.append(configuration) or plain(program, configuration),
    )
    found = study(model, ['fast'])
    assert list(found) == ['fast'] and asked == [model.configure('fast')]
    assert found['fast'] == run(model.program, model.configure('fast'))


def test_an_edit_document_is_one_transaction_over_every_run(monkeypatch):
    """An edit of run `fast` outside the input's range refuses a study of run `slow` too, and no run
    starts."""
    model = compiled()
    asked = []
    monkeypatch.setattr(store, 'run', lambda program, configuration: asked.append(configuration))
    edits = edits_for(model, {'runs': {'fast': {'plant.rate': 100}}})
    with pytest.raises(LanguageError) as caught:
        study(model, ['slow'], edits)
    assert caught.value.codes == ['range'] and asked == []


def test_every_problem_of_the_document_and_of_the_names_comes_at_once():
    model = compiled()
    edits = {'schema_version': SCHEMA_VERSION, 'model_hash': 'another revision'}
    with pytest.raises(LanguageError) as caught:
        configurations(model, ['slow', 'quick', 'faster'], edits)
    assert sorted(caught.value.codes) == ['model_hash', 'run', 'run']
    with pytest.raises(ValueError, match='names each run once'):
        configurations(model, ['slow', 'slow'])


def test_each_level_of_an_edit_reaches_its_runs():
    """`set` reaches every run; an option's edit the runs that take it, over the option; a run's edit
    that run, over both."""
    model = compiled()
    edits = edits_for(model, {'set': {'plant.rate': 3}, 'options': {'Fast': {'plant.rate': 5}}})
    found = configurations(model, None, edits)
    assert [item.inputs for item in found.values()] == [
        (InputValue('plant', 'rate', Quantity(3, 'L/h')),),
        (InputValue('plant', 'rate', Quantity(5, 'L/h')),),
    ]
    edits = edits_for(model, {'set': {'plant.rate': 3}, 'runs': {'fast': {'plant.rate': 6}}})
    records = study(model, None, edits)
    assert [held(model, record) for record in records.values()] == pytest.approx([12, 24])


def test_a_run_that_fails_gives_its_record_with_the_failure():
    """At 4 L/h the assertion fails at the start of run `fast`; run `slow` runs to its horizon."""
    model = compiled(PLANT + 'assert plant.rate <= 3 L/h\n')
    found = study(model)
    assert found['slow'].failure is None and held(model, found['slow']) == pytest.approx(8)
    assert found['fast'].failure is not None and found['fast'].failure.t == 0


def test_a_study_in_processes_gives_the_records_of_one_process():
    model = compiled()
    one = run_all(model.program, configurations(model).values())
    two = run_all(model.program, configurations(model).values(), jobs=2)
    assert [held(model, record) for record in two] == pytest.approx(
        [held(model, record) for record in one], rel=1e-12
    )
    assert [record.trace for record in two] == [record.trace for record in one]
    with pytest.raises(ValueError, match='jobs is a whole number'):
        run_all(model.program, (), jobs=0)


def test_an_edit_document_names_the_revision_of_its_model():
    model = compiled()
    assert edits_for(model, {'reason': 'faster'}) == {
        'schema_version': SCHEMA_VERSION,
        'model_hash': model.model_hash,
        'reason': 'faster',
    }
    assert list(configurations(model, None, edits_for(model))) == ['slow', 'fast']


def tank(request, *lines):
    return compiled(
        textwrap.dedent("""\
            scenario "Pulse"
                horizon 4 h
            tank:
            """)
        + ''.join(f'    {line}\n' for line in lines)
        + '    water: L = 0 L in [0 L,]\n    flow pulse: SOURCE -> this.water\n'
        + f'        request = {request}\n'
    )


def water(model):
    return read(run(model.program, model.configuration), model.program, ['tank.water'], [4])[0].values[0]


def test_a_narrow_pulse_in_time_holds_its_gaussian_mass():
    """10 L/h exp(-((t - 2 h) / 0.05 h)^2) adds 10 * 0.05 * sqrt(pi) L; its tails beyond 0 h and 4 h are
    below exp(-1600)."""
    model = tank('formula(10 L/h * exp(-((t - 2 h) / 0.05 h) ** 2))')
    assert water(model) == pytest.approx(0.5 * math.sqrt(math.pi), rel=1e-8)


def test_a_window_in_time_holds_its_rectangle():
    model = tank('formula(2 L/h if t >= 1 h and t < 3 h else 0 L/h)')
    assert water(model) == pytest.approx(4, rel=1e-8)


def test_a_pulse_of_the_model_s_own_clock_holds_the_same_mass():
    model = tank(
        'formula(10 L/h * exp(-((this.clock - 2 h) / 0.05 h) ** 2))',
        'clock: h = 0 h in [0 h,]',
        'flow tick: SOURCE -> this.clock',
        '    request = 1 h/h',
    )
    assert water(model) == pytest.approx(0.5 * math.sqrt(math.pi), rel=1e-8)


@pytest.mark.parametrize(('first', 'second', 'kept'), [('zeta', 'alpha', 2), ('alpha', 'zeta', 1)])
def test_the_stages_of_one_moment_go_in_the_order_of_their_starts_whatever_their_names(first, second, kept):
    """Two stages commit at 1 h (spec, "Rounds"): the occurrence that started first goes first, and the
    value of the one that commits last stays."""
    model = compiled(
        textwrap.dedent(f"""\
            scenario "Order"
                horizon 2 h
            desk:
                mark = 0
                zeta = event():
                    after 1 h:
                        this.mark = 1
                alpha = event():
                    after 1 h:
                        this.mark = 2
            desk.{first}.start()
            desk.{second}.start()
            """)
    )
    record = run(model.program, model.configuration)
    assert [entry.part for entry in record.entries('commit')] == [
        f'desk.{first}.step[0]',
        f'desk.{second}.step[0]',
    ]
    assert read(record, model.program, ['desk.mark'], [2])[0].values == (kept,)
