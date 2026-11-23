"""What the pages read from a model file (spec, "Model text, status cases and evidence"): a name in
words, and the first text under each declaration, which supplies the label of a field, the
description of an entity, the card of an event and of a case of a switch, the menu line of an option,
the message of a check and the name of a named run. A member's value is labelled by its template's
text, as a report gives it. The publisher, which makes the pages from these, is ported in stage M with
`tests/publish/` (docs/design/decisions.md, change 13); the outcome cards, a run's comparison (`versus`, D9) and the
texts that fill braces went with the old language. Who plays each part is no line of a model (docs/design/decisions.md,
change 23): it is the wrapper's (`roles.toml`) and the stylesheet's `[role]`; the catalogue's are
checked in `tests/evidence/test_catalogue.py`, which waits for M.
"""

from __future__ import annotations

import textwrap

import pytest

from napkin.draw.text import in_words
from napkin.engine.report import report
from napkin.engine.timeline import run
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from tests.program.examples import UNITS

TEXTS = """\
scenario "Texts"
    horizon 4 h

options "Pace":
    "Slow":
        "Crews work slowly."
    "Fast":
        "Crews work fast."

runs:
    slow = "Slow"
        "A slow repair"
    fast = "Fast"

crew:
    "The crew of the works."
    state: enum[WAITING, WORKING, DONE] = WAITING
        "Crew work state"
    repairs = 0
        "Repairs done"
    repair = event():
        "The crew repairs the pump."
        when t >= 1 h:
            this.repair.start()
        after 1 h:
            this.repairs += 1
            switch this.state:
                WAITING:
                    "The crew starts the repair."
                    this.state = WORKING
                WORKING:
                    "The crew finishes the repair."
                    this.state = DONE
    assert this.repairs >= 0
        "Repairs are never negative"

Pump:
    "A pump of the works."
    wear = 0
        "Wear of the pump"

north: Pump

south: Pump
"""


def compiled(text=TEXTS):
    return compile_text(textwrap.dedent(text), UNITS)


@pytest.mark.parametrize(
    ('name', 'words'),
    [
        ('RepairCrews', 'Repair crews'),
        ('AIAgent', 'AI agent'),
        ('SCADAGateway', 'SCADA gateway'),
        ('TerminalManagementSystem', 'Terminal management system'),
        ('first_batch', 'First batch'),
        ('stroke_patients', 'Stroke patients'),
        ('near', 'Near'),
    ],
)
def test_a_name_reads_in_words_and_an_acronym_keeps_its_capitals(name, words):
    assert in_words(name) == words


def test_the_first_text_under_each_declaration_is_what_the_pages_read():
    declared = compiled().declared
    texts = {
        path: declared.part(path).text
        for path in (
            'crew',
            'crew.state',
            'crew.repairs',
            'crew.repair',
            'crew.repair.step[0].do[1].WAITING',
            'crew.repair.step[0].do[1].WORKING',
            'crew.assert[0]',
            'Pump',
            'Pump.wear',
        )
    }
    assert texts == {
        'crew': 'The crew of the works.',
        'crew.state': 'Crew work state',
        'crew.repairs': 'Repairs done',
        'crew.repair': 'The crew repairs the pump.',
        'crew.repair.step[0].do[1].WAITING': 'The crew starts the repair.',
        'crew.repair.step[0].do[1].WORKING': 'The crew finishes the repair.',
        'crew.assert[0]': 'Repairs are never negative',
        'Pump': 'A pump of the works.',
        'Pump.wear': 'Wear of the pump',
    }
    assert [(option.name, option.text) for option in declared.options] == [
        ('Slow', 'Crews work slowly.'),
        ('Fast', 'Crews work fast.'),
    ]
    # A named run is named by its own text, or, without one, by its options.
    assert [(item.name, item.text, item.options) for item in declared.runs] == [
        ('slow', 'A slow repair', ('Slow',)),
        ('fast', None, ('Fast',)),
    ]


def test_a_members_value_is_labelled_by_its_templates_text_whatever_the_member():
    model = compiled()
    record = run(model.program, model.configuration)
    found = report(
        record, model.program, model.configuration, ['north.wear', 'south.wear'], [4], model=model.declared
    )
    assert [(value.path, value.label) for value in found.values] == [
        ('north.wear', 'Wear of the pump'),
        ('south.wear', 'Wear of the pump'),
    ]


@pytest.mark.parametrize(
    ('old', 'new'),
    [
        ('    "The crew of the works."\n', '    "The crew of the works."\n    "The crew."\n'),
        ('        "Repairs done"\n', '        "Repairs done"\n        "Done repairs"\n'),
    ],
    ids=['entity', 'field'],
)
def test_a_line_has_one_text_under_it(old, new):
    text = TEXTS.replace(old, new)
    with pytest.raises(LanguageError) as raised:
        compiled(text)
    (number,) = [k for k, row in enumerate(text.split('\n'), 1) if row.strip() == new.split('\n')[1].strip()]
    assert [(item.code, item.line) for item in raised.value.problems] == [('layout', number)]
