"""Who plays each part, in the pictures (PLAN.md, change 23 after G0): the model has no role, and the
stylesheet's `[role]` gives what a role gave until then, so that a picture is as it was: a card's
icon when `[icon]` names none, and its role in the map and the layout.

Each case is a picture model of tests/draw/ that wrote a role (models.py, test_picture.py,
test_style.py), now without it, with the same roles in its stylesheet's `[role]`, drawn as `napkin
draw` draws it: the package with its stylesheet beside it (`style.of`, which reads and checks it, as
`napkin compile` does), its map (`model_map.picture`) and its SVG text (`layout`, `svg`).
`roles.json` holds each case's map and the SHA-256 of its SVG text as the code before change 23 drew
them, with the roles in the model (scratch/rewrite/b1/audit3-s/make_expected.py, run on that code).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from napkin.draw import style
from napkin.draw.layout import layout
from napkin.draw.model_map import picture
from napkin.draw.svg import svg
from tests.draw import models, test_picture, test_style

EXPECTED = json.loads(Path(__file__).with_name('roles.json').read_text(encoding='utf-8'))

# {case: (the model, its stylesheet with the roles that the model wrote, its tables, its run)}
CASES = {
    'works': (models.WORKS, models.WORKS_ROLES, None, None),
    'works_styled': (models.WORKS, models.WORKS_STYLE, None, None),
    'works_contract': (models.WORKS, test_picture.CONTRACT_STYLE, None, None),
    'works_attack': (models.WORKS, models.WORKS_STYLE, None, 'attack'),
    'cards': (models.HEADER + test_picture.CARDS, test_picture.CARDS_ROLES, test_picture.WARDS, None),
    'states': (models.HEADER + test_picture.STATES, test_picture.STATES_ROLES, None, None),
    'plans': (test_picture.PLANS, test_picture.STATES_ROLES, None, None),
    'wards': (test_style.MODEL, test_style.ROLES, None, None),
    'wards_styled': (test_style.MODEL, test_style.STYLE, None, None),
    'wards_no_role': (test_style.NO_ROLE_MODEL, test_style.NO_ROLE_ROLES, None, None),
    'wards_table': (test_style.ROWS_MODEL, test_style.ROWS_ROLES, test_style.CREWS, None),
    'wards_stocked': (test_style.STOCKED, test_style.ROLES, None, None),
    'wards_text': (test_style.TEXT_MODEL, test_style.ROLES, None, None),
}


def test_each_case_has_the_picture_that_its_roles_gave_in_the_model():
    assert set(CASES) == set(EXPECTED)


@pytest.mark.parametrize('case', sorted(CASES))
def test_the_roles_of_the_stylesheet_draw_the_picture_that_the_roles_of_the_model_drew(tmp_path, case):
    text, sheet, tables, run = CASES[case]
    model = models.package(tmp_path / case, text, style=sheet, tables=tables)
    found = style.of(model)
    doc = picture(model, found, run=run)
    drawn = svg(doc, layout(doc, found)).encode()
    expected = EXPECTED[case]
    assert doc == expected['map']
    assert {'sha256': hashlib.sha256(drawn).hexdigest(), 'bytes': len(drawn)} == expected['svg']
