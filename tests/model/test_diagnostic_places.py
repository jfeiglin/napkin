"""The place of a problem, `file:line:column`, and the close names that it suggests (difflib).

A problem gives the line and the column of the token or the part of the line that it is about
(`language/problems.py`): the token that the parser cannot read, the number of a quantity whose unit
is no unit, the `@` of a citation, the name that names nothing, the step `.name` that a member does
not have. In a package it gives the file of the module and the line in that file. A name that names
nothing gets at most three names of the model that are closest to it (`semantic.close`), and a name
far from every name gets none."""

from __future__ import annotations

import pytest

from napkin.model.compile import compile_text, load_scenario
from napkin.model.language.problems import LanguageError
from napkin.model.semantic import close
from tests.program.examples import UNITS

TANK = """\
scenario "Places"
    horizon 4 h

options "Repair":
    "Fast repair":
        "The crew repairs fast."
        tank.repair = 1 h  @ident

runs:
    fast = "Fast repair"

tank:
    input repair: h = 2 h in [0 h, 10 h]  @ident
    water: L = 8 L in [0 L,]  @ident
    crews: person = 2 person  @ident
    fill = event():
        after 1 h:
            this.water += 1 L
    level = formula(this.water * 2)

tank.fill.start()

record ident: identity "Analytic contract fixture."
"""


def problems(text):
    with pytest.raises(LanguageError) as raised:
        compile_text(text, UNITS, 'tank.scn')
    return raised.value.problems


def written_at(text, problem):
    """The text of the line of a problem from its column on."""
    return text.split('\n')[problem.line - 1][problem.column - 1 :]


@pytest.mark.parametrize(
    ('old', 'new', 'code', 'at'),
    [
        ('water: L = 8 L in [0 L,]  @ident', 'water: L = 8 L )  @ident', 'bracket', ')'),
        ('crews: person = 2 person', 'crews: person = 2 persn', 'unit', '2 persn'),
        ('crews: person = 2 person  @ident', 'crews: person = 2 person  @idnet', 'unknown_record', '@idnet'),
        ('formula(this.water * 2)', 'formula(zzqx * 2)', 'unknown_name', 'zzqx'),
        ('formula(this.water * 2)', 'formula(this.watr * 2)', 'unknown_name', '.watr'),
    ],
    ids=['token', 'unit', 'record', 'name', 'member'],
)
def test_a_problem_gives_the_file_line_and_column_of_what_it_is_about(old, new, code, at):
    text = TANK.replace(old, new)
    (problem,) = problems(text)
    assert (problem.code, problem.file) == (code, 'tank.scn')
    assert written_at(text, problem).startswith(at)
    assert str(problem).startswith(f'tank.scn:{problem.line}:{problem.column}: ')


def test_a_problem_of_a_module_gives_the_file_line_and_column_of_the_module(tmp_path):
    crew = 'crew:\n    removal: h = 3 h\n    done = formula(this.removal_tim > 1 h)\n'
    (tmp_path / 'model.scn').write_text('scenario "Package"\n    horizon 4 h\nuse crew\n', encoding='utf-8')
    (tmp_path / 'crew.scn').write_text(crew, encoding='utf-8')
    with pytest.raises(LanguageError) as raised:
        load_scenario(tmp_path / 'model.scn')
    (problem,) = raised.value.problems
    assert (problem.code, problem.file, problem.line) == ('unknown_name', (tmp_path / 'crew.scn').as_posix(), 3)
    assert crew.split('\n')[2][problem.column - 1 :].startswith('.removal_tim')
    assert problem.message.endswith('did you mean removal?')


@pytest.mark.parametrize(
    ('old', 'new', 'meant'),
    [
        ('formula(this.water * 2)', 'formula(this.watr * 2)', 'water'),
        ('            this.water += 1 L', '            this.fil.start()', 'fill'),
        ('crews: person = 2 person  @ident', 'crews: person = 2 person  @idnet', 'ident'),
        ('crews: person = 2 person', 'crews: person = 2 persn', 'person'),
        ('    fast = "Fast repair"', '    fast = "Fast repiar"', 'Fast repair'),
    ],
    ids=['value', 'event', 'record', 'unit', 'option'],
)
def test_a_name_that_names_nothing_gets_the_closest_names_of_the_model(old, new, meant):
    (problem,) = problems(TANK.replace(old, new))
    suggested = problem.message.rpartition('did you mean ')[2].rstrip('?')
    assert suggested.split(' or ')[0] == meant


def test_a_name_far_from_every_name_gets_no_suggestion():
    (problem,) = problems(TANK.replace('formula(this.water * 2)', 'formula(this.zzqx * 2)'))
    assert problem.code == 'unknown_name' and 'did you mean' not in problem.message


def test_close_names_are_at_most_three_known_names_and_never_the_name_itself():
    names = ['repair_time', 'repair_times', 'repairs_time', 'repair_tim', 'settle_time']
    listed = close('repair_time', names).removeprefix('; did you mean ').removesuffix('?').split(' or ')
    assert 1 <= len(listed) <= 3 and set(listed) <= set(names) - {'repair_time'}
    assert close('zzqx', names) == '' and close('a', []) == ''
