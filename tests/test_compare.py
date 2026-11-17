"""The comparison of two revisions (`tools/compare.py`), on made-up records: it finds a
changed floating-point bit, exchanged simultaneous steps, keys in another order and an evidence
location changed without a mapping; it leaves out the implementation hash and what an allow file
names; a digest of a result changes with any bit of it; a capture failure on either side fails it;
the canonical form leaves out source positions, event ranks other than their order, and the pages'
controls; a trajectory's record keeps its numbers and its named units and leaves out its trace; a
rename reads whole paths only; and a baseline from another machine is refused. The order of a model
and the numbers of a run are records of names and numbers only: they hold the compiled order, each
step and each sixteenth of a run, and nothing of how a revision keeps them; a model outside the
catalogue is an owner with a dot in its name. For a change of the numerical core, the differences
of two studies are sorted: a number within its tolerance and a located event that shifts a little need
no word, and a discrete difference or a number beyond its tolerance must be explained."""

import json
import math
import re
from dataclasses import dataclass

import numpy as np
import pytest

from napkin.engine import evaluate_study
from tests.build import compiled, scenario
from tools import catalogue, compare


def through_json(value):
    """A value as a capture writes it and the comparison reads it."""
    return json.loads(json.dumps(compare.plain(value)))


def found(a, b, **options):
    return compare.differences(through_json(a), through_json(b), **options)


def test_a_changed_floating_point_bit_differs():
    value = 0.1
    assert found({'v': value}, {'v': math.nextafter(value, 1)})
    assert found({'v': 0.0}, {'v': -0.0})
    assert found({'v': 1}, {'v': 1.0})
    assert not found({'v': float('nan')}, {'v': float('nan')})
    assert not found({'v': value}, {'v': 0.1})


def test_exchanged_simultaneous_steps_and_keys_in_another_order_differ():
    first, second = {'t': 3.0, 'round': 1, 'rule': 'a'}, {'t': 3.0, 'round': 1, 'rule': 'b'}
    assert found({'trace': [first, second]}, {'trace': [second, first]})
    assert found({'a': 1, 'b': 2}, {'b': 2, 'a': 1})
    assert found({'a': [1, 2]}, {'a': [1, 2, 3]})


def test_an_evidence_location_differs_unless_a_mapping_names_it(tmp_path):
    old, new = 'model.scn:12', 'model.scn:13'
    base, tree = tmp_path / 'base' / 'SC97', tmp_path / 'tree' / 'SC97'
    for folder, location in ((base, old), (tree, new)):
        folder.mkdir(parents=True)
        (folder / 'structure.json').write_text(json.dumps({'evidence': {'at': location}}))
    changed, names = compare.compare(tmp_path / 'base', tmp_path / 'tree')
    assert names == ['SC97/structure.json'] and changed
    changed, _ = compare.compare(tmp_path / 'base', tmp_path / 'tree', mapping={old: new})
    assert changed == {}


def test_the_implementation_hash_is_left_out_and_other_hashes_only_when_allowed(tmp_path):
    for side, value in (('base', 'one'), ('tree', 'two')):
        folder = tmp_path / side / 'SC97'
        folder.mkdir(parents=True)
        (folder / 'default.json').write_text(json.dumps({'implementation_hash': value, 'model_hash': value}))
    changed, _ = compare.compare(tmp_path / 'base', tmp_path / 'tree')
    assert list(changed) == ['SC97/default.json'] and all(
        'model_hash' in line for line in changed['SC97/default.json']
    )
    changed, _ = compare.compare(
        tmp_path / 'base', tmp_path / 'tree', ignore=(*compare.DEFAULT_IGNORE, 'model_hash')
    )
    assert changed == {}


def test_a_record_on_one_side_only_differs(tmp_path):
    (tmp_path / 'base' / 'SC97').mkdir(parents=True)
    (tmp_path / 'tree' / 'SC98').mkdir(parents=True)
    (tmp_path / 'base' / 'SC97' / 'default.json').write_text('{}')
    (tmp_path / 'tree' / 'SC98' / 'default.json').write_text('{}')
    changed, names = compare.compare(tmp_path / 'base', tmp_path / 'tree')
    assert set(changed) == set(names) == {'SC97/default.json', 'SC98/default.json'}


@dataclass
class Result:
    values: np.ndarray
    names: set
    order: dict


@pytest.mark.parametrize(
    'other, equal',
    [
        (Result(np.array([1.0, 2.0]), {'b', 'a'}, {'x': 1, 'y': 2}), True),
        (Result(np.array([1.0, math.nextafter(2.0, 3)]), {'a', 'b'}, {'x': 1, 'y': 2}), False),
        (Result(np.array([1.0, 2.0]), {'a', 'c'}, {'x': 1, 'y': 2}), False),
        (Result(np.array([1.0, 2.0]), {'a', 'b'}, {'y': 2, 'x': 1}), False),
    ],
)
def test_a_digest_changes_with_any_bit_of_a_result(other, equal):
    result = Result(np.array([1.0, 2.0]), {'a', 'b'}, {'x': 1, 'y': 2})
    assert (compare.digest(result) == compare.digest(other)) is equal


def test_a_record_keeps_keys_that_are_not_texts_and_sorts_sets():
    assert compare.plain({('Default', 'Fast'): {3, 1, 2}}) == [['<key>', ['Default', 'Fast'], [1, 2, 3]]]


class Units:
    def __init__(self):
        self.units = {'h': 1.0}


def test_a_record_holds_no_memory_address_or_place_of_the_checkout():
    """Two checkouts in different places, with objects at different addresses, give equal records."""
    first, second = compare.plain({'units': Units()}), compare.plain({'units': Units()})
    assert first == second and 'units' in first['units']
    assert compare.plain(object.__new__(object)) == compare.plain(object.__new__(object))
    old = compare.relocated({'file': '/somewhere/base/scenarios/SC97/model.scn'}, ['/somewhere/base'])
    new = compare.relocated({'file': '/elsewhere/scenarios/SC97/model.scn'}, ['/elsewhere'])
    assert old == new == {'file': '<root>/scenarios/SC97/model.scn'}


def write(root, side, owner, **named):
    """Records of one owner, as a capture writes them: `<side>/<owner>/<record>.json`."""
    folder = root / side / owner
    folder.mkdir(parents=True, exist_ok=True)
    for name, value in named.items():
        (folder / f'{name}.json').write_text(json.dumps(value))


