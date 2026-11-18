"""Split `napkin/engine/timeline/run.py` into modules by pure moves (step B0-6 of PLAN.md).

    python split_run.py PACKAGE_ROOT [--check BASE_ROOT] [--dry]

`PACKAGE_ROOT` is a folder that holds `napkin/` (a copy of the checkout, or the checkout itself).
The script rewrites `napkin/engine/timeline/run.py` there and writes the new modules beside it.

What it does, and nothing else:

- Each top-level function, class and constant of `run.py`, and each method of `Run`, is cut as text
  (with the blank lines and comments above it) and pasted into the module that `LAYOUT` names.
- The methods of `Run` that go to a module become the body of one mixin class there. `Run` in
  `run.py` inherits from each mixin, so every `self.x` still finds `x`. No method body changes.
- Each new module gets the import block of `run.py`, and `from .state import ...` for the helpers
  that it reads. `ruff check --select F401 --fix` then removes the imports that a module does not
  use (ruff must be on the path, or in the venv of the checkout).
- `run.py` imports back the names that other modules and tests import from it.

A method that `LAYOUT` names and `run.py` no longer has (the derivative code, after step B0-5) is
skipped. A method that `run.py` has and `LAYOUT` does not name stops the script, with its name.

`--check BASE_ROOT` compares the split package with the unsplit one in `BASE_ROOT`: every function
has the same bytecode, constants and names as before, and `Run` has the same attributes. It needs
no test of the repository.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

RUN = 'napkin/engine/timeline/run.py'

# module -> (mixin class or None, its text, top-level names, methods of Run)
LAYOUT = {
    'state': (
        'State',
        'The columns of a run and its past: how a part reads a name, now or at an earlier time.',
        [
            'ROOT_TOLERANCE', 'CHANCE_TOLERANCE', 'TRIGGER', 'FIRE', 'RULE', 'BOUND', 'ROOT', 'LIMIT',
            'FLOOR', 'END', 'ONE', 'NEGATIVE', 'POSITIVE', 'SEEN',
            '_one', '_spread', '_pairwise', 'Trial', 'Env', 'Seen', 'Unknown', 'Past',
        ],
        [
            'index', 'read', 'read_past', 'past_states', 'segment', 'numeric', 'column', 'value',
            'static', 'sizes', 'rule_free_name', 'rule_name', 'place', 'flat_entity',
        ],
    ),
    'tangents': (
        'Tangents',
        'The derivative of every value by each direction. Step B0-5 deletes all of it.',
        [],
        [
            'tangent', 'note', 'about', 'done', 'ties', 'name_tangent', 'slope', 'rate_tangent',
            'block_ties', 'jumps', 'own_tangent', 'chance_slopes', 'outcome_noted', 'step_noted',
        ],
    ),
    'lists': (
        'Lists',
        'The reductions over the instances of a family, and how one member is brought up to date.',
        [],
        ['aggregate', 'combined', 'reduced', 'update_term'],
    ),
    'sharing': (
        'Sharing',
        'What a flow of the fast tier delivers: groups with a limit, flows that move by one fraction, '
        'and a source that rests on its bound.',
        [],
        [
            'rate_of', 'see_flows', 'flows_at_end', 'negative_flow', 'delivered', 'alone', 'fraction',
            'supply', 'rationed',
        ],
    ),
    'segments': (
        'Segments',
        'What a quantity is between two moments: a line, a numeric block or a closed form, and how '
        'each starts again.',
        ['_span', 'Solution'],
        [
            'field', 'matrices', 'flows_from', 'asked_alone', 'block_program', 'block_values',
            'group_terms', 'decide', 'within_bounds', 'restart_line', '_restart_line', 'rest', 'cut',
            'segment_end', 'restart_block',
        ],
    ),
    'readers': (
        'Readers',
        'What a step wrote: the parts that read it, by any path, and how they are brought up to date.',
        [],
        ['targets', 'merge', 'closure', 'apply'],
    ),
    'checks': (
        'Checks',
        'The checks of the inputs and of the state, and the partitions.',
        [],
        [
            'check_readers', 'holds_at_start', 'check', 'partition', 'check_all', 'input_failures',
            'admit',
        ],
    ),
    'rules': (
        'Rules',
        'The memory of each rule, the reading of a rule and the time at which it is read again.',
        ['RuleState'],
        [
            'ends', 'crossing_due', 'mark', 'holds', 'window', 'spent', 'later', 'read_rule', 'watch',
            'can_trigger',
        ],
    ),
    'steps': (
        'Steps',
        'One step of a rule: its trigger, its outcome and its firing.',
        ['shares'],
        ['extras', 'count_step', 'emitted', 'trigger', '_trigger', 'chosen', 'taken', 'fire', '_fire'],
    ),
    'choices': (
        'Choices',
        'A played run: who picks, the picks, the decision that waits and the pause.',
        ['View', 'Pause'],
        ['controller', 'controlled', 'pick', 'happened', 'ask', 'next_settled'],
    ),
    'trace': (
        'Trace',
        'What a run keeps for its readers: the entries of the trace, the snapshots and the result.',
        ['_basis_ref', 'Result'],
        ['entry', 'entry_at', 'state_now', 'store_now', 'snapshot', 'result'],
    ),
}
# What stays in run.py: the class, its construction, its start and its loop.
STAY = ['__init__', 'start', 'settle', 'run', 'played', 'stale']
# The names that other modules and tests import from run.py today.
BACK = ['Past', 'Unknown', '_one', 'shares', 'Result']


def chunks(lines, nodes, first):
    """{name: text} of each node of a body, with the lines between it and the node before it."""
    found, at = {}, first
    for node in nodes:
        end = node.end_lineno
        names = []
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names += [e.id for e in (target.elts if isinstance(target, ast.Tuple) else [target])]
        text = ''.join(lines[at:end])
        if names:
            found[tuple(names)] = text
        else:
            found[('', at)] = text
        at = end
    return found, at


def names_read(text):
    return {node.id for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Name)}


def split(root, dry=False):
    path = Path(root) / RUN
    source = path.read_text(encoding='utf-8')
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)
    body = tree.body
    # The docstring, the imports, then the rest.
    k = 0
    while k < len(body) and (
        isinstance(body[k], (ast.Import, ast.ImportFrom))
        or (isinstance(body[k], ast.Expr) and isinstance(body[k].value, ast.Constant))
    ):
        k += 1
    head_end = body[k - 1].end_lineno
    docstring = ''.join(lines[: body[0].end_lineno])
    imports = ''.join(lines[body[0].end_lineno : head_end])
    tops, _ = chunks(lines, body[k:], head_end)
    run = next(node for node in body if isinstance(node, ast.ClassDef) and node.name == 'Run')
    methods, _ = chunks(lines, run.body, run.lineno)
    method_names = [key[0] for key in methods]
    top_of = {name: key for key in tops for name in key if isinstance(name, str) and name}

    owner = {}
    for module, (_, _, top_names, names) in LAYOUT.items():
        for name in top_names:
            owner[name] = module
    planned = {name for _, _, _, names in LAYOUT.values() for name in names} | set(STAY)
    unknown = [name for name in method_names if name not in planned]
    if unknown:
        raise SystemExit(f'run.py has methods that LAYOUT does not name: {unknown}')
    unowned = [name for name in top_of if name not in owner and name != 'Run']
    if unowned:
        raise SystemExit(f'run.py has top-level names that LAYOUT does not name: {unowned}')

    written, mixins = {}, []
    for module, (mixin, text, top_names, names) in LAYOUT.items():
        keys = list(dict.fromkeys(top_of[name] for name in top_names if name in top_of))
        # In the order of run.py.
        keys.sort(key=lambda key: list(tops).index(key))
        own_methods = [name for name in method_names if name in names]
        if not keys and not own_methods:
            continue
        parts = ''.join(tops[key] for key in keys)
        body_text = ''.join(methods[(name,)] for name in own_methods)
        read = names_read(parts + '\nclass _:\n' + body_text if body_text else parts)
        needs = {}
        for name in sorted(read):
            other = owner.get(name)
            if other and other != module and name in top_of:
                needs.setdefault(other, []).append(name)
        lines_out = [f'"""{text}\n\nMoved from `run.py`, with no change (step B0-6). ']
        if own_methods:
            lines_out.append(f'`{mixin}` is a part of `run.Run`: its methods read the\nrun as `self`.')
        lines_out.append('"""\n')
        out = ''.join(lines_out) + imports
        for other, wanted in needs.items():
            out += f'from .{other} import {", ".join(wanted)}\n'
        out += parts
        if own_methods:
            out += f'\n\nclass {mixin}:\n    """See the module."""\n' + body_text
            mixins.append((module, mixin))
        written[module] = out

    stay = ''.join(methods[(name,)] for name in method_names if name in STAY)
    header = lines[run.lineno - 1]
    assert header.startswith('class Run'), header
    bases = ', '.join(mixin for _, mixin in mixins)
    read = names_read('class _:\n' + stay)
    out = docstring + imports
    for module, (mixin, _, top_names, _) in LAYOUT.items():
        if module not in written:
            continue
        wanted = [name for name in top_names if name in top_of and (name in read or name in BACK)]
        if any(m == module for m, _ in mixins):
            wanted.append(mixin)
        if wanted:
            noqa = '  # noqa: F401' if any(name in BACK for name in wanted) else ''
            out += f'from .{module} import {", ".join(wanted)}{noqa}\n'
    out += f'\n\nclass Run({bases}):\n' + stay
    written['run'] = out
    if dry:
        for module, text in written.items():
            print(f'{module}.py: {len(text.splitlines())} lines')
        return written
    folder = path.parent
    for module, text in written.items():
        (folder / f'{module}.py').write_text(text, encoding='utf-8')
    files = [str(folder / f'{module}.py') for module in written]
    ruff = Path(sys.executable).with_name('ruff')
    command = [str(ruff) if ruff.exists() else 'ruff', 'check', '--isolated']
    subprocess.run([*command, '--select', 'F401', '--fix', '--quiet', *files], check=False)
    subprocess.run([*command, '--select', 'I001', '--fix', '--quiet', *files], check=False)
    wrong = subprocess.run([*command, '--select', 'F', '--quiet', *files], check=False)
    for module in written:
        print(f'{module}.py: {len((folder / f"{module}.py").read_text().splitlines())} lines')
    if wrong.returncode:
        raise SystemExit('ruff finds a name that a module does not have: see above')
    return written


