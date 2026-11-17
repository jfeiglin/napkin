"""The checks of what a scenario means, over its semantic model: one checker for each rule of
docs/language.md that the semantic model alone decides.

The front end calls these checks, so each has one implementation and gives one diagnostic: the menu
of profiles, the runs, and the profiles of two groups that set one value. A diagnostic names the place of the part that the front end gave it
(`where`). The rules of the file's own syntax stay in the front end.
"""

from __future__ import annotations

import re

from .ir import close_names, diagnostic, thaw
from .load import schema_document
from .semantic import flat_entity

# A run is named as an edit document names it (the edit schema, `$defs/run`).
RUN_NAME = re.compile(schema_document('edits')['$defs']['run']['pattern'])


def _fail(errors, where, message):
    errors.append(diagnostic('structure', '/'.join(map(str, where)), message))


def menu(scenario, errors):
    """{profile: its group} of the menu. Each group names its profiles, each with one line; a profile
    is in one group."""
    group_of = {}
    for group in scenario.groups:
        if not group.profiles:
            _fail(errors, group.where, 'a group of profiles names its profiles, each with its text')
            continue
        for profile in group.profiles:
            if profile.name in group_of:
                _fail(
                    errors, profile.where, f'{profile.name} is already in the group {group_of[profile.name]}'
                )
            group_of.setdefault(profile.name, group.name)
            text = thaw(profile.text)
            if not isinstance(text, str) or not text.strip():
                _fail(errors, profile.where, 'the text of a profile is nonempty text')
    return group_of


def run_errors(scenario, group_of, errors):
    """Each run has a name that an edit can name, and its profiles, at most one of each group; a run
    that is the comparison of another names a run that is no comparison itself. A model without
    profiles has runs without them: its one run `base` takes the values as the file writes them."""
    if scenario.groups and not scenario.runs:
        _fail(errors, scenario.groups[0].where, 'a model with options names its runs (runs:)')
    runs = {run.name: run for run in scenario.runs}
    compared = {run.name: thaw(run.comparison) for run in scenario.runs}
    for run in scenario.runs:
        name = run.name
        if not isinstance(name, str) or not RUN_NAME.match(name):
            _fail(
                errors,
                run.where,
                f'a run name starts with a letter and has only letters, digits, _, . and -, so that an edit can '
                f'name it: not {name!r}',
            )
        other = compared[name]
        if other is not None and (
            not isinstance(other, str) or other not in runs or other == name or compared[other] is not None
        ):
            _fail(
                errors,
                run.versus_where or run.where,
                f'a run is the comparison of another run that is no comparison itself, not {other!r}',
            )
        profiles = list(run.profiles)
        if not profiles:
            if scenario.groups:
                _fail(errors, run.where, 'a run lists its profiles')
            continue
        unknown = [p for p in profiles if p not in group_of]
        if unknown:
            close = close_names(unknown[0], group_of) if len(unknown) == 1 else ''
            _fail(errors, run.where, f'{unknown} are not profiles of the file{close}')
        groups = [group_of[p] for p in profiles if p in group_of]
        twice = sorted({g for g in groups if groups.count(g) > 1})
        if twice:
            _fail(errors, run.where, f'a run names one profile of each group, not two of {twice}')


def setting_errors(scenario, group_of, errors):
    """The profiles of two groups never set one value of an entity. The diagnostic names the setting of
    the second group, in the order of the groups' names, once."""
    seen = set()
    for entity in scenario.entities:
        for value in entity.values:
            first = {}
            for setting in value.settings:
                group = group_of.get(setting.profile)
                if group is not None:
                    first.setdefault(group, setting)
            if len(first) > 1:
                second = first[sorted(first)[1]]
                message = (
                    f'{value.name} is set by options of two groups: '
                    f'{sorted(s.profile for s in first.values())}'
                )
                if (second.where, message) not in seen:
                    seen.add((second.where, message))
                    _fail(errors, second.where, message)


def meaning_errors(scenario):
    """The diagnostics of what a scenario means (its semantic model, read leniently)."""
    errors = []
    group_of = menu(scenario, errors)
    run_errors(scenario, group_of, errors)
    setting_errors(scenario, group_of, errors)
    return errors


def flat_clashes(names, main):
    """The names that two entities take in the structure (`flat_entity`), sorted; the name of the main
    (`main`) when an entity takes it. Copy k of a set, `set.k`, is `set_k` there."""
    flat = [flat_entity(name) for name in names]
    taken = sorted({name for name in flat if flat.count(name) > 1})
    return taken or ([main] if main in flat else [])
