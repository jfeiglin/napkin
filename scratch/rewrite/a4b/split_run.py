"""Split `napkin/engine/timeline/run.py` into modules by pure moves (step B0-6 of PLAN.md).

    python split_run.py ROOT                      # every module of LAYOUT, in one pass
    python split_run.py ROOT --only state         # one move (or several: --only lists,sharing)
    python split_run.py ROOT --dry                # say what would move, write nothing
    python split_run.py ROOT --check BASE         # prove that the split changed no function

`ROOT` is a folder that holds `napkin/` (the checkout, or a copy of it). The script rewrites
`napkin/engine/timeline/run.py` there and writes the new modules beside it. `LAYOUT.md` gives the
order of the moves and the tests that guard each.

What one move does, and nothing else:

- Each top-level function, class and constant of `run.py` that `LAYOUT` gives to the module, and
  each such method of `Run`, is cut as text, with the blank lines and the comments above it, and
  pasted into the module. The methods become the body of one mixin class there. `Run` in `run.py`
  inherits from each mixin, so every `self.x` still finds `x`. No body changes.
- The module gets the imports of `run.py`, and `from .state import ...` for the helpers that it
  reads. ruff then removes the imports that a file does not use, sorts them, and formats the new
  lines (it must be on the path, or beside the Python that runs this script).
- `run.py` imports the mixin, and imports back, under their own names, the names that other
  modules and tests import from it (`BACK`).

A method that `LAYOUT` names and `run.py` no longer has is skipped: the derivative code after step
B0-5, or a module that an earlier call moved. A method or a top-level name that `run.py` has and
`LAYOUT` does not name stops the script, with the name. `state` is the first move: the other
modules import its helpers.

`--check BASE` compares the package in `ROOT` with the unsplit one in `BASE`: `Run` has the same
attributes, and each function has the same bytecode, constants and names as before. It imports
both packages in fresh processes and runs no test of the repository.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

FOLDER = 'napkin/engine/timeline'

# module -> (mixin class, the text of the module, top-level names, methods of Run)
LAYOUT = {
    'state': (
        'State',
        'The columns of a run and its past: how a part reads a name, now or at an earlier time.',
        [
            *('ROOT_TOLERANCE', 'CHANCE_TOLERANCE', 'TRIGGER', 'FIRE'),
            *('RULE', 'BOUND', 'ROOT', 'LIMIT', 'FLOOR', 'END'),
            *('ONE', 'NEGATIVE', 'POSITIVE', 'SEEN'),
            *('_one', '_spread', '_pairwise', 'Trial', 'Env', 'Seen', 'Unknown', 'Past'),
        ],
        [
            *('index', 'read', 'read_past', 'past_states', 'segment', 'numeric', 'column', 'value'),
            *('static', 'sizes', 'rule_free_name', 'rule_name', 'place', 'flat_entity'),
        ],
    ),
    'tangents': (
        'Tangents',
        'The derivative of every value by each direction. Step B0-5 deletes all of it.',
        [],
        [
            *('tangent', 'note', 'about', 'done', 'ties', 'name_tangent', 'slope', 'rate_tangent'),
            *('block_ties', 'jumps', 'own_tangent', 'chance_slopes', 'outcome_noted', 'step_noted'),
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
        'What a flow of the fast tier delivers: a group with a limit, flows that move by one\n'
        'fraction, and a source that rests on its bound.',
        [],
        [
            *('rate_of', 'see_flows', 'flows_at_end', 'negative_flow', 'delivered', 'alone'),
            *('fraction', 'supply', 'rationed'),
        ],
    ),
    'segments': (
        'Segments',
        'What a quantity is between two moments: a line, a numeric block or a closed form, and how\n'
        'each starts again.',
        ['_span', 'Solution'],
        [
            *('field', 'matrices', 'flows_from', 'asked_alone', 'block_program', 'block_values'),
            *('group_terms', 'decide', 'within_bounds', 'restart_line', '_restart_line', 'rest'),
            *('cut', 'segment_end', 'restart_block'),
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
            *('check_readers', 'holds_at_start', 'check', 'partition', 'check_all'),
            *('input_failures', 'admit'),
        ],
    ),
    'rules': (
        'Rules',
        'The memory of each rule, the reading of a rule, and the time at which it is read again.',
        ['RuleState'],
        [
            *('ends', 'crossing_due', 'mark', 'holds', 'window', 'spent', 'later', 'read_rule'),
            *('watch', 'can_trigger'),
        ],
    ),
    'steps': (
        'Steps',
        'One step of a rule: its trigger, the outcome that it takes, and its firing.',
        ['shares'],
        ['extras', 'count_step', 'emitted', 'trigger', '_trigger', 'chosen', 'taken', 'fire', '_fire'],
    ),
    'choices': (
        'Choices',
        'A played run: who picks, the picks, the decision that waits, and the pause.',
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
# The names that other modules and tests import from run.py today, and who reads each.
BACK = {
    'Past': 'timeline/reports.py',
    'Unknown': 'timeline/reports.py',
    '_one': 'timeline/reports.py',
    'shares': 'tests/engine/test_timeline_outcomes.py',
    'Result': 'timeline/__init__.py',
}


def chunks(lines, nodes, first):
    """[(names, text)] of each node of a body. The text has the lines above the node, from the end
    of the node before it (or from line `first`, counted from 0)."""
    found, at = [], first
    for node in nodes:
        names = ()
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names = (node.name,)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names += tuple(e.id for e in (target.elts if isinstance(target, ast.Tuple) else [target]))
        found.append((names, ''.join(lines[at : node.end_lineno])))
        at = node.end_lineno
    return found


def names_read(text):
    return {node.id for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Name)}


def ruff(root, *arguments):
    beside = Path(sys.executable).with_name('ruff')
    command = [str(beside) if beside.exists() else 'ruff', *arguments]
    config = Path(root) / 'pyproject.toml'
    if config.is_file():
        command += ['--config', str(config)]
    else:
        command += ['--isolated', '--line-length', '110']
        if arguments[0] == 'format':
            command += ['--config', 'format.quote-style = "single"']
    return command


def split(root, only=None, dry=False):
    folder = Path(root) / FOLDER
    path = folder / 'run.py'
    source = path.read_text(encoding='utf-8')
    lines = source.splitlines(keepends=True)
    body = ast.parse(source).body
    # The docstring and the imports, then the rest.
    k = 0
    while k < len(body) and (
        isinstance(body[k], (ast.Import, ast.ImportFrom))
        or (isinstance(body[k], ast.Expr) and isinstance(body[k].value, ast.Constant))
    ):
        k += 1
    head = ''.join(lines[: body[k - 1].end_lineno])
    # The imports that a new module gets: those of run.py, but for the modules of the split.
    kept = []
    for node, (_, text) in zip(body[1:k], chunks(lines, body[1:k], body[0].end_lineno)):
        if not (isinstance(node, ast.ImportFrom) and node.level == 1 and node.module in LAYOUT):
            kept.append(text)
    imports = ''.join(kept)
    tops = chunks(lines, body[k:], body[k - 1].end_lineno)
    run = next(node for node in body if isinstance(node, ast.ClassDef) and node.name == 'Run')
    # The header of the class can take several lines once it names its mixins.
    header_end = max([run.lineno, *(base.end_lineno for base in run.bases)])
    while not lines[header_end - 1].rstrip().endswith(':'):
        header_end += 1
    methods = chunks(lines, run.body, header_end)
    here = {name for names, _ in tops for name in names}

    owner = {name: module for module, (_, _, names, _) in LAYOUT.items() for name in names}
    home = {name: module for module, (_, _, _, names) in LAYOUT.items() for name in names}
    unknown = [names[0] for names, _ in methods if names and names[0] not in home and names[0] not in STAY]
    if unknown:
        raise SystemExit(f'run.py has methods that LAYOUT does not name: {unknown}')
    unknown = sorted(here - owner.keys() - {'Run'})
    if unknown:
        raise SystemExit(f'run.py has top-level names that LAYOUT does not name: {unknown}')
    wanted = list(LAYOUT) if only is None else list(only)
    for module in wanted:
        if module not in LAYOUT:
            raise SystemExit(f'{module} is no module of LAYOUT: {", ".join(LAYOUT)}')

    written, mixins, moved_tops = {}, [], set()
    for module in wanted:
        mixin, text, top_names, method_names = LAYOUT[module]
        parts = [(names, chunk) for names, chunk in tops if names and owner.get(names[0]) == module]
        own = [(names, chunk) for names, chunk in methods if names and names[0] in method_names]
        if not parts and not own:
            continue
        if (folder / f'{module}.py').exists():
            raise SystemExit(f'{module}.py is there, and run.py still has parts of it: move them by hand')
        top_text = ''.join(chunk for _, chunk in parts)
        body_text = ''.join(chunk for _, chunk in own)
        read = names_read(top_text) | (names_read('class _:\n' + body_text) if own else set())
        needs = {}
        for name in sorted(read):
            other = owner.get(name)
            if other is None or other == module:
                continue
            if name in here and other not in wanted[: wanted.index(module)]:
                raise SystemExit(f'{module} reads {name}, which is still in run.py: move {other} first')
            needs.setdefault(other, []).append(name)
        out = f'"""{text}\n\nMoved from `run.py` with no change (step B0-6).'
        if own:
            out += f' `{mixin}` is a part of `run.Run`: its methods\nread the run as `self`.'
        out += '\n"""\n' + imports
        for other, found in needs.items():
            out += f'from .{other} import {", ".join(found)}\n'
        out += top_text
        if own:
            out += f'\n\nclass {mixin}:\n    """See the module."""\n' + body_text
            mixins.append(mixin)
        written[module] = out
        moved_tops |= {name for names, _ in parts for name in names}

    # run.py: its head, the imports of the new modules, and what stays.
    moved_methods = {name for module in written for name in LAYOUT[module][3]}
    stay_methods = ''.join(chunk for names, chunk in methods if not (names and names[0] in moved_methods))
    out = head
    read = names_read('class _:\n' + stay_methods)
    for names, chunk in tops:
        if names and names[0] not in moved_tops and names != ('Run',):
            read |= names_read(chunk.lstrip('\n'))
    for module in written:
        mixin, _, top_names, method_names = LAYOUT[module]
        found = [name for name in top_names if name in moved_tops and name in read and name not in BACK]
        if mixin in mixins:
            found.append(mixin)
        if found:
            out += f'from .{module} import {", ".join(found)}\n'
        for name in top_names:
            if name in moved_tops and name in BACK:
                out += f'from .{module} import {name} as {name}  # {BACK[name]} imports it from here\n'
    for names, chunk in tops:
        if names == ('Run',):
            before = chunk[: chunk.index('class Run')]
            bases = [ast.unparse(base) for base in run.bases] + mixins
            out += before + f'class Run({", ".join(bases)}):\n' + stay_methods
        elif not (names and names[0] in moved_tops):
            out += chunk
    written['run'] = out
    if dry:
        for module, text in written.items():
            print(f'{module}.py: about {len(text.splitlines())} lines')
        return
    files = []
    for module, text in written.items():
        (folder / f'{module}.py').write_text(text, encoding='utf-8')
        files.append(str(folder / f'{module}.py'))
    subprocess.run([*ruff(root, 'check', '--select', 'F401,I001', '--fix', '--quiet'), *files], check=False)
    subprocess.run([*ruff(root, 'format', '--quiet'), *files], check=False)
    wrong = subprocess.run([*ruff(root, 'check', '--select', 'F', '--quiet'), *files], check=False)
    for module in written:
        print(f'{module}.py: {len((folder / f"{module}.py").read_text(encoding="utf-8").splitlines())} lines')
    if wrong.returncode:
        raise SystemExit('ruff finds a name that a module does not have: see above')