def functions(module):
    """{qualified name: code} of each function of a module, and of each method of its classes."""
    import types

    found = {}

    def visit(prefix, owner):
        for name, value in vars(owner).items():
            if isinstance(value, (staticmethod, classmethod)):
                value = value.__func__
            if isinstance(value, property):
                value = value.fget
            if isinstance(value, types.FunctionType) and value.__module__ == module.__name__:
                found[prefix + name] = value.__code__
            elif isinstance(value, type) and value.__module__ == module.__name__ and owner is module:
                visit(f'{name}.', value)

    visit('', module)
    return found


def same_code(a, b):
    import types

    if a.co_code != b.co_code or a.co_names != b.co_names or a.co_varnames != b.co_varnames:
        return False
    if len(a.co_consts) != len(b.co_consts):
        return False
    for x, y in zip(a.co_consts, b.co_consts):
        if isinstance(x, types.CodeType) and isinstance(y, types.CodeType):
            if not same_code(x, y):
                return False
        elif isinstance(x, types.CodeType) or isinstance(y, types.CodeType) or x != y:
            return False
    return True


CHECK = r"""
import importlib, json, sys
sys.path.insert(0, {root!r})
sys.path.insert(0, {here!r})
import split_run
names = ['run'] + [m for m in split_run.LAYOUT]
found = {{}}
for name in names:
    try:
        module = importlib.import_module('napkin.engine.timeline.' + name)
    except ModuleNotFoundError:
        continue
    for key, code in split_run.functions(module).items():
        # A method of a mixin is a method of Run.
        owner, _, rest = key.partition('.')
        mixins = {{mixin for mixin, *_ in split_run.LAYOUT.values()}}
        key = 'Run.' + rest if owner in mixins else key
        assert key not in found, key
        found[key] = code
run = importlib.import_module('napkin.engine.timeline.run')
attributes = sorted(name for name in dir(run.Run) if not name.startswith('__'))
import marshal, base64
print(json.dumps({{'attributes': attributes,
                  'code': {{key: base64.b64encode(marshal.dumps(code)).decode() for key, code in found.items()}}}}))
"""


