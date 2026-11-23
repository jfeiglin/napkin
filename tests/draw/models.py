"""The models of the drawing tests: small synthetic texts in the language of the rewrite, no catalogue.

`compiled(text, tables)` compiles a text with the units of the tests (`UNITS`); `package(folder, main,
...)` writes a package (its main file, modules, a stylesheet and a library) and loads it, so that a
stylesheet is found beside it and the references read its library. `WORKS` is the water works: a
model with every kind of card, part and relation that the picture draws, whose expected pictures the
tests work out by hand from its text. Who plays each of its parts is its stylesheet's (`WORKS_ROLES`,
docs/design/decisions.md, change 23): a model has no role.
"""

from __future__ import annotations

import hashlib
import json
import textwrap
from pathlib import Path

from napkin.model.compile import compile_text, load_scenario
from tests.program.examples import UNITS as PROGRAM_UNITS
from tests.units import PRELUDE
from tests.units import library as test_library

UNITS = {**PROGRAM_UNITS, 'people': {'people': 1}, 'kg': ({'mass': 1}, 1000), 'm3': {'volume': 1}}

# The water works. The attacker can break into the controls only when the option "Attacker AI" sets
# its input `ai`, so the runs `base` and `attack` draw different events of the attacker.
WORKS = """\
scenario "A water works and its town, a synthetic fixture for tests only"
    horizon 48 h
    resolution 1 h

options "Attacker":
    "No AI":
        "The attacker works by hand."
    "Attacker AI":
        "The attacker uses an AI."
        attacker.ai = true  @fixture

runs:
    base = "No AI"
    attack = "Attacker AI"
        "An attack with an AI"

attacker:
    "The attacker."
    title "The attacker"
    input ai: bool = false  @fixture
        "Whether the attacker has an AI"
    input hold_time: h = 2 h in [1 h, 12 h]  @fixture
        "Time that the attacker holds access"
    access: enum[NONE, GAINED, KEPT, LOST] = NONE
        "Access to the plant"
    break_in = event():
        "The attacker breaks in to the controls of the plant."
        when this.ai and t >= 2 h:
            this.break_in.start()
            reset when false
        after 0 h:
            this.access = GAINED
    hold = event():
        when this.access == GAINED and since(this.break_in) >= this.hold_time:
            this.hold.start()
            reset when false
        after 0 h:
            this.access = KEPT
    take_over = event():
        "The attacker takes over the controls."
        when this.access == KEPT and plant.mode == NORMAL:
            this.take_over.start()
            reset when false
        after 0 h:
            plant.mode = MANUAL

plant:
    "The water treatment plant of the town."
    title "The water treatment plant"
    input capacity: L/h = 10 L/h in [0 L/h, 50 L/h]  @fixture
        "Treatment capacity"
    mode: enum[NORMAL, MANUAL, DOWN] = NORMAL
        "Mode of the controls"
    raw: L = 50 L in [0 L, 100 L]
        "Raw water"
    treated: L = 0 L in [0 L,]
        outflow.capacity = 8 L/h
        outflow.allocation = priority(town.supply, hospital.supply)
    treated_total: L = 0 L in [0 L,]
        "Water treated"
    pace = formula(this.capacity if this.mode == NORMAL else this.capacity / 2)
        "Pace of the treatment"
    flow intake: SOURCE -> this.raw
        "Intake"
        request = 6 L/h
    flow treat: this.raw -> this.treated
        "Treatment"
        request = this.pace
    flow count: SOURCE -> this.treated_total
        request = this.pace
    alarms = 0
        "Alarms raised"
    alarm = event():
        when this.mode == MANUAL:
            this.alarm.start()
            reset when false
        after 0 h:
            this.alarms += 1
            crews.repair.start()

town:
    "The town."
    stored: L = 0 L in [0 L,]
        "Water in the town"
    flow supply: plant.treated -> this.stored
        "Supply"
        request = 5 L/h

hospital:
    "The hospital."
    stored: L = 0 L in [0 L,]
    flow supply: plant.treated -> this.stored
        request = 5 L/h

crews:
    "The crews."
    repairs = 0
    repair = event():
        after 1 h:
            this.repairs += 1
            if plant.mode == MANUAL:
                plant.mode = NORMAL

Zone:
    "A zone of the town."
    input need: L = 1 L in [0 L,]  @fixture
        "Need of the zone"
    level: L = 0 L in [0 L,]
        "Water in the zone"
    flow fill: town.stored -> this.level
        request = this.need / (1 h)

north: Zone
    need = 2 L  @fixture

south: Zone

record fixture: assumption "A synthetic test fixture."
"""

