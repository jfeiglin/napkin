"""The category of an output is a tag that the language does not read (docs/language.md, §2.8).

An output of any category is accepted, and the report gives each output its category, as written. A
library lists no categories, and a tag changes no value.

Every expected value comes from the analytic transfer of tests/build.py, which serves min(n, rate *
end) people, with the inputs read from the model.
"""

import pytest

from napkin.engine import evaluate_study, sample_result
from tests.build import compiled, edit, library, output, replace, scenario


def tagged(**categories):
    """The analytic transfer with one more output of the people served for each `output=category`,
    after its output `delivered`."""
    delivered = output('delivered', 'service.served', 'people', doc='Delivered')
    more = [
        output(
            name, 'service.served', 'people', doc=f'People served ({name})', under=(f'category {category}',)
        )
        for name, category in categories.items()
    ]
    return edit(scenario(), replace(delivered, '\n'.join([delivered, *more])))


def finals(model):
    """{run: the final values of its outputs}."""
    return {
        run: item['reporting_points']['final']['values']
        for run, item in sample_result(evaluate_study(model))['runs'].items()
    }


def test_an_output_of_any_category_is_accepted_and_reported_with_its_tag():
    """`hurt`, `followed` and `deaths` are tags: the library names none of them."""
    model = compiled(tagged(injured='hurt', reached='followed', counted='deaths'), library())
    injured, reached, counted = (model.outputs[name] for name in ('injured', 'reached', 'counted'))
    for run, item in sample_result(evaluate_study(model))['runs'].items():
        values = model.run_values(run)
        served = min(values['service.n'], values['service.rate'] / 24 * values['service.end'])
        final = item['reporting_points']['final']
        for name in (injured, reached, counted):
            assert final['values'][name] == pytest.approx(served, rel=1e-6)
        # Each output keeps its tag, and an output with no category has none.
        found = {name: outcome.get('category') for name, outcome in item['outcomes'].items()}
        assert found == {
            model.outputs['delivered']: None,
            injured: 'hurt',
            reached: 'followed',
            counted: 'deaths',
        }


def test_a_tag_changes_no_value():
    """The same output with another tag, or with none, gives the same values in every run."""
    tags = [finals(compiled(tagged(served=category))) for category in ('deaths', 'loss', 'anything')]
    plain = finals(compiled(tagged()))
    for found in tags:
        assert {
            run: {k: v for k, v in values.items() if k != 'served'} for run, values in found.items()
        } == plain
        assert all(values['served'] == plain[run]['delivered'] for run, values in found.items())
