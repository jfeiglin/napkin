"""The files of a package (docs/language.md, §2.12).

A package is a folder whose entry file is its `model.scn`. Its variants are the folders of its
`variants/` folder that hold an entry file of their own: the variant `east` is the file
`variants/east/model.scn`. The other `.scn` files of a package are its modules. These functions read
no file. Where a catalogue keeps its packages, and what a checkout or an installed copy holds, are the
concerns of their own tools (`tools/catalogue.py`), never of the language.
"""

from pathlib import Path

# The entry file of a package or of a variant, and the folder of the variants of a package.
ENTRY = 'model.scn'
VARIANTS = 'variants'


def entry(folder):
    """The entry file of the package or the variant in `folder`, whether or not the file is there."""
    return Path(folder) / ENTRY


def variants(package):
    """{name: entry file} of the variants of the package in the folder `package`, sorted by name: each
    folder of its `variants/` that holds an entry file. It reads no file."""
    return {
        path.parent.name: path
        for path in sorted((Path(package) / VARIANTS).glob(f'*/{ENTRY}'))
        if path.is_file()
    }


def names_of(path):
    """(the scenario, the variant or None) that a model file is, by its folders: a package's entry file
    is named by the folder of the package, and a variant's entry file,
    `<package>/variants/<name>/model.scn`, by the package and its variant. Any other file is named by
    its stem. It reads no file."""
    path = Path(path)
    if path.name != ENTRY:
        return path.stem, None
    if path.parent.parent.name == VARIANTS and path.parent.parent.parent.name:
        return path.parent.parent.parent.name, path.parent.name
    return path.parent.name or path.stem, None


def package_of(path):
    """The folder of the package that holds `path`, a file or a folder: the nearest folder at or above
    `path` that holds an entry file, or the grandparent of that folder when it is a variant (a folder of
    `variants/`). None when no folder at or above `path` holds an entry file."""
    path = Path(path)
    for folder in (path, *path.parents):
        if entry(folder).is_file():
            return folder.parent.parent if folder.parent.name == VARIANTS else folder
    return None