def check(root, base):
    """Compare the functions of the split package in `root` with those of `base`."""
    import base64
    import json
    import marshal

    here = str(Path(__file__).resolve().parent)
    read = {}
    for where in (root, base):
        made = subprocess.run(
            [sys.executable, '-c', CHECK.format(root=str(Path(where).resolve()), here=here)],
            capture_output=True,
            text=True,
            check=False,
        )
        if made.returncode:
            raise SystemExit(f'{where}: the package does not import:\n{made.stderr}')
        read[where] = json.loads(made.stdout)
    new, old = read[root], read[base]
    if new['attributes'] != old['attributes']:
        raise SystemExit(
            'Run has other attributes: '
            f'{sorted(set(new["attributes"]) ^ set(old["attributes"]))}'
        )
    missing = sorted(set(old['code']) ^ set(new['code']))
    if missing:
        raise SystemExit(f'functions that only one side has: {missing}')
    differ = [
        key
        for key in old['code']
        if not same_code(
            marshal.loads(base64.b64decode(old['code'][key])),
            marshal.loads(base64.b64decode(new['code'][key])),
        )
    ]
    if differ:
        raise SystemExit(f'functions whose code changed: {differ}')
    print(f'{len(old["code"])} functions have the same code; Run has the same {len(old["attributes"])} attributes')


if __name__ == '__main__':
    arguments = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not arguments:
        raise SystemExit(__doc__)
    if '--check' in sys.argv:
        check(arguments[0], arguments[1])
    else:
        split(arguments[0], dry='--dry' in sys.argv)
