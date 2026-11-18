"""Every published version string derives from the two package constants (the library document
keeps the version of its own schema), and the check runs only from a source checkout. The package's
version is the distribution's metadata, or the checkout's pyproject.toml when nothing is installed."""

import json
import re
import tomllib
from pathlib import Path

from napkin import SCHEMA_VERSION, __version__
from napkin.schema import FOLDER as SCHEMAS
from tools import catalogue

# The checkout: this file reads its version strings, and no model.
ROOT = catalogue.ROOT


def test_release_metadata_carries_the_package_version():
    citation = (ROOT / 'CITATION.cff').read_text()
    assert re.search(r'^version: (\S+)$', citation, re.MULTILINE).group(1) == __version__
    # The distribution's version is written out in pyproject.toml, beside the package's own.
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    assert project['version'] == __version__


def test_a_checkout_that_is_not_installed_reads_its_version_from_pyproject(monkeypatch):
    import napkin

    def missing(name):
        raise napkin._metadata.PackageNotFoundError(name)

    monkeypatch.setattr(napkin._metadata, 'version', missing)
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    assert napkin._version() == project['version']


def test_scenarios_edits_and_reports_share_the_schema_version():
    # The edits and the reports carry the schema version as a string.
    for name in ('edits', 'report'):
        schema = json.loads((SCHEMAS / f'{name}.schema.json').read_text())
        assert schema['properties']['schema_version'] == {'const': SCHEMA_VERSION}, name


def test_the_library_document_has_the_version_of_its_schema():
    # The library's format did not change with the scenario language: it keeps its own version.
    schema = json.loads((SCHEMAS / 'library.schema.json').read_text())
    assert catalogue.vocabulary(ROOT)['schema_version'] == schema['properties']['schema_version']['const']


def test_the_tools_run_from_the_source_checkout_that_holds_them():
    """No wheel ships the tools, so their root is always a source checkout: the folder above `tools/`,
    which holds the project's metadata, its tests and its docs."""
    import tools

    assert Path(tools.__file__).resolve().parents[1] == catalogue.ROOT
    for name in ('pyproject.toml', 'tests', 'docs', 'napkin'):
        assert (catalogue.ROOT / name).exists(), name
