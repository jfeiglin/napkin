"""The schemas that the compiler reads: the library, a folder's units, the edit document and the
report. They are files of the package, so a checkout and an installed wheel read the same bytes."""

from pathlib import Path

# The folder of the schemas: `<name>.schema.json` for each name.
FOLDER = Path(__file__).resolve().parent


def path(name):
    """The file of the schema `name` (`library`, `scenario-units`, `edits` or `report`)."""
    return FOLDER / f'{name}.schema.json'
