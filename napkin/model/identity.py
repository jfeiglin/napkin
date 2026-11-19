"""The identity of a model: its hash, and the version of the language that the hash covers.

The hash of a model (`model_hash`) names one revision of what the model computes and of how a run
can configure it: its program (`napkin.program.canonical.program_bytes`), the options and the named
runs that set its inputs, the horizon and the numerics of its default run, and the version of the
language. It covers no label: not a text, a title, a menu line, a note or a record, and not the
places of the lines, the comments or the names of the files, the package and its variants. So a
corrected label, a moved line or a renamed package keeps the hash, and a saved edit document stays
valid; a new variant is a model of its own and leaves the hashes of its siblings. The key of a stored
run reads the program and one configuration (`napkin.store.key`), so a label moves neither.
"""

from __future__ import annotations

import hashlib

from ..program.artifact import LANGUAGE_VERSION
from ..program.canonical import configuration_bytes, program_bytes, value_bytes

# `LANGUAGE_VERSION`, which the hash of a model covers, is the program's (`napkin.program.artifact`):
# a model's identity changes with the language, never with the version of the package.

# The record collections of a folder's evidence (`library.py`).
COLLECTIONS = ('sources', 'claims', 'assumptions')


def model_hash(declared, program, base=None):
    """The hash of a declared model, its program and the configuration of its default run (`base`,
    None for a model with no horizon): see the module."""
    # A group is named by its place: its name is a label, and only which options share it counts.
    groups = list(dict.fromkeys(option.group for option in declared.options))
    options = tuple(
        (
            option.name,
            groups.index(option.group),
            tuple(
                (item.member, item.instances, item.name, _constant(item.value)) for item in option.settings
            ),
        )
        for option in declared.options
    )
    runs = tuple((run.name, run.options) for run in declared.runs)
    parts = [LANGUAGE_VERSION.encode(), program_bytes(program), value_bytes((options, runs))]
    if base is not None:
        parts += [configuration_bytes(base), value_bytes(base.request.horizon)]
    digest = hashlib.sha256(b'napkin model\0')
    for part in parts:
        # Each part is length-prefixed, so no two models share their bytes across a boundary.
        digest.update(b'%d:' % len(part))
        digest.update(part)
    return digest.hexdigest()


def _constant(value):
    """A setting's constant as canonical data: its number or yes/no or text and the spelling of its
    type, or the program's distribution."""
    from . import semantic as s
    from .lowering import distribution

    if isinstance(value, s.Distribution):
        return distribution(value)
    return (value.value, str(value.type))
