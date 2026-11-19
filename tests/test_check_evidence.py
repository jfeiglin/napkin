"""The evidence stage of `tools.check` (item 16 of the plan's changes after G0): a scenario package of
the catalogue whose model rests a value on no record fails the check, though the model still runs.

Each test writes a small catalogue of its own, with packages that the tests' reserved IDs name, and
asks the stage about it. The line of each warning is counted by hand in the texts below."""

import textwrap

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
    assert 'SC97: 1 part rests on no record' in printed
    assert 'SC98' not in printed


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
