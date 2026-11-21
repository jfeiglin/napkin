"""The evidence stage of `tools.check` (item 16 of the plan's changes after G0): a scenario package of
the catalogue whose model rests a value on no record, or gives a value that differs from a datum that
its record cites, fails the check, though the model still runs.

Each test writes a small catalogue of its own, with packages that the tests' reserved IDs name, and
asks the stage about it. The line of each warning is counted by hand in the texts below."""

import json
import textwrap

from napkin.model.compile import load_scenario
from napkin.model.support import cited_data
from tests.evidence.support import datum_package
from tools import check

# A tank whose water, drain and event rest on a record. Its rate is an input that rests on none
# when `{cite}` is empty: line 7 of the file.
TANK = """\
scenario "A tank"
    horizon 4 h

tank:
    "A tank that drains."
    water: people = 8 people in [0,]  @basis
    input rate: people/h = 1 people/h in [0 people/h, 5 people/h]{cite}
        "Rate of the drain"
    flow drain: this.water -> SINK  @basis
        request = formula(this.rate)
    empty = event():  @basis
        when this.water <= 0 people:
            this.empty.start()
            reset when false
        after 0 h:
            this.water += 0 people

record basis: assumption "The tank holds eight and drains at the rate."
"""


def catalogue(root, **packages):
    """A catalogue at `root` with one package for each keyword: its ID and the text of its model."""
    for name, text in packages.items():
        folder = root / 'scenarios' / name
        folder.mkdir(parents=True)
        (folder / 'model.scn').write_text(textwrap.dedent(text), encoding='utf-8')
    return root


def test_a_package_with_a_value_on_no_record_fails_and_names_the_value_at_its_line(tmp_path, capsys):
    root = catalogue(tmp_path, SC97=TANK.format(cite=''), SC98=TANK.format(cite='  @basis'))
    found = check.unsupported(root=root)
    assert list(found) == ['SC97']
    (message,) = found['SC97']
    assert message.startswith('scenarios/SC97/model.scn:7: tank.rate: an input rests on no record')
    assert check.evidence(root=root) == 1
    printed = capsys.readouterr().out
    assert 'SC97: 1 part without the support of a record' in printed
    assert 'SC98' not in printed


def test_a_package_with_a_value_that_differs_from_its_cited_datum_fails_with_both_numbers(tmp_path, capsys):
    """The audit's row 17: an input of 99 h whose record cites a datum of 34 h. The compiler warns
    (`napkin.model.support.DATUM`); the catalogue check refuses it, as a value on no record. The
    package with the value of its datum (whose `open` rests on no record) has every refusal of the
    99 h package but that one."""
    datum_package(tmp_path / 'equal')
    base = check.unsupported(root=tmp_path / 'equal').get('SC99', [])
    entry = datum_package(tmp_path / 'apart', end='99 h')
    line = next(k for k, row in enumerate(entry.read_text().split('\n'), 1) if 'input end' in row)
    expected = (
        f'scenarios/SC99/model.scn:{line}: service.end: @timing cites the datum delay of C-ACTION, 34 h, '
        'and 99 h differs from it'
    )
    assert sorted(check.unsupported(root=tmp_path / 'apart')['SC99']) == sorted([*base, expected])
    capsys.readouterr()
    assert check.evidence(root=tmp_path / 'apart') == 1
    count = len(base) + 1
    assert (
        f'SC99: {count} part{"s" if count > 1 else ""} without the support of a record'
        in capsys.readouterr().out
    )


def test_a_package_whose_every_value_rests_on_a_record_passes(tmp_path):
    root = catalogue(tmp_path, SC98=TANK.format(cite='  @basis'))
    assert check.unsupported(root=root) == {}
    assert check.evidence(root=root) == 0


def test_the_stage_checks_only_the_selected_packages(tmp_path):
    root = catalogue(tmp_path, SC97=TANK.format(cite=''), SC98=TANK.format(cite='  @basis'))
    assert check.evidence(('SC98',), root=root) == 0
    assert check.evidence(('SC97',), root=root) == 1
    # A selection of no package checks nothing.
    assert check.evidence((), root=root) == 0


def test_a_package_that_does_not_compile_fails_with_its_first_problem(tmp_path):
    root = catalogue(tmp_path, SC97=TANK.format(cite='  @nowhere'))
    (message,) = check.unsupported(root=root)['SC97']
    assert 'it does not compile, so its evidence is not read' in message
    assert check.evidence(root=root) == 1


def test_the_evidence_stage_runs_with_the_whole_check_and_not_with_test_paths_alone(capsys):
    assert check.main(['--all', '--plan']) == 0
    assert 'Evidence' in capsys.readouterr().out.split('Stages: ')[1].splitlines()[0]
    assert check.main(['--tests', 'tests/test_check_evidence.py', '--plan']) == 0
    assert 'Evidence' not in capsys.readouterr().out.split('Stages: ')[1].splitlines()[0]


def test_ninety_nine_hours_cannot_cite_thirty_four_gallons_per_year(tmp_path):
    entry = datum_package(tmp_path, end='99 h', delay=(34, 'gal/yr'))
    entry.write_text(entry.read_text().replace('open: bool = true', 'open: bool = true  @fixture'))
    # This complete spelling is registered. "gal" and "yr" need no definitions of their own.
    units = entry.parent / 'units.json'
    table = json.loads(units.read_text())
    table['gal/yr'] = {'dimensions': {'volume': 1, 'time': -1}, 'scale': 1}
    units.write_text(json.dumps(table))
    (message,) = check.unsupported(root=tmp_path)['SC99']
    assert all(
        word in message for word in ('service.end', 'C-ACTION', '34 gal/yr', '99 h is of another dimension')
    )
    assert check.evidence(root=tmp_path) == 1


def test_an_unresolvable_cited_unit_names_the_value_claim_and_datum(tmp_path):
    model = load_scenario(datum_package(tmp_path)).declared
    library = {'claims': [{'id': 'C-ACTION', 'data': {'delay': {'value': 34, 'unit': 'unknown/yr'}}}]}
    problems = cited_data(model, library)
    assert any(
        all(word in warning.message for word in ('service.end', 'C-ACTION', 'delay', 'unknown/yr'))
        for warning in problems
    )