# Who plays each part of the water works: the stylesheet's `[role]`, which gives each of these things
# the icon of its role unless `[icon]` gives it one.
WORKS_ROLES = (
    '[role]\nadversary = ["attacker"]\noperator = ["plant"]\ncommunity = ["town", "hospital"]\n'
    'responder = ["crews"]\nenvironment = ["Zone"]\n'
)
# A stylesheet of the water works: its roles; it hides the hospital and gives the plant an icon of its
# own.
WORKS_STYLE = WORKS_ROLES + '\n[layout]\nhide = ["hospital"]\n\n[icon]\nfactory = ["plant"]\n'
# The scenario line that `compiled` gives a text without one.
HEADER = 'scenario "A fixture"\n    horizon 10 h\n\n'


def compiled(text, tables=None):
    """The compiled model of a text, with the units of the tests; a text without a scenario line
    gets one with a horizon of 10 h."""
    text = textwrap.dedent(text)
    if not text.lstrip().startswith('scenario'):
        text = HEADER + text
    return compile_text(text, UNITS, tables=tables)


def package(folder, main, *, modules=None, style=None, library=None, tables=None):
    """Writes a package in `folder` and gives its compiled model: its main file, its modules by name,
    its tables by file name and `style.toml`. Its units are those of the tests that the prelude does
    not have: in `units.json`, or with `library` (`{collection: [record, …]}`, conventions too) in the
    shared library `lib/vocabulary.json`, which a `library "lib"` line of its scenario names."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    main = textwrap.dedent(main)
    units = {}
    for name, spec in UNITS.items():
        if name not in PRELUDE:
            dimensions, scale = spec if isinstance(spec, tuple) else (spec, 1)
            units[name] = {'dimensions': dict(dimensions), 'scale': scale}
    if library is None:
        (folder / 'units.json').write_text(json.dumps(units), encoding='utf-8')
    else:
        head, _, rest = main.partition('\n')
        main = f'{head}\n    library "lib"\n{rest}'
        (folder / 'lib').mkdir(exist_ok=True)
        vocabulary = {**test_library(), 'units': units, **library}
        (folder / 'lib' / 'vocabulary.json').write_text(json.dumps(vocabulary), encoding='utf-8')
    (folder / 'model.scn').write_text(main, encoding='utf-8')
    for name, text in (modules or {}).items():
        (folder / f'{name}.scn').write_text(textwrap.dedent(text), encoding='utf-8')
    for name, text in (tables or {}).items():
        (folder / name).write_text(text, encoding='utf-8')
    if style is not None:
        (folder / 'style.toml').write_text(style, encoding='utf-8')
    return load_scenario(folder / 'model.scn')


def works():
    """The compiled water works."""
    return compiled(WORKS)


def fixture_claim(identifier, **fields):
    """A claim of the library, with the verification record that pins the digest of its content."""
    claim = {
        'id': identifier,
        'source': 'src',
        'locator': 'p. 1',
        'shows': f'{identifier} fixture fact.',
        'limits': 'Synthetic.',
        **fields,
    }
    digest = hashlib.sha256(
        json.dumps(claim, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    ).hexdigest()
    verification = {
        'status': 'unverified',
        'date': '2026-09-18',
        'method': 'access_attempt',
        'notes': 'Synthetic.',
        'checked_fields': [],
        'content_sha256': digest,
    }
    return {**claim, 'verification': verification}
