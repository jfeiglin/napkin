"""A distribution with arguments by name, compiled and run: `normal(2 h, sd=40 h, max=3 h, min=1 h)`.

The oracles are properties of the distributions. Each draw is inside the bounds that `min` and `max`
name, although the spread that `sd` or `gsd` names is much wider than the bounds. The central value
is the median, which symmetry gives: a normal cut at the same distance on each side of its mean has
its mean as median, and a lognormal cut at the same ratio on each side of its median keeps its
median. An argument that the reader took by its place, and not by its name, would break each of
these.

A file writes an argument by name in the distribution of an input or of a `let`. The grammar of an
expression has no `=`, so a file cannot write one in a line of an event. For that case the test
gives the resolver the tree of the line with its arguments by name (`by_name`), and the rest of the
compiler and the engine run as they are.
"""

from __future__ import annotations

import ast
from dataclasses import replace

import pytest

from napkin.core import expr as typed
from napkin.engine import SamplingSettings, evaluate_uncertainty
from napkin.engine.report import evaluate_outputs
from napkin.engine.runtime import simulate
from napkin.model import resolved
from napkin.model.language import expressions
from tests.build import block, compiled, document, entity, library, rejected, stock, timer

HOURS = 120  # one firing an hour


def test_the_draws_of_an_input_stay_inside_the_bounds_that_its_named_arguments_give():
    """served(24 h) = rate * end (`timer`): each sample runs with its own draws. An argument by name
    is a number with its unit or a computation of such numbers: the bounds of the rate are 1 and
    3 people/h, and the bounds of the end are 4 h and 9 h (0.375 days)."""
    model = compiled(
        timer(
            rate='normal(2 people/h, sd=2 * 20 people/h, max=1 people/h + 2 people/h, '
            'min=max(1 people/h, 12 people/day))',
            end='lognormal(median=6 h, gsd=4 * 5, min=4 h, max=0.375 days)',
        )
    )
    # The central run takes the medians.
    assert model.run_values('a')['s.rate'] == pytest.approx(2, rel=1e-12)
    assert model.run_values('a')['s.end'] == pytest.approx(6, rel=1e-12)
    result = evaluate_uncertainty(model, None, SamplingSettings(48, 5, 'random'))
    assert result.admissible, result.diagnostics
    sampled = result.samples['a']
    rates = [values['s.rate'] for values in sampled['values']]
    ends = [values['s.end'] for values in sampled['values']]
    assert len(set(rates)) == len(set(ends)) == 48
    assert all(1 <= rate <= 3 for rate in rates)
    assert all(4 <= end <= 9 for end in ends)
    for rate, end, completed in zip(rates, ends, sampled['runs']):
        (row,) = evaluate_outputs(completed, library(), [completed['trajectory'].horizon])
        assert row['values'][model.outputs['served']] == pytest.approx(rate * end, rel=1e-9)


def clock(line):
    """A clock that fires `tick` every hour from 1 h. Each firing reads `line`."""
    return document(
        'Named arguments',
        entity(
            'clock',
            stock('next', 1, 'h', minimum=None, maximum=HOURS + 2, size=None, kind='state'),
            stock('total', 0, 'people', size=1000),
            stock('seen', 0, 'people', minimum=None, maximum=1000, size=None, kind='state'),
            block('event tick when t >= next:  @fixture', '"A tick."', 'next += 1 h', line),
        ),
        horizon=HOURS,
    )


def increments(model, luck=None):
    """What each firing of `tick` added to the total."""
    rs = model.resolve('a')
    if luck is not None:
        rs = replace(rs, luck=luck)
    trajectory = simulate(rs, library())
    totals = [trajectory.env_at(hour + 0.5)['clock.total'] for hour in range(1, HOURS)]
    return [b - a for a, b in zip([0.0, *totals[:-1]], totals)]


def by_name(read):
    """A reader of the tokens of an expression that gives each call of `normal` with four arguments
    by place as the call with the last three by name, in another order: `normal(mean, max=…, sd=…,
    min=…)`. `read` is the grammar's reader (`expressions.tree`)."""

    def tree(tokens):
        made, names = read(tokens)
        for part in ast.walk(made):
            if isinstance(part, ast.Call) and isinstance(part.func, ast.Name) and part.func.id == 'normal':
                mean, sd, low, high = part.args
                part.args = [mean]
                part.keywords = [
                    ast.keyword(arg='max', value=high),
                    ast.keyword(arg='sd', value=sd),
                    ast.keyword(arg='min', value=low),
                ]
        return made, names

    return tree


LINE = 'total += normal(2 people, 40 people, 1 people, 3 people + seen)'


def drawn_of(model):
    """The typed nodes of the distribution that the last line of `tick` adds to the total."""
    (tick,) = model.scenario.entity('clock').events
    return tick.outcomes[0].lines[-1].value.right


def test_the_draws_of_a_line_of_an_event_stay_inside_the_bounds_that_its_named_arguments_give(monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(expressions, 'tree', by_name(expressions.tree))
        model = compiled(clock(LINE))
    drawn = drawn_of(model)
    assert type(drawn) is resolved.Named
    assert [key for key, _ in drawn.named] == ['max', 'sd', 'min']
    # An argument by name reads a value of the model as an argument by place does.
    assert any(type(part) is resolved.Ref for part in typed.walk(drawn.named[0][1]))
    # The central run takes the median at each firing, which is the mean: the bounds are 1 person
    # on each side of it.
    assert increments(model) == pytest.approx([2.0] * (HOURS - 1))
    luck = {'seed': 3, 'sample': 0}
    added = increments(model, luck)
    assert len(set(added)) == len(added)  # each firing draws again
    assert all(1.0 <= value <= 3.0 for value in added)
    # The same arguments by place give the same draws, bit for bit.
    by_place = compiled(clock(LINE))
    assert type(drawn_of(by_place)) is typed.Call
    assert increments(by_place, luck) == added


@pytest.mark.parametrize(
    'value',
    [
        # Two stars before an argument are the one form of an argument with no place that the
        # grammar of an expression reads. No function of the language takes it.
        'uniform(1 people, ** seen)',
        'max(seen, ** seen)',
        'delayed(seen, ** seen)',
    ],
)
def test_an_argument_with_two_stars_is_refused_at_its_line(value):
    assert ('build', 'clock/tick/done/1') in rejected(clock(f'total += {value}'), library())