def test_an_induced_capture_failure_on_either_side_fails_the_run(tmp_path, capsys):
    failure = compare._part(lambda: 1 / 0)
    assert list(failure) == [compare.FAILURE]
    write(tmp_path, 'base', 'SC97', default={'v': 1})
    write(tmp_path, 'tree', 'SC97', default=failure)
    assert compare.judge(tmp_path / 'base', tmp_path / 'tree') == 2
    write(tmp_path, 'base', 'SC97', default=failure)
    write(tmp_path, 'tree', 'SC97', default={'v': 1})
    assert compare.judge(tmp_path / 'base', tmp_path / 'tree') == 2
    # Alike failures on both sides compare equal, and still fail the run.
    write(tmp_path, 'tree', 'SC97', default=failure)
    assert compare.compare(tmp_path / 'base', tmp_path / 'tree')[0] == {}
    assert compare.judge(tmp_path / 'base', tmp_path / 'tree') == 2
    out = capsys.readouterr().out
    assert 'CAPTURE FAILED (base) SC97/default.json: ZeroDivisionError' in out
    assert 'CAPTURE FAILED (tree) SC97/default.json: ZeroDivisionError' in out
    write(tmp_path, 'base', 'SC97', default={'v': 1})
    write(tmp_path, 'tree', 'SC97', default={'v': 1})
    assert compare.judge(tmp_path / 'base', tmp_path / 'tree') == 0


def test_the_canonical_form_leaves_out_positions_ranks_other_than_their_order_and_controls():
    first = {
        'lines': {'scenario:': 2},
        'index': {'file': '<root>/a.scn', 'uses': [{'name': 'n', 'line': 4, 'file': '<root>/a.scn'}]},
        'structures': [{'rank': [484, 3, 0]}, {'rank': [-1]}, {'rank': [490, 3, 0]}],
    }
    moved = {
        'lines': {'scenario:': 9},
        'index': {'file': '<root>/b.scn', 'uses': [{'name': 'n', 'line': 7, 'file': '<root>/b.scn'}]},
        'structures': [{'rank': [10, 3, 0]}, {'rank': [-1]}, {'rank': [16, 3, 0]}],
    }
    assert compare.canonical('structure', first) == compare.canonical('structure', moved)
    exchanged = {**moved, 'structures': [{'rank': [16, 3, 0]}, {'rank': [-1]}, {'rank': [10, 3, 0]}]}
    assert compare.canonical('structure', first) != compare.canonical('structure', exchanged)
    renamed = {**moved, 'index': {**moved['index'], 'uses': [{'name': 'm', 'line': 7}]}}
    assert compare.canonical('structure', first) != compare.canonical('structure', renamed)
    assert compare.canonical('pages', {'controls': ['a.x'], 'runs': ['r']}) == {'runs': ['r']}
    # Only the model loses its positions, and only the pages their controls.
    assert compare.canonical('default', {'lines': 1, 'controls': 2}) == {'lines': 1, 'controls': 2}


@dataclass
class Trajectory:
    horizon: float
    trace: list
    diagnostics: list
    _units: object
    _snapshots: list


class UnitTable:
    def __init__(self, table):
        self._units = table


def test_a_trajectory_record_keeps_the_numbers_and_the_named_units_and_leaves_out_the_trace():
    table = {'h': [1.0], 'people': [1.0], 'days': [24.0], 'USD2025/h': [1.0]}
    resolved = {'types': {'crew': 'people'}, 'expr': "q(2.0, 'h') * x"}
    one = Trajectory(10.0, [{'label': 'one'}], [], UnitTable(table), [(0.0, np.array([1.0, 2.0]))])
    record = compare.trajectory_record(one, resolved)
    assert list(record['units']) == ['h', 'people']
    reordered = Trajectory(
        10.0, [{'label': 'two'}], [{'w': 1}], UnitTable(dict(reversed(table.items()))), one._snapshots
    )
    assert compare.trajectory_record(reordered, resolved) == record
    other_bit = Trajectory(10.0, [], [], UnitTable(table), [(0.0, np.array([1.0, math.nextafter(2.0, 3)]))])
    assert compare.trajectory_record(other_bit, resolved) != record
    rescaled = Trajectory(10.0, [], [], UnitTable({**table, 'h': [2.0]}), one._snapshots)
    assert compare.trajectory_record(rescaled, resolved) != record
    unused_unit = Trajectory(10.0, [], [], UnitTable({**table, 'week': [168.0]}), one._snapshots)
    assert compare.trajectory_record(unused_unit, resolved) == record


def test_a_rename_reads_whole_paths_and_never_part_of_a_word():
    read = compare.renamer({'SC97_east': 'SC97:east', 'scenarios/SC97_east': 'scenarios/SC97/variants/east'})
    assert read('SC97_east') == 'SC97:east'
    assert read('SC97_east/default.json') == 'SC97:east/default.json'
    assert read('<root>/scenarios/SC97_east/model.scn') == '<root>/scenarios/SC97/variants/east/model.scn'
    for text in ('SC97_east_side', 'xSC97_east', 'the SC97_east case', 'SC97_east:12', 'SC97_eastx/a'):
        assert read(text) == text


def test_a_rename_reads_the_owners_and_texts_of_the_base(tmp_path):
    write(tmp_path, 'base', 'SC97_east', default={'file': '<root>/scenarios/SC97_east/model.scn'})
    write(tmp_path, 'tree', 'SC97:east', default={'file': '<root>/scenarios/SC97/variants/east/model.scn'})
    renames = {'SC97_east': 'SC97:east', 'scenarios/SC97_east': 'scenarios/SC97/variants/east'}
    assert compare.compare(tmp_path / 'base', tmp_path / 'tree')[0]
    found, names = compare.compare(tmp_path / 'base', tmp_path / 'tree', renames=renames)
    assert found == {} and names == ['SC97:east/default.json']


