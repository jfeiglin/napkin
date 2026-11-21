"""A cited change to a member's field belongs in the compiled artifact's side table."""
from napkin.engine.report import report
from napkin.engine.timeline import run
from napkin.model.compile import compile_text
from napkin.program.artifact import loads


def test_member_field_citation_survives_in_compiled_artifact():
    source = '''scenario "Meters"
    horizon 1 h
Cell:
    input reading: L = 0 L
north: Cell
    reading = 2 L  @meter_north
south: Cell
    reading = 3 L  @meter_south
total = formula(sum(Cell.instances.reading))
record meter_north: source "Northern meter reading."
record meter_south: source "Southern meter reading."
'''
    units = {'h': {'time': 1}, 'L': {'volume': 1}}
    model = compile_text(source, units)
    record = run(model.program, model.configuration)
    row = report(record, model.program, model.configuration, ['total'], [1], model=model.declared)
    assert row.values[0].values == (5,)
    assert {name for name, _, _ in row.records} == {'meter_north', 'meter_south'}
    revised = compile_text(source.replace('Northern meter reading.', 'A revised source.'), units)
    original, changed = (loads(m.artifact().data()) for m in (model, revised))
    assert original.program == changed.program
    assert original.table != changed.table
