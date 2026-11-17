"""The scenario's expected-order fixture detects altered comparisons."""

from scenarios.tests.test_catalogue import broken_expected_orders, edited_alike, expected_orders
from tests.helpers import catalogue_model


def test_an_order_binds_the_runs_an_edit_set_edits_alike_and_catches_a_fall():
    model = catalogue_model('iv_fluid_shortage')
    group = {option: g for g, options in model.menu.items() for option in options}
    edit = {'any.input': 1}
    for runs, _ in expected_orders('iv_fluid_shortage'):
        first = runs[0]
        assert edited_alike(model, {'set': edit}, runs)
        assert not edited_alike(model, {'runs': {first: edit}}, runs)
        assert edited_alike(model, {'runs': dict.fromkeys(runs, edit)}, runs)
        # An edit to an option of the first run reaches every run that shares the option.
        for option in model.runs[first]['options']:
            shared = all(option in model.runs[run]['options'] for run in runs)
            assert edited_alike(model, {'options': {option: edit}}, runs) == shared, (runs, group[option])
    # Equal values keep every order; a fall along a tuple, or a value that is not estimated, breaks it.
    names = {name for _, outputs in expected_orders('iv_fluid_shortage') for name in outputs}
    level = {
        run: dict.fromkeys(names, 1.0) for runs, _ in expected_orders('iv_fluid_shortage') for run in runs
    }

    def report(values):
        return {'runs': {run: {'reporting_points': {'final': {'values': v}}} for run, v in values.items()}}

    assert broken_expected_orders(model, report(level)) == []
    runs, outputs = expected_orders('iv_fluid_shortage')[0]
    for changed in (0.5, None):
        values = {run: dict(v) for run, v in level.items()}
        values[runs[-1]][outputs[0]] = changed
        broken = broken_expected_orders(model, report(values))
        assert (runs, outputs[0], [*[1.0] * (len(runs) - 1), changed]) in broken
