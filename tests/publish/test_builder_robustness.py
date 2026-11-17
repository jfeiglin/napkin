"""Publication builders render every valid model file, and a value that is not estimated is never
a number."""

import json
import re

import pytest

from tests.build import (
    block,
    compiled,
    drop,
    evidence_library,
    in_place,
    member,
    number_of,
    option,
    options,
    output,
    quote,
    sc99,
    scenario,
)
from tests.helpers import ROOT
from tests.owned import block_at, write_scenario
from tests.publish.test_pages import Written, after, before, edited, uncited
from tools import catalogue
from tools.publish import Context, assumptions
from tools.publish.formatting import dollars
from tools.publish.methods import scenario_methods
from tools.publish.pages import Pages


def started_off():
    """The analytic fixture, plus a run whose service is off from the start.

    The profile that sets the start state gives that run a structure of its own. It declares no
    first move, which a file outside the catalogue may leave out.
    """
    return edited(
        scenario(),
        before(
            'runs:',
            options(
                'Start',
                option('Running', 'The service runs at the start.'),
                option(
                    'Off at the start',
                    'The service is off from the start.',
                    'service.state = "off"  @fixture',
                ),
            ),
            '',
        ),
        member('runs:', 'c = "Default" + "Off at the start"'),
    )


def test_a_definition_that_every_structure_shares_keeps_one_unlabelled_row():
    text = started_off()
    written = Written(text)
    model = compiled(text)
    assert len(model.structures) == 2
    methods = scenario_methods(model, link=lambda target: target)
    # The output has one row, and its first cell is its label alone: no note names a profile or a run.
    label = written.texts['output:/delivered/""']
    outputs = methods.split('## Calculated outcomes')[1].split('\n## ')[0]
    rows = [line for line in outputs.splitlines() if line.startswith(f'| {label}')]
    assert len(rows) == 1 and rows[0].startswith(f'| {label} |')
    # An input has one definition, so each keeps one unlabelled row.
    values = {
        m.name: m for m in written.thing('service').members if getattr(m, 'kind', None) in ('input', 'fixed')
    }
    inputs = methods.split('## Inputs and their sources')[1].split('\n## ')[0]
    cells = [line[2:-2].split(' | ') for line in inputs.splitlines() if line.startswith('| ')][1:]
    assert [(row[0], row[1], row[-2], row[-1]) for row in cells] == [
        (
            f'{line.text.value} (`service.{f}`)',
            written.typed(f'service/{f}'),
            '–'.join(str(number_of(written.keyed(f'service/{f}/{edge}:'))) for edge in ('min', 'max')),
            written.record(line.support[0].name)['explanation'],
        )
        for f, line in values.items()
    ]


def without_main_controls(text):
    """A file whose profiles set no input, so that the pages have no main controls: its only
    profile is the defender response `Default`, which sets nothing."""
    return edited(text, drop('options:/Rate', 'runs:/b'))


def test_the_assumption_inventory_takes_assumptions_without_title_or_supports(tmp_path):
    lib = evidence_library()
    lib['assumptions'].append(
        {'id': 'A-BARE', 'statement': 'Bare.', 'rationale': 'Fixture.', 'review': {'status': 'unreviewed'}}
    )
    text = edited(
        sc99(),
        uncited('service/n'),
        after('service/n/""', in_place('assumption', 'Fixture.', assumption='A-BARE')),
    )
    write_scenario(tmp_path, text, lib)
    output = assumptions.artifacts(Context(tmp_path))
    records = {
        a['id']: a
        for a in json.loads(output[catalogue.result('SC99', 'assumption-review.json')])['assumptions']
    }
    bare = records['A-BARE']
    assert (bare['title'], bare['cited_claims']) == ('A-BARE', [])
    # One line of the file names the assumption: the line of the value that it supports.
    (place,) = bare['places']
    text = (tmp_path / 'scenarios/SC99/model.scn').read_text(encoding='utf-8')
    assert 'A-BARE' in block_at(text, place) and place.endswith('/n')
    assert records['RT-FIXTURE']['cited_claims'] == [{'claim': 'C-ACTION', 'relation': 'mechanism_precedent'}]


