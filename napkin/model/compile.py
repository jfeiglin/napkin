"""Load a scenario's model, and the compiler functions that the model builder uses.

`load_scenario` builds the model of a model file (`model/model.py`, docs/python-api.md).
The model checks, proves and resolves each structure with `resolve_structure` and
`check_parameters`, and names the code and the schemas that it runs with `implementation_digest`.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from ..expressions import ExpressionError, UnitSystem
from .analysis import values as value_analysis
from .ir import ModelError, diagnostic, thaw
from .load import SCHEMA_BYTES
from .structure import Resolved

# The folder of the package, whose engine, model, typed core and expression evaluator the implementation
# hash names.
PACKAGE = Path(__file__).resolve().parents[1]
_SOURCES = sorted(path for folder in ('core', 'engine', 'model') for path in (PACKAGE / folder).rglob('*.py'))
_SOURCES.append(PACKAGE / 'expressions.py')
# The code and compiler-read schemas are digested once, at import. This names what the process
# loaded even if source files change while a long-lived process is running.
CODE_DIGEST = {
    path.relative_to(PACKAGE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in _SOURCES
}
SCHEMA_DIGEST = {
    f'schema/{name}': hashlib.sha256(content).hexdigest() for name, content in SCHEMA_BYTES.items()
}


def implementation_digest():
    return {**CODE_DIGEST, **SCHEMA_DIGEST}


def implementation_hash():
    """A machine identity of the imported implementation, separate from authored content."""
    canonical = json.dumps(implementation_digest(), sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def load_scenario(path, library=None, *, admission_runs=None):
    """Read, build, check and prove one scenario's model file: its model (`model.model.Model`,
    docs/python-api.md). ``admission_runs`` explicitly limits numerical admission to
    those named runs; None retains full admission, including the profiles that no run names."""
    from .model import build_model

    return build_model(path, library, admission_runs=admission_runs)


def check_parameters(definitions, values, path, errors):
    """The diagnostics of input values against their definitions: a known input, a finite number, a
    bool input's 0 or 1, the code of a named input's value, and a value within the input's range.
    `definitions` are the inputs of a structure as typed parts (`structure.Parameter`)."""
    for name, value in values.items():
        if name not in definitions:
            errors.append(diagnostic('parameter', f'{path}/{name}', 'Unknown parameter'))
            continue
        definition = definitions[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            errors.append(diagnostic('parameter', f'{path}/{name}', 'Parameter requires a finite number'))
            continue
        adjustment = definition.adjust
        # The notes of an input (`metadata`) are plain data, not a typed part.
        metadata = definition.metadata or {}
        if metadata.get('control') == 'binary':
            if value not in (0, 1):
                errors.append(
                    diagnostic(
                        'binary_control', f'{path}/{name}', 'Binary control value must equal zero or one'
                    )
                )
            if adjustment.mode == 'range' and (adjustment.minimum != 0 or adjustment.maximum != 1):
                errors.append(
                    diagnostic(
                        'binary_control',
                        f'{definition.path}/adjust',
                        'Binary control range must equal [0, 1]',
                    )
                )
        choices = metadata.get('values')
        if metadata.get('control') == 'choice' and (
            not isinstance(choices, (list, tuple)) or value not in range(len(choices))
        ):
            errors.append(
                diagnostic(
                    'choice_control',
                    f'{path}/{name}',
                    'A choice is the code of one of its named values, 0 to n - 1',
                )
            )
        if adjustment.mode == 'range':
            lower, upper = adjustment.minimum, adjustment.maximum
            if lower > upper:
                errors.append(diagnostic('bounds', f'{definition.path}/adjust', 'Minimum exceeds maximum'))
            if not lower <= value <= upper:
                errors.append(
                    diagnostic('bounds', f'{path}/{name}', f'Value {value} outside [{lower}, {upper}]')
                )


def resolve_structure(structure, source, library, values, context, *, checked=False, proofs=None):
    """The values of one run in one structure, checked: (what a resolution has of its own, the
    number of each bound of a quantity that is written as an expression).

    `structure` is the typed parts of the structure (`structure.Structure`), which every check of
    the run reads: nothing is written into them, and every resolution of the structure shares them.
    `source` gives the model's `time` and `initiation`. The first result has the keys of a
    resolution in their order:
    `values` (in execution units), `parameter_values`, `time`, `initiation` and what the proofs
    proved (`structure.Resolved`). The second is quantity → `min` / `max` → number.

    `checked` runs the blocking parameter checks first, so a run whose inputs break the scenario's
    own check is rejected with that check rather than with a proof it makes fail. `proofs` is what
    the caller keeps for this structure from one set of values to the next
    (`analysis.values.Proofs`)."""
    units = UnitSystem(library['units'])
    parameters = structure.parameters
    errors = []
    check_parameters(
        parameters,
        {k: p.value for k, p in parameters.items()},
        f'{context}/parameters',
        errors,
    )
    unknown = values.keys() - parameters.keys()
    errors += [
        diagnostic('parameter', f'{context}/set/{name}', 'Unknown parameter') for name in sorted(unknown)
    ]
    if errors:
        raise ModelError(errors)
    own = {}
    try:
        own['values'] = {key: units.normalize(value, parameters[key].unit) for key, value in values.items()}
    except ExpressionError as exc:
        raise ModelError([diagnostic('unit', context, exc)]) from exc
    own['parameter_values'] = dict(values)
    own['time'] = thaw(source['time'])
    own['initiation'] = thaw(source.get('initiation'))
    if checked:
        try:
            failures = value_analysis.input_check_failures(structure, units, own['values'])
            blocked = [d for d in failures if d['severity'] == 'error']
        except ExpressionError:
            blocked = []  # the proofs below locate the failing expression
        if blocked:
            raise ModelError(blocked)
    # What the checks read: the parts of the structure themselves, with the values of this run.
    errors, facts = value_analysis.value_facts(Resolved.over(structure, own), library, proofs=proofs)
    if errors:
        raise ModelError([{**item, 'context': context} for item in errors])
    own.update({key: facts[key] for key in value_analysis.PROVED if key in facts})
    return own, facts['bounds']
