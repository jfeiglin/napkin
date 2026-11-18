"""What each test file needs, from its imports and its text: `none` (no model text and no compiler),
`source` (it compiles model text) or `catalogue` (it reads `scenarios/` or `examples/`).

    python scratch/rewrite/triage/needs.py > scratch/rewrite/triage/needs.csv

A file needs what the test modules that it imports need. This is the mechanical part of the triage:
the classes of the files come from the other files of this folder.

`catalogue` is given too often: a file that only makes a synthetic catalogue in a temporary folder
has it too. What matters for the dormant list is `none` against the rest: a file with `none` still
runs when the old language is gone.
"""

import ast
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# The modules that make or compile model text, and the names that do it.
SOURCE_MODULES = (
    'napkin.model',
    'napkin.package',
    'napkin.session',
    'napkin.spread',
    'napkin.commands',
    'napkin.cli',
    'napkin.draw',
    'napkin.dynamics',
    'napkin.engine.study',
    'napkin.engine.report',
    'napkin.engine.uncertainty',
    'napkin.engine.runtime',
    'napkin.engine.timeline',
    'napkin.engine.expectations',
    'tools.publish',
    'tools.evidence',
    'tools.compare',
    'tools.bench',
    'tools.new',
)
SOURCE_NAMES = re.compile(r'\b(load_scenario|load_package|evaluate_study|sample_result|evaluate_uncertainty|Session)\b')
CATALOGUE = re.compile(r"""(tools\.catalogue|['"/]scenarios['"/]|['"/]examples['"/]|catalogue\.)""")


def imports(path):
    """The modules that a file imports, as dotted names."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            found.add(node.module)
            found |= {f'{node.module}.{alias.name}' for alias in node.names}
    return found


def module_file(name):
    path = ROOT / Path(*name.split('.'))
    for candidate in (path.with_suffix('.py'), path / '__init__.py'):
        if candidate.is_file():
            return candidate
    return None


def needs(path, seen=None):
    seen = seen if seen is not None else set()
    if path in seen:
        return 'none'
    seen.add(path)
    text = path.read_text(encoding='utf-8')
    names = imports(path)
    level = 'none'
    relative = path.relative_to(ROOT).as_posix()
    if relative.startswith('scenarios/') or relative == 'tests/helpers.py' or CATALOGUE.search(text):
        level = 'catalogue'
    elif any(name == module or name.startswith(module + '.') for name in names for module in SOURCE_MODULES):
        level = 'source'
    elif SOURCE_NAMES.search(text):
        level = 'source'
    for name in sorted(names):
        if name.split('.')[0] in ('tests', 'scenarios'):
            inner = module_file(name)
            if inner is not None and inner != path:
                below = needs(inner, seen)
                if below == 'catalogue' or (below == 'source' and level == 'none'):
                    level = below
    return level


def main():
    files = sorted(
        path
        for base in ('tests', 'scenarios')
        for path in (ROOT / base).rglob('*.py')
        if '__pycache__' not in path.parts and path.name != '__init__.py' and (base == 'tests' or 'tests' in path.parts)
    )
    out = csv.writer(sys.stdout, lineterminator='\n')
    out.writerow(['path', 'lines', 'tests', 'needs'])
    for path in files:
        text = path.read_text(encoding='utf-8')
        tests = len(re.findall(r'^(?:async )?def test_', text, flags=re.M)) + len(re.findall(r'^    def test_', text, flags=re.M))
        out.writerow([path.relative_to(ROOT).as_posix(), text.count('\n'), tests, needs(path)])


if __name__ == '__main__':
    main()