# ---- the check ------------------------------------------------------------------------------------

READ = r"""
import base64, importlib, json, marshal, sys, types
sys.path.insert(0, {root!r})
mixins = {mixins!r}
found = {{}}
for name in ['run', *{modules!r}]:
    try:
        module = importlib.import_module('napkin.engine.timeline.' + name)
    except ModuleNotFoundError as problem:
        if problem.name != 'napkin.engine.timeline.' + name:
            raise
        continue

    def visit(prefix, owner, top):
        for key, value in vars(owner).items():
            if isinstance(value, (staticmethod, classmethod)):
                value = value.__func__
            if isinstance(value, property):
                value = value.fget
            if isinstance(value, types.FunctionType) and value.__module__ == module.__name__:
                assert prefix + key not in found, prefix + key
                found[prefix + key] = value.__code__
            elif isinstance(value, type) and value.__module__ == module.__name__ and top:
                # A method of a mixin is a method of Run.
                visit('Run.' if key in mixins else key + '.', value, False)

    visit('', module, True)
run = importlib.import_module('napkin.engine.timeline.run')
attributes = sorted(name for name in dir(run.Run) if not name.startswith('__'))
code = {{key: base64.b64encode(marshal.dumps(value)).decode() for key, value in found.items()}}
print(json.dumps({{'attributes': attributes, 'code': code}}))
"""


