"""Discover model sources and their settings without compiling the catalogue."""

from napkin.draw import style
from napkin.model.language.modules import paths as model_paths
from napkin.model.library import library_folders
from tools import catalogue
from tools.publish.brief import BRIEF_FILE

SETTINGS = (style.STYLE_FILE, BRIEF_FILE)


def source_contract_files(root, ids=None, *, include_fixtures=True):
    """Find selected source files and their shared folders without compiling a model."""
    scenarios = sorted(path for sid, path in catalogue.entries(root).items() if ids is None or sid in ids)
    entries = set(scenarios)
    if ids is None:
        # The complete check reads every committed model file and stylesheet below `scenarios/`, in a
        # package's folder and in each of its variants' folders: also the modules that no current model
        # uses, a main file that only its variants read and the files of a folder that is no owner's,
        # so that none of them escapes the check.
        modules = sorted(
            path
            for path in (root / 'scenarios').rglob('*.scn')
            if path not in entries and 'tests' not in path.relative_to(root / 'scenarios').parts
        )
    else:
        # A selected model's check reads the files of its package's folder and of its variant's folder,
        # also the modules there that no current model uses, and each file of its package that it reads,
        # found from the `use` lines alone: a variant's main file and a module in a folder of the package.
        folders = {folder for path in scenarios for folder in library_folders(path)}
        found = {path for folder in folders for path in folder.glob('*.scn')}
        found.update(path.resolve() for scenario in scenarios for path in model_paths(scenario))
        entered = {path.resolve() for path in entries}
        modules = sorted(path for path in found if path not in entered)
    fixtures = sorted((root / 'tests' / 'acceptance').glob('*.scn')) if include_fixtures else []
    styles = sorted(
        (
            path
            for name in SETTINGS
            for pattern in (f'*/{name}', f'*/variants/*/{name}')
            for path in (root / 'scenarios').glob(pattern)
        )
        if ids is None
        # A selected model's own stylesheet and brief settings: its folder's, else its package's.
        else {taken for path in scenarios for name in SETTINGS if (taken := style.lookup(path, name))}
    )
    return scenarios, modules, fixtures, styles
