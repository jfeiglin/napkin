"""A report credits the field selected by a collection and the evidence that selected it."""

from dataclasses import replace

import pytest

from napkin.engine import run
from napkin.engine.report import report
from napkin.model.compile import compile_text
from napkin.program.record import Key

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def readings(text, paths, times, everything):
    model = compile_text(text, UNITS)
    config = model.configuration
    if not everything:
        keys = tuple(Key(owner, (field,)) for owner, field in (p.rsplit('.', 1) for p in paths))
        config = replace(config, request=replace(config.request, everything=False, keys=keys))
    record = run(model.program, config)
    assert record.failure is None
    return report(record, model.program, config, paths, times, model=model.declared).values


def credited(row):
    return {source for part in row.trail if part.exercised for source in part.records}


@pytest.mark.parametrize('everything', [True, False], ids=['full', 'selected'])
def test_sum_of_one_occurrences_field_cites_its_measurement(everything):
    """The one reading of 2 L is both the direct value and the complete sum, live and frozen."""
    text = """scenario "A sample"
    horizon 2 h
w:
    input measured: L = 2 L  @meter
    job = event():
        sample = formula(this.measured)
        after 1 h
    total = formula(sum(this.job.occurrences.sample))

w.job.start()
record meter: source "Meter reading."
"""
    direct, total = readings(text, ['w.job#0.sample', 'w.total'], [1.5, 0.5], everything)
    assert direct.values == total.values == (2, 2)
    assert credited(direct) == {'meter'}
    assert credited(total) == {'meter'}


def table(second, cutoff):
    return f"""scenario "Selected readings"
    horizon 2 h
Cell:
    input eligible: bool = false
    input rank = 0
    input measured: L = 0 L
a: Cell
    eligible = true  @flag_a
    rank = 1  @rank_a
    measured = 2 L  @meter_a
b: Cell
    eligible = {str(second).lower()}  @flag_b
    rank = 2  @rank_b
    measured = 9 L  @meter_b
w:
    input cutoff = {cutoff}  @cutoff_source
    total = formula(sum(Cell.instances.where(eligible).measured))
    later = formula(this.total if t >= 1 h else 0 L)
    picked = formula(Cell.instances.by(rank).at(this.cutoff).measured)
record flag_a: source "Eligibility of a."
record flag_b: source "Eligibility of b."
record rank_a: source "Rank of a."
record rank_b: source "Rank of b."
record meter_a: source "Meter a."
record meter_b: source "Meter b."
record cutoff_source: source "Lookup cutoff."
"""


@pytest.mark.parametrize('everything', [True, False], ids=['full', 'selected'])
@pytest.mark.parametrize('second', [False, True])
def test_filtered_total_cites_eligibility_and_only_the_selected_measurements(everything, second):
    """Changing just b's eligibility adds its 9 L to a's 2 L. Both flags were tested."""
    expected = {'flag_a', 'flag_b', 'meter_a'} | ({'meter_b'} if second else set())
    amount = 11 if second else 2
    for paths, times in [(['w.total', 'w.later'], [0, 2]), (['w.later', 'w.total'], [2, 0])]:
        for row in readings(table(second, 1), paths, times, everything):
            assert row.values == tuple(0 if row.path == 'w.later' and t == 0 else amount for t in times)
            assert credited(row) == expected


@pytest.mark.parametrize('everything', [True, False], ids=['full', 'selected'])
@pytest.mark.parametrize(('cutoff', 'amount', 'meter'), [(1, 2, 'meter_a'), (2, 9, 'meter_b')])
def test_keyed_read_cites_the_cutoff_the_index_and_the_selected_measurement(
    everything, cutoff, amount, meter
):
    """The greatest rank at or below 1 selects 2 L. Raising only the cutoff to 2 selects 9 L."""
    (row,) = readings(table(False, cutoff), ['w.picked'], [2, 0], everything)
    assert row.values == (amount, amount)
    assert credited(row) == {'cutoff_source', 'rank_a', 'rank_b', meter}


@pytest.mark.parametrize('everything', [True, False], ids=['full', 'selected'])
def test_named_filtered_index_credits_only_the_fields_it_consulted(everything):
    """Checking a's rank admits it. b fails the first filter, so its rank and meter go unread.
    Taking the cutoff from the true arm also leaves the other arm's source unread."""
    text = table(False, 2).replace(
        '    picked = formula(Cell.instances.by(rank).at(this.cutoff).measured)',
        '''    input fallback = 1  @unused
    indexed = Cell.instances.where(eligible).where(rank >= 1).by(rank)
    picked = formula(this.indexed.at(this.cutoff if this.cutoff > 0 else this.fallback).measured)
record unused: source "Unused fallback."''',
    )
    (row,) = readings(text, ['w.picked'], [2, 0], everything)
    assert row.values == (2, 2)
    assert credited(row) == {'flag_a', 'flag_b', 'rank_a', 'cutoff_source', 'meter_a'}
