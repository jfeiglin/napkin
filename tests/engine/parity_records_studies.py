"""Independent builder forms for the bounded study and single-pass report examples."""

from functools import partial

from napkin.program import build as b
from tests.engine import path_selection_cases as selection
from tests.engine import study_request_cases as study
from tests.engine.parity_records import pair
from tests.engine.program_parity import check_pairs

UNITS = {'h': {'time': 1}}


def study_program(seed):
    target, other = ('blue', 'red') if seed % 2 else ('red', 'blue')
    opening, change = 7 + seed % 11, 1 + seed % 5
    threshold = (0.5, 0.55, 0.6)[seed % 3]
    make = b.Builder(UNITS)
    yard = make.entity(
        'yard',
        b.input_('roll', '', b.draw(b.uniform(0, 1))),
        b.value(target, '', opening),
        b.value(other, '', 3),
        b.event(
            'update',
            b.after(
                b.q(1, 'h'),
                b.assign(
                    getattr(b.this, target), b.ifelse(b.this.roll > threshold, opening + change, opening)
                ),
            ),
        ),
    )
    make.setup(b.start(yard.update))
    return make.finish()


def check_parity_study(seed):
    source, _ = study.study_case(seed, 2, 'selected', 1)
    check_pairs(seed, [pair('counter', source, UNITS, partial(study_program, seed))])


def selected_program(seed):
    make = b.Builder(UNITS)
    make.root(b.value('first', '', 7 + seed % 29), b.value('second', '', 3 - seed % 13))
    return make.finish()


def check_parity_selection(seed):
    source, _ = selection.selection_case(seed)
    check_pairs(seed, [pair('selected-counters', source, UNITS, partial(selected_program, seed))])
