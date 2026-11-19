"""The expected pictures of tests/draw/test_roles.py, made by the code before change 23 (PLAN.md,
"Changes after G0"), with the roles in the models: run it on that code (commit c94ab8f), from the
checkout, as `NAPKIN_STORE=off .venv/bin/python scratch/rewrite/b1/audit3-s/make_expected.py`.

Each case is a picture model of tests/draw/ that writes a role, as those files wrote it then, drawn
as `napkin draw` draws it: the package with its stylesheet beside it (`style.of`), its map
(`model_map.picture`) and its SVG (`layout`, `svg`). It writes tests/draw/roles.json: each case's map
and the SHA-256 and length of its SVG text.
"""

import hashlib
import json
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from napkin.draw import layout as layouts  # noqa: E402
from napkin.draw import style as styles  # noqa: E402
from napkin.draw import svg as svgs  # noqa: E402
from napkin.draw.model_map import picture  # noqa: E402
from tests.draw import models, test_picture, test_style  # noqa: E402

# The scenario line that `models.compiled` gives a text without one.
HEADER = 'scenario "A fixture"\n    horizon 10 h\n\n'
# The model of test_picture.py's `test_a_card_names_its_template_copies_and_role`, as it wrote it.
CARDS = textwrap.dedent(
    """
    Ward:
        role community
        people: people = 0 people
        flow arrive: SOURCE -> this.people
            request = 1 people/h
    wards: Ward from "wards.csv"
    north: Ward
    crew:
        role crew
        x: people = 0 people
    meter:
        y: people = 0 people
    operator:
        role operator
        forecast = categorical(ACT: 0.5, WAIT: 0.5)
        decide = event():
            order: enum[ACT, WAIT] = WAIT
            after 0 h:
                order = operator.forecast.draw()
                switch order:
                    ACT:
                        meter.y += 1 people
                    WAIT:
                        meter.y -= 1 people

    operator.decide.start()
    """
)
# The model of test_picture.py's `test_an_option_that_sets_the_input_of_a_start_shows_on_its_machine`.
PLANS = (
    'scenario "Plans"\n    horizon 10 h\n\noptions "Plan":\n    "Planned A":\n        "A."\n'
    '        plant.plan = A\n    "Planned B":\n        "B."\n        plant.plan = B\n' + test_picture.STATES
)
# The table of test_style.py's `test_a_table_is_named_by_its_card`.
ROWS = '\nCrew:  @counts\n    "A crew."\n    role responder\n\ncrews: Crew from "crews.csv"\n'

# {case: (the model with its roles, its stylesheet or None, its tables, its run)}
CASES = {
    'works': (models.WORKS, None, None, None),
    'works_styled': (models.WORKS, models.WORKS_STYLE, None, None),
    'works_contract': (models.WORKS, test_picture.CONTRACT_STYLE, None, None),
    'works_attack': (models.WORKS, models.WORKS_STYLE, None, 'attack'),
    'cards': (HEADER + CARDS, None, {'wards.csv': 'id\na\nb\nc\n'}, None),
    'states': (HEADER + test_picture.STATES, None, None, None),
    'plans': (PLANS, None, None, None),
    'wards': (test_style.MODEL, None, None, None),
    'wards_styled': (test_style.MODEL, test_style.STYLE, None, None),
    'wards_no_role': (
        test_style.MODEL.replace('west: Ward\n', 'west: Ward\n' + test_style.NO_ROLE),
        None,
        None,
        None,
    ),
    'wards_table': (
        test_style.MODEL.replace('west: Ward\n', 'west: Ward\n' + ROWS),
        None,
        {'crews.csv': 'id\na\nb\n'},
        None,
    ),
    'wards_stocked': (test_style.STOCKED, None, None, None),
    'wards_text': (test_style.TEXT_MODEL, None, None, None),
}


def main():
    # On the code after change 23 the models have no role: what it would draw is no expectation.
    if 'role adversary' not in models.WORKS:
        raise SystemExit(
            'the models of tests/draw have no role: run this on the code before change 23 (c94ab8f)'
        )
    out = {}
    with tempfile.TemporaryDirectory() as root:
        for name, (text, sheet, tables, run) in CASES.items():
            model = models.package(Path(root) / name, text, style=sheet, tables=tables)
            found = styles.of(model)
            doc = picture(model, found, run=run)
            drawn = svgs.svg(doc, layouts.layout(doc, found)).encode()
            out[name] = {
                'map': doc,
                'svg': {'sha256': hashlib.sha256(drawn).hexdigest(), 'bytes': len(drawn)},
            }
    target = ROOT / 'tests' / 'draw' / 'roles.json'
    target.write_text(json.dumps(out, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(f'wrote {target}: {len(out)} cases')


main()