def same_code(a, b):
    import types

    if a.co_code != b.co_code or a.co_names != b.co_names or a.co_varnames != b.co_varnames:
        return False
    if a.co_freevars != b.co_freevars or a.co_cellvars != b.co_cellvars or a.co_flags != b.co_flags:
        return False
    if len(a.co_consts) != len(b.co_consts):
        return False
    for x, y in zip(a.co_consts, b.co_consts):
        if isinstance(x, types.CodeType) != isinstance(y, types.CodeType):
            return False
        if isinstance(x, types.CodeType):
            if not same_code(x, y):
                return False
        elif type(x) is not type(y) or x != y:
            return False
    return True


def check(root, base):
    """Compare the functions of the split package in `root` with those of `base`."""
    import base64
    import json
    import marshal

    read = {}
    for where in (root, base):
        text = READ.format(
            root=str(Path(where).resolve()),
            mixins=[mixin for mixin, *_ in LAYOUT.values()],
            modules=list(LAYOUT),
        )
        made = subprocess.run([sys.executable, '-B', '-c', text], capture_output=True, text=True, check=False)
        if made.returncode:
            raise SystemExit(f'{where}: the package does not import:\n{made.stderr}')
        read[where] = json.loads(made.stdout)
    new, old = read[root], read[base]
    if new['attributes'] != old['attributes']:
        raise SystemExit(f'Run has other attributes: {sorted(set(new["attributes"]) ^ set(old["attributes"]))}')
    if set(old['code']) != set(new['code']):
        raise SystemExit(f'functions that only one side has: {sorted(set(old["code"]) ^ set(new["code"]))}')
    differ = [
        key
        for key in old['code']
        if not same_code(
            marshal.loads(base64.b64decode(old['code'][key])), marshal.loads(base64.b64decode(new['code'][key]))
        )
    ]
    if differ:
        raise SystemExit(f'functions whose code changed: {differ}')
    print(f'{len(old["code"])} functions have the same code; Run has the same {len(old["attributes"])} attributes')


if __name__ == '__main__':
    arguments = sys.argv[1:]
    options = {}
    for flag in ('--only', '--check'):
        if flag in arguments:
            at = arguments.index(flag)
            options[flag] = arguments[at + 1]
            del arguments[at : at + 2]
    dry = '--dry' in arguments
    arguments = [a for a in arguments if a != '--dry']
    if len(arguments) != 1:
        raise SystemExit(__doc__)
    if '--check' in options:
        check(arguments[0], options['--check'])
    else:
        split(arguments[0], options['--only'].split(',') if '--only' in options else None, dry)