def test_money_units_are_exactly_the_librarys_single_currency_units_at_their_scale():
    units = catalogue.vocabulary(ROOT)['units']
    for name, unit in units.items():
        (dimension, power), *others = unit['dimensions'].items() or [(None, None)]
        money = not others and power == 1 and bool(re.fullmatch(r'USD(\d{4})?', dimension or ''))
        assert (dollars(name) is not None) == money, name
        if money:
            assert dollars(name) == unit['scale'], name
    assert dollars('USD2025-hours') is None and dollars('USD2025/h') is None


def declared_unestimated_clinical(root):
    """The analytic transfer started by a cyber incident, which states that it does not estimate its
    deaths or its serious casualties, and estimates its economic loss."""
    text = edited(
        without_main_controls(sc99()),
        after(
            'output:/delivered',
            output(
                'deaths',
                None,
                'people',
                doc='Deaths',
                under=(
                    'category deaths',
                    'unestimated "The fixture does not convert its service loss into deaths."',
                ),
            ),
            output(
                'casualties',
                None,
                'people',
                doc='Serious casualties, including deaths',
                under=(
                    'category casualties',
                    'unestimated "The fixture does not convert its service loss into serious harm."',
                ),
            ),
            output(
                'economic_loss',
                'service.served * 5 USD2025 / 1 people',
                'USD2025',
                'net',
                doc='Economic loss',
                under=('category loss',),
            ),
        ),
        member(
            'notes:',
            block(
                'verification:',
                f'status: {quote("conditional_calculation")}',
                f'research: {quote("evidence/research.md")}',
            ),
        ),
    )
    (root / 'scenarios/SC99/evidence').mkdir(parents=True)
    (root / 'scenarios/SC99/evidence/research.md').write_text('# Fixture\n', encoding='utf-8')
    return text


def declared_harm_model(root):
    """The analytic fixture that declares that it does not estimate its deaths, its serious casualties
    or its economic loss, with the reason of each."""
    source = declared_unestimated_clinical(root)
    declarations = [
        output(
            name,
            None,
            unit,
            under=(
                f'category {category}',
                'unestimated "The fixture does not convert service outcomes into this harm."',
            ),
        )
        for name, category, unit in (
            ('deaths', 'deaths', 'people'),
            ('casualties', 'casualties', 'people'),
            ('economic_loss', 'loss', 'USD2025'),
        )
    ]
    source = edited(
        source,
        drop('output:/deaths', 'output:/casualties', 'output:/economic_loss'),
        after('output:/delivered', *declarations),
    )
    return compiled(source, evidence_library())


@pytest.mark.parametrize('declare_harms', [False, True])
def test_methods_accept_research_without_claiming_unmodeled_harm(tmp_path, declare_harms):
    if declare_harms:
        model = declared_harm_model(tmp_path)
    else:
        model = compiled(
            edited(
                sc99(),
                member('notes:', block('verification:', 'research: "fixture/research.md"')),
            ),
            evidence_library(),
        )
    verification = Pages(model).reviewed['verification']
    assert 'accounting' not in verification
    text = scenario_methods(model, link=lambda target: target)
    assert verification['research'] in text
    assert 'patient group' not in text and 'economic accounts' not in text


def test_methods_preserve_declared_accounting(tmp_path):
    lib = evidence_library()
    model = compiled(
        edited(
            declared_unestimated_clinical(tmp_path),
            member('notes:/verification:', 'accounting: "Fixture accounting boundary"'),
        ),
        lib,
    )
    verification = Pages(model).reviewed['verification']
    text = scenario_methods(model, link=lambda target: target)
    assert verification['research'] in text and verification['accounting'] + '.' in text