def test_a_path_leaves_out_one_place_and_the_reporting_projection_keeps_the_final_point(tmp_path):
    early = {
        'reporting_points': {
            'day_one': {'t': 24.0, 'values': {'x': 1.0}},
            'final': {'t': 72.0, 'values': {'x': 3.0}},
        },
        'samples': [{'t': 24.0, 'values': {'x': 1.0}}, {'t': 72.0, 'values': {'x': 3.0}}],
        'health': [{'t': 24.0}, {'t': 72.0}],
        'peaks': {'x': {'value': 3.0, 't': 72.0}},
        'severity': 'high',
    }
    later = {
        'reporting_points': {'final': {'t': 72.0, 'values': {'x': 3.0}}},
        'samples': [{'t': 72.0, 'values': {'x': 3.0}}],
        'health': [{'t': 72.0}],
        'peaks': {'x': {'value': 3.0, 't': 60.0}},
    }
    diagnostics = [{'severity': 'error'}]
    write(tmp_path, 'base', 'SC97', default={'report': {'runs': {'r': early}}, 'diagnostics': diagnostics})
    write(tmp_path, 'tree', 'SC97', default={'report': {'runs': {'r': later}}, 'diagnostics': diagnostics})
    paths = ['default/report/runs/*/peaks/*/t', 'default/report/runs/*/severity']
    assert compare.compare(tmp_path / 'base', tmp_path / 'tree')[0]
    assert compare.compare(tmp_path / 'base', tmp_path / 'tree', ignore_paths=paths)[0]
    assert (
        compare.compare(tmp_path / 'base', tmp_path / 'tree', ignore_paths=paths, reporting='final')[0] == {}
    )
    # A path names one place: the diagnostics' own severity still counts, and so does the peak's value.
    write(
        tmp_path,
        'tree',
        'SC97',
        default={'report': {'runs': {'r': later}}, 'diagnostics': [{'severity': 'x'}]},
    )
    assert compare.compare(tmp_path / 'base', tmp_path / 'tree', ignore_paths=paths, reporting='final')[0]
    moved = {**later, 'peaks': {'x': {'value': 4.0, 't': 60.0}}}
    write(tmp_path, 'tree', 'SC97', default={'report': {'runs': {'r': moved}}, 'diagnostics': diagnostics})
    assert compare.compare(tmp_path / 'base', tmp_path / 'tree', ignore_paths=paths, reporting='final')[0]


def test_a_baseline_from_another_machine_is_refused(tmp_path):
    for side in ('base', 'tree'):
        (tmp_path / side).mkdir()
    assert not compare.same_machine(tmp_path / 'base', tmp_path / 'tree')
    machine = {'python': '3.13', 'cpu_features': ['AVX2']}
    for side in ('base', 'tree'):
        (tmp_path / side / 'environment.json').write_text(json.dumps(machine))
    assert compare.same_machine(tmp_path / 'base', tmp_path / 'tree')
    (tmp_path / 'tree' / 'environment.json').write_text(json.dumps({**machine, 'cpu_features': ['AVX512F']}))
    assert not compare.same_machine(tmp_path / 'base', tmp_path / 'tree')


def test_a_selected_comparison_reads_only_the_selected_owners_of_a_baseline(tmp_path):
    write(tmp_path, 'base', 'SC97', default={'v': 1})
    write(tmp_path, 'base', 'SC98', default={'v': 2})
    write(tmp_path, 'tree', 'SC97', default={'v': 1})
    assert list(compare.compare(tmp_path / 'base', tmp_path / 'tree')[0]) == ['SC98/default.json']
    found, names = compare.compare(tmp_path / 'base', tmp_path / 'tree', owners={'SC97'})
    assert found == {} and names == ['SC97/default.json']
    write(tmp_path, 'base', 'SC98', default={compare.FAILURE: 'not selected'})
    assert compare.judge(tmp_path / 'base', tmp_path / 'tree', owners={'SC97'}) == 0
    write(tmp_path, 'tree', 'SC97', default={'v': 3})
    assert compare.judge(tmp_path / 'base', tmp_path / 'tree', owners={'SC97'}) == 1


def test_a_rename_that_gives_two_base_records_one_name_fails(tmp_path):
    write(tmp_path, 'base', 'SC97_east', default={'v': 1})
    write(tmp_path, 'base', 'SC97_west', default={'v': 1})
    write(tmp_path, 'tree', 'SC97:any', default={'v': 1})
    found, _ = compare.compare(
        tmp_path / 'base', tmp_path / 'tree', renames={'SC97_east': 'SC97:any', 'SC97_west': 'SC97:any'}
    )
    assert list(found) == ['SC97:any/default.json'] and 'one name' in found['SC97:any/default.json'][0]


def test_a_baseline_is_the_saved_base_side_and_a_keep_folder_may_not_overlap_it(tmp_path, capsys):
    kept = tmp_path / 'kept'
    for side in ('base', 'tree'):
        (kept / side).mkdir(parents=True)
    assert compare.baseline_records(kept) is None
    (kept / 'tree' / 'environment.json').write_text('{}')
    assert compare.baseline_records(kept) is None  # a tree side alone is no baseline
    (kept / 'base' / 'environment.json').write_text('{}')
    assert compare.baseline_records(kept) == kept / 'base'
    assert compare.baseline_records(kept / 'tree') == kept / 'tree'  # a bare capture folder
    assert compare.overlaps(kept, kept) and compare.overlaps(kept / 'tree', kept)
    assert compare.overlaps(kept, kept / 'base') and not compare.overlaps(tmp_path / 'other', kept)
    for keep in (kept, kept / 'tree', tmp_path):
        with pytest.raises(SystemExit) as error:
            compare.main(['--baseline', str(kept), '--keep', str(keep)])
        assert error.value.code == 2
    assert 'would write into the baseline' in capsys.readouterr().err


def test_each_revision_runs_its_own_capture_code(tmp_path):
    with pytest.raises(SystemExit):
        compare.capture_code(tmp_path)
    for name in ('cyber_scenarios/compare.py', 'tools/compare.py'):  # an old layout, then a newer one
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text('')
        assert compare.capture_code(tmp_path) == tmp_path / name


# ---- the records that do not depend on the representation -------------------------------------------

# A model that needs no library but the prelude: an example's folder holds such a file. The valve
# closes at CLOSE hours, so the tank holds what ran in until then: RATE × CLOSE.
RATE, CLOSE = 0.05, 4.0
TANK = f"""scenario "A tank that fills"
    summary "Water runs into a tank until a valve closes."
    horizon 10 h
    scope "The tank."

tank:
    "The tank."
    input rate: fraction/h = {RATE} fraction/h in 0 fraction/h to 0.1 fraction/h
        "Water that runs in"
        @assumption "The test assumes this rate."
    var valve: "open" | "closed" = "open"
        "Valve"
    var water: fraction = 0 size 1
        "Water in the tank"
        @identity "The water in the tank, as a share of what it holds."
    output water
    flow fill: -> water at rate while valve is "open"
    event close once when t >= {CLOSE} h:
        "The valve closes."
        @assumption "The test assumes this time."
        valve = "closed"
"""


@pytest.fixture(scope='module')
def transfer():
    model = compiled(scenario())
    return model, evaluate_study(model)


