"""The drawing of every catalogue model: the properties of each test file of the drawing, on every
scenario of the catalogue. The catalogue is in the old language until stage M, so this file waits in
`tests/dormant.txt` and runs once the catalogue is migrated.

For each scenario, with its own stylesheet: the picture keeps its contract and names what its model
declares (`test_picture.py`); its layout and its SVG hold every property (`test_layout.py`,
`test_svg.py`), also with every card at `rules` (`test_trigger_levels.py`) and with every card in the
panels and the references shown (`test_drawn_panels.py`); the symbols of the drawn cards are one each
(`test_symbols.py`); every trigger line names what it reads (`test_triggers.py`); every expression
builds, keeps its value and reads back from its LaTeX (`test_notation.py`), and typesets
(`test_typeset.py`); the References of every input hold their properties (`test_references.py`).
"""

from __future__ import annotations

import dataclasses
import time
import xml.etree.ElementTree as ET
from functools import cache
from pathlib import Path

import pytest

from napkin.draw import notation, style
from napkin.draw.layout import layout
from napkin.draw.model_map import picture
from napkin.draw.svg import svg
from napkin.draw.symbols import symbols
from napkin.draw.things import Things
from napkin.draw.triggers import card_lines
from napkin.model.compile import load_scenario
from tests.selection import selected
from tools import catalogue

ROOT = Path(__file__).resolve().parents[2]
SCENARIO_IDS = selected(tuple(catalogue.entries(ROOT)))


@cache
def catalogue_model(scenario_id):
    """The compiled model of a scenario of the catalogue, and its things."""
    return Things(load_scenario(catalogue.scenario_path(ROOT, scenario_id)))


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_the_picture_of_every_scenario_keeps_the_contract_and_its_layout_and_svg_hold(scenario_id):
    from tests.draw.test_layout import check
    from tests.draw.test_picture import picture_problems
    from tests.draw.test_svg import check_model, check_svg

    found = catalogue_model(scenario_id)
    sheet = style.of(found.compiled)
    doc = picture(found, sheet)
    assert picture_problems(doc) == []
    start = time.perf_counter()
    placed = layout(doc)
    assert time.perf_counter() - start < 5.0
    check(doc, placed)
    text = svg(doc, placed)
    check_svg(doc, placed, text)
    check_model(found.compiled, ET.fromstring(text))


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_every_card_of_every_scenario_at_rules_and_in_the_panels(scenario_id):
    from tests.draw.test_drawn_panels import drawn
    from tests.draw.test_panels import check_latex, check_symbols
    from tests.draw.test_picture import picture_problems

    found = catalogue_model(scenario_id)
    own = style.of(found.compiled)
    shown = style.drawn(own, found)
    with_events = tuple(card for card in shown if found.events(card))
    sheet = dataclasses.replace(
        own, triggers=(('rules', with_events),), equations=tuple(shown), references_show=True
    )
    doc = picture(found, sheet)
    assert picture_problems(doc) == []
    drawn(doc)
    check_symbols(doc)
    check_latex(doc)
    for card in doc['cards']:
        if card['id'] in with_events:
            full = {line.key: line.full for line in card_lines(found, card['id'])}
            assert all(event['full'] == full[event['event']] for event in card['triggers']['events'])


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_the_symbols_and_the_lines_of_every_scenario(scenario_id):
    from tests.draw.test_symbols import check_symbols
    from tests.draw.test_triggers import check_lines

    found = catalogue_model(scenario_id)
    sheet = style.of(found.compiled)
    made = symbols(found, sheet)
    check_symbols(found, sheet, made)
    assert symbols(found, sheet) == made
    check_lines(found)


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_every_expression_of_every_scenario_keeps_its_value_and_typesets(scenario_id):
    from tests.draw.test_notation import (
        Point,
        canonical,
        kinds_of,
        latex_back,
        outcome,
        same,
        shape,
        value_of_node,
        value_of_typed,
    )
    from tests.draw.test_typeset import check_node, nodes_of

    found = catalogue_model(scenario_id)
    points = [Point(seed, kinds_of(found)) for seed in (1, 2)]
    for place, expression in notation.walk(found):
        keys = notation.keys_of(found, place)
        node = notation.build(expression, keys)
        text, back = latex_back(node)
        assert shape(canonical(back)) == shape(canonical(node)), (place, text)
        for point in points:
            expected = outcome(value_of_typed, expression, point, keys)
            assert same(outcome(value_of_node, node, point), expected), place
    for node in nodes_of(found):
        check_node(node)


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_the_references_of_every_scenario_hold_their_properties(scenario_id):
    """The References list of all the inputs of a scenario, as if the picture showed each one."""
    from napkin.draw.references import references
    from tests.draw.test_references import assert_holds, ids_of, leaks

    found = catalogue_model(scenario_id)
    cited = [
        ((card, value.name), value.evidence)
        for card in found.cards
        for value in found.values(card)
        if value.kind == 'input'
    ]
    refs = references(cited, found)
    assert_holds(found, cited, refs)
    assert not leaks(refs, ids_of(found) - {record.name for record in found.declared.records})
    assert references(cited, found) == refs
