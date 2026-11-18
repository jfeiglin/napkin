"""A command line of `napkin` run in this process (`napkin.cli.main`), and the packages that the
tests of the commands write: the tank of the spec, and its units."""

from __future__ import annotations

import json
from dataclasses import dataclass

from napkin.cli import main

# The tank of the spec (spec.md, "Flows and algebraic solvers"), with a scenario line.
TANK = """\
scenario "Tank"
    horizon 4 h

tank:
    readonly water: L = 8 in [0, 20]

clinic:
    flow delivery: tank.water -> SINK
        capacity = 5 L/h
        request = 3 L/h
"""
# Litres, and minutes so that a time can be 2 h 40 min.
UNITS = {
    'L': {'dimensions': {'volume': 1}, 'scale': 1, 'description': 'A litre.'},
    'min': {'dimensions': {'time': 1}, 'scale': 1 / 60, 'description': 'A minute.'},
}


@dataclass(frozen=True)
class Done:
    """What a command line gave: its exit code and what it wrote."""

    code: int
    out: str
    err: str

    @property
    def doc(self):
        """The JSON document that it wrote."""
        return json.loads(self.out)


def napkin(capsys, *argv):
    """Run `napkin ARGV` in this process: its exit code (2 for a line that argparse refuses) and its
    output."""
    capsys.readouterr()
    try:
        code = main([str(word) for word in argv])
    except SystemExit as stop:
        code = stop.code
    out, err = capsys.readouterr()
    return Done(code, out, err)


def package(folder, text, units=None):
    """A package in `folder`: its `model.scn` and, when given, its `units.json`."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'model.scn').write_text(text, encoding='utf-8')
    if units is not None:
        (folder / 'units.json').write_text(json.dumps(units), encoding='utf-8')
    return folder
