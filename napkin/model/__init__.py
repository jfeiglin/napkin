"""The scenario language: read a model file and build its model (docs/language.md, docs/python-api.md).

The front end (`language/`) reads a file into its semantic model (`semantic`), `lower` writes the engine's
flat structures from it, `runs` gives the values of its runs under an edit document, and `model`
builds, checks and proves the model that the engine runs.
"""

from .compile import load_scenario
from .ir import ModelError
from .library import load_library
from .load import SourceError, load_json
from .model import Model

__all__ = [
    'Model',
    'ModelError',
    'SourceError',
    'load_json',
    'load_library',
    'load_scenario',
]