def leaves(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from leaves(item)
    else:
        yield value


def test_the_order_of_a_model_is_its_names_in_the_compiled_order_and_no_definition(transfer):
    model, _ = transfer
    record = through_json(compare.order_record(model))
    assert list(record) == [json.dumps(list(starts)) for starts in model.structures]
    for starts, structure in model.structures.items():
        order = record[json.dumps(list(starts))]
        for section in compare.ORDERED:
            assert order[section] == list(getattr(structure, section))
        ranks = [tuple(structure.rules[rule].rank) for rule in order['moment']]
        assert ranks == sorted(ranks) and sorted(order['moment']) == sorted(structure.rules)
        assert order['left_out'] == {name: list(parts) for name, parts in model.left_out[starts].items()}
        # The kind of each trigger, with the quantity and the comparison of a crossing.
        assert list(order['triggers']) == list(structure.rules)
        for rule, (kind, quantity, comparison) in order['triggers'].items():
            trigger = structure.rules[rule].trigger
            assert kind == (trigger.kind or 'discrete')
            assert (quantity, comparison) == (trigger.var, trigger.op)
        assert sorted(order['formula_order']) == sorted(structure.computed)
        # A name only: each other text of the record is the key of a part, never an expression.
        names = {name for section in compare.ORDERED for name in getattr(structure, section)}
        names |= {name for parts in model.left_out[starts].values() for name in parts}
        rest = {key: value for key, value in order.items() if key != 'triggers'}
        assert set(leaves(rest)) <= names
    key = next(iter(record))
    quantities = record[key]['quantities']
    assert len(quantities) > 1
    exchanged = {
        **record,
        key: {**record[key], 'quantities': [quantities[1], quantities[0], *quantities[2:]]},
    }
    assert compare.differences(record, exchanged)


def test_the_numbers_of_a_run_are_each_step_and_each_sixteenth_and_no_internal_object(transfer):
    model, study = transfer
    for run, item in study.runs.items():
        trajectory = item['trajectory']
        record = through_json(compare.run_states(trajectory, item['resolved'], trajectory._units))
        structure = model.structure_of(run)
        assert record['names'] == list(structure.quantities)
        assert record['formulas'] == list(structure.computed)
        assert record['discrete'] == sorted(record['discrete'])
        assert len(record['tolerances']) == len(record['names']) and all(t > 0 for t in record['tolerances'])
        # One row for each step of the trace, in its order, at its time.
        assert [row['t'] for row in record['steps']] == [entry['t'] for entry in trajectory.trace]
        assert all('written' in row for row in record['steps'])
        end = trajectory.end_time
        assert [row['t'] for row in record['grid']] == [
            end * k / compare.GRID for k in range(compare.GRID + 1)
        ]
        for row in record['steps'] + record['grid']:
            assert len(row['values']) == len(record['names'])
            assert len(row['discrete']) == len(record['discrete'])
        last = trajectory.env_at(end)
        assert record['grid'][-1]['values'] == [last[name] for name in record['names']]
        assert record['grid'][-1]['discrete'] == [last[name] for name in record['discrete']]
        assert record['grid'][-1]['formulas'] == [last[name] for name in record['formulas']]
        # Names and numbers only: no field of an object, and no expression of the model.
        assert '<object>' not in json.dumps(record) and '<array>' not in json.dumps(record)
        assert all(leaf is None or isinstance(leaf, (int, float, str)) for leaf in leaves(record))
        changed = json.loads(json.dumps(record))
        changed['grid'][-1]['values'][0] = math.nextafter(changed['grid'][-1]['values'][0], math.inf)
        assert compare.differences(record, changed)
    # The two runs differ in a rate, so their numbers differ.
    first, second = (compare.run_states(item['trajectory']) for item in study.runs.values())
    assert compare.differences(through_json(first), through_json(second))


def test_a_model_outside_the_catalogue_is_an_owner_with_a_dot_in_its_name(tmp_path):
    (tmp_path / compare.EXAMPLES / 'tank').mkdir(parents=True)
    (tmp_path / compare.EXAMPLES / 'tank' / 'model.scn').write_text(TANK)
    (tmp_path / compare.EXAMPLES / 'notes').mkdir()  # no model file: no owner
    found_owners = compare.extras(tmp_path)
    assert list(found_owners) == [f'{compare.EXAMPLES}.tank']
    for root in (tmp_path, catalogue.ROOT):
        for owner in compare.extras(root):
            assert '.' in owner and re.fullmatch(catalogue.OWNER, owner) is None
    assert compare.ACCEPTANCE[0] in compare.extras(catalogue.ROOT)


def test_the_capture_of_a_model_outside_the_catalogue_has_its_order_and_its_numbers(tmp_path):
    root, out = tmp_path / 'root', tmp_path / 'out'
    (root / compare.EXAMPLES / 'tank').mkdir(parents=True)
    (root / compare.EXAMPLES / 'tank' / 'model.scn').write_text(TANK)
    owner = f'{compare.EXAMPLES}.tank'
    compare.capture_extra(owner, out, root)
    assert compare.failures(out) == []
    assert sorted(path.name for path in (out / owner).iterdir()) == [
        'default.json',
        'order.json',
        'structure.json',
    ]
    order = json.loads((out / owner / 'order.json').read_text())
    assert order['[]']['quantities'] == ['tank.water'] and order['[]']['moment'] == ['tank.close']
    assert order['[]']['triggers'] == {'tank.close': ['timer', None, None]}
    default = json.loads((out / owner / 'default.json').read_text())
    states = default['states']['base']
    assert states['names'] == ['tank.water']
    # The one step is the timer, at the time that the model writes; the run has no numerical segment.
    assert [(row['t'], row['written']) for row in states['steps']] == [(CLOSE, CLOSE)]
    assert states['numerical_from'] is None
    assert states['grid'][-1]['t'] == 10.0
    assert states['grid'][-1]['values'][0] == pytest.approx(RATE * CLOSE, rel=1e-12)
    # A file that does not compile is a capture failure, which fails a comparison.
    (root / compare.EXAMPLES / 'tank' / 'model.scn').write_text(TANK.replace('horizon 10 h', 'horizon 10'))
    compare.capture_extra(owner, tmp_path / 'broken', root)
    assert [name for name, _ in compare.failures(tmp_path / 'broken')] == [f'{owner}/default.json']


def test_the_acceptance_fixture_is_captured_with_its_own_library(tmp_path):
    owner = compare.ACCEPTANCE[0]
    compare.capture_extra(owner, tmp_path, catalogue.ROOT)
    assert compare.failures(tmp_path) == []
    default = json.loads((tmp_path / owner / 'default.json').read_text())
    assert default['admissible'] and set(default['states']) == set(default['report']['runs'])


def test_the_canonical_form_writes_the_gate_and_the_times_of_a_trigger_in_one_way():
    joined = {
        'rules': {'r': {'trigger': {'when': 'a == 1 and t >= x', 'gate': '(a == 1)', 'times': ['e + (d)']}}}
    }
    plain_form = {
        'rules': {'r': {'trigger': {'when': 'a == 1 and t >= x', 'gate': 'a == 1', 'times': ['e + d']}}}
    }
    assert compare.canonical('structure', joined) == compare.canonical('structure', plain_form)
    other = {'rules': {'r': {'trigger': {'when': 'a == 1 and t >= x', 'gate': 'a == 2', 'times': ['e + d']}}}}
    assert compare.canonical('structure', joined) != compare.canonical('structure', other)
    # Brackets that change the meaning stay a difference.
    grouped = {'rules': {'r': {'trigger': {'when': 'w', 'gate': 'a - (b - c)', 'times': []}}}}
    flat = {'rules': {'r': {'trigger': {'when': 'w', 'gate': 'a - b - c', 'times': []}}}}
    assert compare.canonical('structure', grouped) != compare.canonical('structure', flat)


# ---- the comparison of a change of the numerical core -----------------------------------------------

EVENT = 40.0  # the time of the made-up run's one moment, in hours


def run_report(t_event=EVENT, water=0.4, written=None, numerical_from=0.0, **changes):
    """(the report, the numbers) of a made-up run with two steps at one moment. By default a root can
    give the moment's time: the model writes none for it, and a numerical segment starts before it."""
    outcome, order = changes.get('outcome', 'open'), changes.get('order', ('decide', 'spill'))
    trace = [
        {'t': t_event, 'step': k + 1, 'rule': rule, 'event': f'{rule}.{outcome}', 'outcome': outcome}
        | {'changes': {'gate': 'open'} if rule == 'decide' else {'water': water}}
        | {'transfers': [['water', 'spilled', changes.get('moved', 0.25)]] if rule == 'spill' else []}
        for k, rule in enumerate(order)
    ]
    level = changes.get('level', water)
    report = {
        'label': 'Base',
        'samples': [
            {'t': 120.0, 'values': {'spilled': 0.5, 'level': level}, 'statuses': {'spilled': 'estimated'}}
        ],
        'reporting_points': {'final': {'t': 120.0, 'values': {'spilled': 0.5, 'level': level}}},
        'trace': trace,
        'health': [{'t': 120.0, 'entities': {'reservoir': {'status': changes.get('status', 'ok')}}}],
        'numerical_diagnostics': [],
        'peaks': {
            'level': {
                'value': changes.get('peak', 0.7),
                't': changes.get('peak_t', t_event),
                'certified': False,
            }
        },
    }
    states = {
        'names': ['water', 'spilled'],
        'tolerances': changes.get('tolerances', [1e-10, 1e-10]),
        'numerical_from': numerical_from,
        'discrete': ['decide__count', 'decide__time', 'gate'],
        'formulas': ['headroom'],
        'steps': [
            {'t': t_event, 'values': [0.7, 0.0], 'discrete': [1, t_event, 'open'], 'written': written},
            {'t': t_event, 'values': [water, 0.0], 'discrete': [1, t_event, 'open'], 'written': written},
        ],
        'grid': [
            {
                't': 120.0,
                'values': [water, 0.5],
                'discrete': [1, t_event, 'open'],
                'formulas': [changes.get('headroom', 1 - water)],
            }
        ],
    }
    return report, states


def study_record(**changes):
    report, states = run_report(**changes)
    return {
        'admissible': True,
        'diagnostics': [],
        'report': {'model_hash': 'm', 'runs': {'base': report}},
        'trajectories': {'base': {'parts': {'_steps': str(sorted(changes.items()))}}},
        'states': {'base': states},
    }


def sorted_studies(a, b, record='default'):
    found = compare.Sorted()
    compare.sort_record(found, record, through_json(a), through_json(b))
    return found


def test_equal_studies_have_nothing_to_sort_and_the_form_of_a_trajectory_is_left_out():
    found = sorted_studies(study_record(), study_record())
    assert (found.within, found.shifted, found.discrete, found.beyond) == (0, 0, [], [])
    # The record of a trajectory's parts differs between two revisions (it is of one's own form).
    other = study_record()
    other['trajectories'] = {'base': {'parts': {'_steps': 'another form'}}}
    assert not sorted_studies(study_record(), other).failed


def test_a_value_within_its_tolerance_needs_no_word_and_one_beyond_it_must_be_explained():
    near = 0.4 * (1 + 0.5 * compare.VALUE_RELATIVE)
    found = sorted_studies(study_record(), study_record(water=near))
    assert found.within > 0 and not found.failed
    far = 0.4 * (1 + 3 * compare.VALUE_RELATIVE)
    found = sorted_studies(study_record(), study_record(water=far))
    assert found.beyond and not found.discrete and found.failed
    # With the same tolerances on both sides, the comparison is the same from either side.
    back = sorted_studies(study_record(water=far), study_record())
    assert (back.within, len(back.beyond)) == (found.within, len(found.beyond))
    # The amount of a move and the value of a peak are values too.
    assert sorted_studies(study_record(), study_record(moved=0.25 * (1 + 3 * compare.VALUE_RELATIVE))).beyond
    assert not sorted_studies(
        study_record(), study_record(moved=0.25 * (1 + 0.5 * compare.VALUE_RELATIVE))
    ).failed
    assert sorted_studies(study_record(), study_record(peak=0.7 * (1 + 3 * compare.VALUE_RELATIVE))).beyond


def test_a_small_quantity_takes_its_absolute_tolerance_and_an_outcome_a_small_floor():
    floor = compare.VALUE_TOLERANCES * 1e-10
    # `water` is a quantity: next to zero, half of what its tolerance allows is within it.
    assert not sorted_studies(study_record(water=0.0), study_record(water=0.5 * floor)).failed
    assert sorted_studies(study_record(water=0.0), study_record(water=3 * floor, level=0.0)).beyond
    # An outcome has no tolerance of its own. Next to zero it takes a small absolute floor, so a
    # residue of roundoff needs no word; more than a share of its largest value does.
    assert not sorted_studies(study_record(level=0.0, peak=0.0), study_record(level=1e-18, peak=0.0)).failed
    assert sorted_studies(
        study_record(level=0.0), study_record(level=3 * compare.VALUE_RELATIVE * 0.7)
    ).beyond


def test_a_quantity_far_below_its_size_cannot_change_by_a_large_part_unseen():
    """The absolute tolerance of a quantity follows its authored size. With a size far above the values,
    a thousand tolerances are more than the values themselves, so the absolute term is also held to a
    share of the quantity's largest value in the base run."""
    loose = [1e-3, 1e-10]  # the absolute tolerance of `water`, whose largest value is 0.7
    base = study_record(tolerances=loose)
    assert compare.VALUE_TOLERANCES * loose[0] > 0.7 > compare.VALUE_SHARE * 0.7 < loose[0]
    # Only the quantity changes: the outcome and the formula that read it keep their values, so that
    # the test is of the quantity's own tolerance.
    same = {'level': 0.4, 'headroom': 0.6}
    found = sorted_studies(base, study_record(tolerances=loose, water=0.4 * 1.09, **same))
    assert found.beyond and not found.discrete
    # One absolute tolerance is always allowed: the solver itself promises no more.
    assert not sorted_studies(base, study_record(tolerances=loose, water=0.4 + 0.5 * loose[0], **same)).failed
    # With a tolerance far below the values, the share is the bound.
    tight = [1e-5, 1e-10]
    base = study_record(tolerances=tight)
    share = compare.VALUE_SHARE * 0.7
    assert tight[0] < share < compare.VALUE_TOLERANCES * tight[0]
    assert not sorted_studies(base, study_record(tolerances=tight, water=0.4 + 0.5 * share, **same)).failed
    assert sorted_studies(base, study_record(tolerances=tight, water=0.4 + 3 * share, **same)).beyond


def test_a_time_that_a_root_can_give_shifts_a_little_and_the_moment_counts_once():
    shift = 0.5 * compare.LOCATED_TIME_RELATIVE * EVENT
    found = sorted_studies(study_record(), study_record(t_event=EVENT + shift))
    # Two steps, their rows, a peak and the discrete values hold the time: one moment shifted.
    assert found.shifted == 1 and found.largest_shift == pytest.approx(shift) and not found.failed
    late = sorted_studies(
        study_record(), study_record(t_event=EVENT + 3 * compare.LOCATED_TIME_RELATIVE * EVENT)
    )
    assert late.beyond
    close = sorted_studies(
        study_record(written=EVENT), study_record(written=EVENT, t_event=EVENT + 0.5 * compare.EXACT_TIME_H)
    )
    assert close.within > 0 and close.shifted == 0 and not close.failed


def test_a_time_that_the_model_writes_and_a_time_before_the_numerical_segments_cannot_shift():
    shift = 0.5 * compare.LOCATED_TIME_RELATIVE * EVENT
    # A timer on inputs: the model writes its time, whatever the solver does around it.
    timer = sorted_studies(study_record(written=EVENT), study_record(written=EVENT, t_event=EVENT + shift))
    assert timer.beyond and timer.shifted == 0
    # A closed form: no numerical segment starts before the moment, or the run has none.
    for start in (EVENT + 1, None):
        exact = sorted_studies(
            study_record(numerical_from=start), study_record(numerical_from=start, t_event=EVENT + shift)
        )
        assert exact.beyond and exact.shifted == 0


def test_the_time_of_a_peak_takes_the_tolerance_of_a_located_time_and_is_not_counted():
    # A peak is the largest of the candidates that one engine's segments give: its time is no moment.
    near = EVENT + 0.5 * compare.LOCATED_TIME_RELATIVE * EVENT
    found = sorted_studies(study_record(), study_record(peak_t=near))
    assert not found.failed and found.shifted == 0
    far = EVENT + 3 * compare.LOCATED_TIME_RELATIVE * EVENT
    found = sorted_studies(study_record(), study_record(peak_t=far))
    assert found.beyond and all('/peaks/level/t' in line for line in found.beyond)


def test_the_side_under_test_cannot_widen_its_own_tolerance():
    shift = 0.5 * compare.LOCATED_TIME_RELATIVE * EVENT
    # The base says that the model writes the time; the tree says that a root can give it.
    found = sorted_studies(study_record(written=EVENT), study_record(written=None, t_event=EVENT + shift))
    assert found.beyond
    # The base's tolerances judge the values, and another list of tolerances is a difference itself.
    wide = study_record(water=0.5, tolerances=[1.0, 1.0])
    found = sorted_studies(study_record(), wide)
    assert found.beyond and any('tolerances' in line for line in found.discrete)
    # A base without the tolerances and the written times cannot judge: it is captured again.
    old = study_record()
    del old['states']['base']['numerical_from']
    found = sorted_studies(old, study_record())
    assert any('capture the base again' in line for line in found.discrete)


@pytest.mark.parametrize(
    'bad, other',
    [(math.inf, 0.4), (0.4, math.inf), (math.nan, math.nan), (math.nan, 0.4), (-math.inf, math.inf)],
)
def test_a_number_that_is_not_finite_is_listed(bad, other):
    found = sorted_studies(study_record(water=bad), study_record(water=other))
    assert found.beyond and all('not finite' in line or 'apart' in line for line in found.beyond)


def test_a_time_that_is_not_finite_is_listed_and_never_a_shift():
    found = sorted_studies(study_record(), study_record(t_event=math.inf))
    assert found.beyond and found.shifted == 0


@pytest.mark.parametrize(
    'change',
    [
        {'outcome': 'wait'},  # another outcome of a firing
        {'order': ('spill', 'decide')},  # two steps of one moment in the other order
        {'status': 'failed'},  # another status of a thing
    ],
)
def test_a_discrete_difference_must_be_explained(change):
    found = sorted_studies(study_record(), study_record(**change))
    assert found.discrete and found.failed


def test_a_missing_step_a_warning_and_a_changed_admission_are_discrete_differences():
    base = study_record()
    shorter = study_record()
    shorter['report']['runs']['base']['trace'].pop()
    shorter['states']['base']['steps'].pop()
    assert sorted_studies(base, shorter).discrete
    warned = study_record()
    warned['report']['runs']['base']['numerical_diagnostics'] = [{'code': 'slow', 'severity': 'warning'}]
    assert sorted_studies(base, warned).discrete
    noted = study_record()
    noted['report']['runs']['base']['numerical_diagnostics'] = [
        {'code': 'boundary_roundoff', 'severity': 'info'}
    ]
    found = sorted_studies(base, noted)
    assert not found.failed and found.within == 1  # a note more or less needs no word
    refused = {**study_record(), 'admissible': False}
    assert sorted_studies(base, refused).discrete


def test_records_of_different_forms_are_differences_and_never_a_crash():
    base = study_record()
    for break_it in (
        lambda r: r['report']['runs'].__setitem__('base', None),
        lambda r: r['report']['runs']['base'].__setitem__('samples', [None]),
        lambda r: r['report']['runs']['base'].__setitem__('peaks', {'level': None}),
        lambda r: r['report']['runs']['base'].__setitem__('trace', [None, None]),
        lambda r: r['states']['base'].__setitem__('steps', [None, None]),
        lambda r: r['states'].__setitem__('base', None),
        lambda r: r.__setitem__('report', None),
    ):
        broken = study_record()
        break_it(broken)
        assert sorted_studies(base, broken).failed and sorted_studies(broken, base).failed


def test_the_studies_of_the_sweeps_are_sorted_each_by_its_name():
    base = {'one': study_record(), 'two': study_record()}
    near = {'one': study_record(), 'two': study_record(water=0.4 * (1 + 0.5 * compare.VALUE_RELATIVE))}
    found = sorted_studies(base, near, record='sweeps')
    assert found.within > 0 and not found.failed
    far = {'one': study_record(), 'two': study_record(water=0.5)}
    found = sorted_studies(base, far, record='sweeps')
    assert found.beyond and all(line.startswith('/two/') for line in found.beyond)
    assert sorted_studies(base, {'one': study_record()}, record='sweeps').discrete  # a sweep on one side only
    assert sorted_studies(base, far, record='edits').beyond


def test_the_command_compares_within_tolerance_only_when_asked(tmp_path, capsys):
    near = study_record(water=0.4 * (1 + 0.5 * compare.VALUE_RELATIVE))
    write(tmp_path, 'base', 'SC97', default=through_json(study_record()), order={'[]': {'rules': ['decide']}})
    write(tmp_path, 'tree', 'SC97', default=through_json(near), order={'[]': {'rules': ['decide']}})
    assert compare.judge(tmp_path / 'base', tmp_path / 'tree') == 1
    assert 'records differ' in capsys.readouterr().out
    assert compare.judge(tmp_path / 'base', tmp_path / 'tree', tolerance=True) == 0
    out = capsys.readouterr().out
    assert 'WITHIN THE CONTRACT' in out and 'within tolerance' in out
    # The compiled order still compares exactly.
    write(tmp_path, 'tree', 'SC97', default=through_json(near), order={'[]': {'rules': ['spill']}})
    assert compare.judge(tmp_path / 'base', tmp_path / 'tree', tolerance=True) == 1
    assert 'differences to explain' in capsys.readouterr().out


# A model with a crossing that a numerical segment locates: the rate of `risk_time` changes where the
# water passes a level, so the engine integrates the segments around it. A timer at TICK hours fires
# while a numerical segment runs, and sets the time of a check, AHEAD hours later. An event waits WAIT
# hours after the timer, and another fires ECHO hours after it. An event follows the crossing by
# FOLLOW hours, and one more follows that one by ECHO hours.
TICK, WAIT, FOLLOW, AHEAD, ECHO = 30.0, 3.0, 2.0, 7.0, 11.0
# More waits on the timer: one whose delay, HELD hours, another event changes while it waits; one whose
# delay is drawn; one whose delay reads the time, and ends at BACK hours. Two events have a timer and a
# wait on the crossing: one at BOTH hours, after the crossing's wait has ended, so the timer gives its
# time; one whose timer is early, so the crossing gives its time.
HELD, STRETCH, BACK, BOTH, EARLY, LAG = 5.0, 2.0, 50.0, 60.0, 10.0, 1.5
BASIN = f"""scenario "A basin that fills"
    summary "Water runs into a basin. A valve opens at a level."
    horizon 5 days
    scope "The basin."

basin:
    "The basin."
    input inflow: fraction/day = 0.06 fraction/day in 0 fraction/day to 0.08 fraction/day
        "Water that runs in"
        @assumption "The test assumes this rate."
    input level: fraction = 0.7 in 0.5 to 1
        "Level at which the valve opens"
        @assumption "The test assumes this level."
    var water: fraction = 0.6 size 1
        "Water in the basin"
        @assumption "The test assumes this start."
    var valve: "closed" | "open" = "closed"
        "Valve"
    var spilled: fraction = 0 size 1
        "Water let out"
        @identity "The water that goes out, counted once."
    output spilled
    var risk_time: h = 0 h size 120 h
        "Time above the risk level"
        @identity "The hours above the risk level."
    output risk_time
    var due: h = 119 h in 0 h to 500 h
        "Time of the check"
        @assumption "The test assumes this time."
    var seen: h = 119 h in 0 h to 500 h
        "Time of the look"
        @assumption "The test assumes this time."
    flow storm: -> water at inflow
    flow spill: water -> spilled at 0.15 fraction/day while valve is "open"
    flow at_risk: -> risk_time at 1 if water >= 0.65 else 0
    event open once when water >= level:
        "The valve opens."
        @assumption "The test assumes this rule."
        valve = "open"
        seen = t + {AHEAD} h
    event look once when t >= seen:
        "A look, at the time that the crossing set."
        @assumption "The test assumes this rule."
    event tick once when t >= {TICK} h:
        "A timer."
        @assumption "The test assumes this time."
        due = t + {AHEAD} h
    event check once when t >= due:
        "A check, at the time that the timer set."
        @assumption "The test assumes this rule."
    event echo once when since(tick) >= {ECHO} h:
        "A step that follows the timer."
        @assumption "The test assumes this wait."
    event report once after {WAIT} h when count(tick) > 0:
        "A report, some hours after the timer."
        @assumption "The test assumes this wait."
    event follow once when since(open) >= {FOLLOW} h:
        "A step that follows the crossing."
        @assumption "The test assumes this wait."
    event trail once when since(follow) >= {ECHO} h:
        "A step that follows the step after the crossing."
        @assumption "The test assumes this wait."
    var patience: h = {HELD} h in 0 h to 500 h
        "The wait of the held event"
        @assumption "The test assumes this wait."
    event held once after patience when count(tick) > 0:
        "A step that waits for a time that changes while it waits."
        @assumption "The test assumes this rule."
    event stretch once when t >= {TICK + STRETCH} h:
        "The wait gets longer, after the held event has read it."
        @assumption "The test assumes this rule."
        patience = {HELD + 4} h
    event drawn once after pert(1 h, 3 h, 12 h) when count(tick) > 0:
        "A step that waits for a drawn time."
        @assumption "The test assumes this wait."
    event back once after {BACK} h - t when count(tick) > 0:
        "A step whose wait reads the time."
        @assumption "The test assumes this wait."
    event both once when t >= {BOTH} h and since(open) >= {LAG} h:
        "A step at a timer, after the wait on the crossing has ended."
        @assumption "The test assumes this rule."
    event either once when t >= {EARLY} h and since(open) >= {LAG} h:
        "A step at the end of the wait on the crossing, after its timer."
        @assumption "The test assumes this rule."
    event slow once after {FOLLOW} h when count(open) > 0:
        "A step that waits after the crossing."
        @assumption "The test assumes this wait."
"""


def basin_study(tmp_path, name, settings=None, edits=None):
    folder = tmp_path / name / 'basin'  # the folder names the scenario in the report
    folder.mkdir(parents=True)
    (folder / 'model.scn').write_text(BASIN)
    from napkin.engine import edits_for
    from napkin.model import load_scenario

    model = load_scenario(folder / 'model.scn')
    study = evaluate_study(model, edits_for(model, edits) if edits else None, numerical_settings=settings)
    return through_json(compare._study(study))


def steps_of(record, rule):
    """[(the place in the trace, the trace entry, the row of the numbers)] of a rule's steps."""
    trace = record['report']['runs']['base']['trace']
    rows = record['states']['base']['steps']
    return [(k, entry, rows[k]) for k, entry in enumerate(trace) if entry['rule'] == rule]


def moved_in_time(record, rule, shift):
    """A copy of a study's record with each step of one rule later by `shift`, and with each discrete
    time that says when it happened."""
    changed = json.loads(json.dumps(record))
    for _, entry, row in steps_of(changed, rule):
        old = entry['t']
        entry['t'] = row['t'] = old + shift
        states = changed['states']['base']
        for other in states['steps'] + states['grid']:
            other['discrete'] = [old + shift if value == old else value for value in other['discrete']]
    return changed


def one_step(record, rule):
    ((_, entry, row),) = steps_of(record, rule)
    return entry, row


def test_the_capture_says_which_times_the_model_writes(tmp_path):
    base = basin_study(tmp_path, 'base')
    states = base['states']['base']
    opened, open_row = one_step(base, 'basin.open')
    ticked, tick_row = one_step(base, 'basin.tick')
    # The timer is at the time that the model writes, while a numerical segment runs around it.
    assert ticked['t'] == TICK and tick_row['written'] == TICK
    assert states['numerical_from'] is not None and states['numerical_from'] < TICK
    # What waits on the timer is written too: an event some hours after it, the event at the time
    # that the timer's step set, and the report, which triggers with the timer and fires a wait later.
    for rule, wait in (('basin.echo', ECHO), ('basin.check', AHEAD)):
        entry, row = one_step(base, rule)
        assert entry['t'] == pytest.approx(TICK + wait, abs=1e-9) and row['written'] == entry['t']
    report = steps_of(base, 'basin.report')
    assert [(entry['t'], row['written']) for _, entry, row in report] == [
        (TICK, TICK),
        (TICK + WAIT, TICK + WAIT),
    ]
    # A root gives the time of the crossing, so that time is not written. Neither is a time that waits
    # on it: the step after it, the step after that one, and the event at the time that its step set.
    assert open_row['written'] is None
    for rule, wait in (
        ('basin.follow', FOLLOW),
        ('basin.trail', FOLLOW + ECHO),
        ('basin.look', AHEAD),
        ('basin.either', LAG),
    ):
        entry, row = one_step(base, rule)
        assert entry['t'] == pytest.approx(opened['t'] + wait, abs=1e-9) and row['written'] is None
    assert EARLY < opened['t'] + LAG < BOTH


def firing(record, rule):
    """(the trace entry, the row of the numbers) of the firing of a rule that waits."""
    ((_, triggered, _), (_, entry, row)) = steps_of(record, rule)
    assert triggered['outcome'] is None and entry['outcome'] is not None
    return triggered, entry, row


def test_the_time_of_a_firing_that_waits_is_written_when_its_trigger_and_its_delay_are(tmp_path):
    base = basin_study(tmp_path, 'base')
    opened, _ = one_step(base, 'basin.open')
    # The engine reads a delay as the rule triggers. Another event makes the delay longer while the
    # rule waits: the firing stays where the first delay put it, and its time is written.
    triggered, entry, row = firing(base, 'basin.held')
    stretched, _ = one_step(base, 'basin.stretch')
    assert triggered['t'] == TICK < stretched['t'] < entry['t'] == TICK + HELD == row['written']
    # A drawn delay is no number of the solver, and a delay that reads the time is exact at a timer.
    triggered, entry, row = firing(base, 'basin.drawn')
    assert triggered['t'] == TICK and TICK + 1 < entry['t'] < TICK + 12 and row['written'] == entry['t']
    _, entry, row = firing(base, 'basin.back')
    assert entry['t'] == BACK == row['written']
    # A wait after the crossing carries the crossing's accuracy.
    triggered, entry, row = firing(base, 'basin.slow')
    assert triggered['t'] == opened['t'] and row['written'] is None
    assert entry['t'] == pytest.approx(opened['t'] + FOLLOW, abs=1e-9)


def test_a_timer_gives_the_time_of_a_step_whose_located_wait_ended_before_it(tmp_path):
    base = basin_study(tmp_path, 'base')
    entry, row = one_step(base, 'basin.both')
    assert entry['t'] == BOTH == row['written']


def test_a_located_step_of_a_real_run_can_shift_and_its_timer_cannot(tmp_path):
    base = basin_study(tmp_path, 'base')
    opened, _ = one_step(base, 'basin.open')
    shift = 0.5 * compare.LOCATED_TIME_RELATIVE * max(1.0, opened['t'])
    # The crossing, and each step that waits on it, take the tolerance of a time that a root gives.
    for rule in ('basin.open', 'basin.follow', 'basin.trail', 'basin.look'):
        found = compare.Sorted()
        compare.sort_study(found, '', base, moved_in_time(base, rule, shift))
        assert found.shifted == 1 and not found.failed, rule
    found = compare.Sorted()
    compare.sort_study(found, '', base, moved_in_time(base, 'basin.either', shift))
    assert found.shifted == 1 and not found.failed
    # The timer, and each step that waits on it, cannot shift.
    for rule in ('basin.tick', 'basin.echo', 'basin.check', 'basin.held', 'basin.drawn', 'basin.back'):
        found = compare.Sorted()
        compare.sort_study(found, '', base, moved_in_time(base, rule, shift))
        assert found.beyond and found.shifted == 0, rule
    found = compare.Sorted()
    compare.sort_study(found, '', base, moved_in_time(base, 'basin.both', shift))
    assert found.beyond and found.shifted == 0


def test_a_looser_solver_is_within_the_contract_and_another_input_is_not(tmp_path):
    """A deliberate change of the numerics, through the real capture: the same run with a solver
    tolerance a hundred times looser has the same steps, and its numbers differ within the contract. The
    same run with another level has its event at another time, which the contract does not allow."""
    base = basin_study(tmp_path, 'base')
    looser = basin_study(tmp_path, 'looser', settings={'rtol': 1e-7})
    found = compare.Sorted()
    compare.sort_study(found, '', base, looser)
    # The numerical settings are in the report, and they differ on purpose: nothing else is discrete.
    assert found.discrete and all('numerical_settings/rtol' in line for line in found.discrete)
    assert not found.beyond and found.within > 0
    assert compare.differences(base['report']['runs'], looser['report']['runs'])  # the bits do differ
    moved = basin_study(tmp_path, 'moved', edits={'set': {'basin.level': 0.72}})
    found = compare.Sorted()
    compare.sort_study(found, '', base, moved)
    assert found.beyond
