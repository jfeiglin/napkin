"""The checks of what a scenario means (`model/meaning.py`), which every front end calls: each rule has
one counterexample, built on the semantic model itself, so no front end's syntax is involved."""

from napkin.model.meaning import flat_clashes, meaning_errors
from napkin.model.semantic import Entity, Group, Profile, Run, Scenario, Setting, Value


def group(name, *profiles):
    return Group(name, tuple(Profile(p, f'{p}.', ('menu', name, p)) for p in profiles), ('menu', name))


GROUPS = (group('Pace', 'Slow', 'Fast'), group('Team', 'AI', 'Human'))


def value(name, *settings):
    """A value of an entity, with the settings (profile, where) that profiles give it."""
    return Value(
        name=name,
        kind='input',
        type='h',
        text=name,
        value='1 h',
        range=None,
        records=None,
        settings=tuple(Setting(profile, '2 h', where) for profile, where in settings),
        where=('values', name),
        value_where=('values', name, 'value'),
        range_where=('values', name, 'range'),
        type_where=('values', name, 'type'),
    )


def scenario(groups=GROUPS, runs=None, entities=()):
    runs = runs if runs is not None else (Run('a', ('Slow', 'AI'), ('runs', 'a')),)
    return Scenario(groups, runs, entities)


def found(scenario):
    return [(d['path'], d['message']) for d in meaning_errors(scenario)]


def test_a_scenario_that_means_what_it_says_has_no_diagnostic():
    entity = Entity(
        'crew', 'crew', None, None, (value('delay', ('Slow', ('p', 'Slow', 'delay'))),), ('crew',)
    )
    runs = (
        Run('a', ('Slow', 'AI'), ('runs', 'a')),
        Run('b', ('Fast', 'AI'), ('runs', 'b'), comparison='a', versus_where=('runs', 'b', 'versus')),
    )
    assert found(scenario(runs=runs, entities=(entity,))) == []


def test_the_menu_names_each_profile_once_with_its_line():
    empty = Group('Empty', (), ('menu', 'Empty'))
    twice = group('Again', 'Slow')
    blank = Group('Blank', (Profile('Quiet', '  ', ('menu', 'Blank', 'Quiet')),), ('menu', 'Blank'))
    assert found(scenario(groups=(*GROUPS, empty, twice, blank))) == [
        ('menu/Empty', 'a group of profiles names its profiles, each with its text'),
        ('menu/Again/Slow', 'Slow is already in the group Pace'),
        ('menu/Blank/Quiet', 'the text of a profile is nonempty text'),
    ]


def test_no_group_is_asked_of_a_run():
    # A run names at most one profile of each group, and need not name one of every group.
    runs = (Run('a', ('AI',), ('runs', 'a')),)
    assert found(scenario(runs=runs)) == []


def test_only_a_model_without_profiles_has_a_run_without_them():
    # The run `base` of a model without profiles names none; a model with profiles names its runs.
    assert found(scenario(groups=(), runs=(Run('base', (), ('runs', 'base')),))) == []
    assert found(scenario(runs=())) == [('menu/Pace', 'a model with options names its runs (runs:)')]


def test_a_run_has_a_usable_name_and_one_known_profile_of_each_group():
    runs = (
        Run('half rate', ('Slow',), ('runs', 'half rate')),
        Run('none', (), ('runs', 'none')),
        Run('typo', ('Slwo',), ('runs', 'typo')),
        Run('both', ('Slow', 'Fast'), ('runs', 'both')),
    )
    assert found(scenario(runs=runs)) == [
        (
            'runs/half rate',
            'a run name starts with a letter and has only letters, digits, _, . and -, so that an edit '
            "can name it: not 'half rate'",
        ),
        ('runs/none', 'a run lists its profiles'),
        # The profile of the file closest to the typo (difflib), and not the other one.
        ('runs/typo', "['Slwo'] are not profiles of the file; did you mean Slow?"),
        ('runs/both', "a run names one profile of each group, not two of ['Pace']"),
    ]


def test_a_comparison_names_another_run_that_is_no_comparison_itself():
    runs = (
        Run('a', ('Slow',), ('runs', 'a')),
        Run('b', ('Fast',), ('runs', 'b'), comparison='a', versus_where=('runs', 'b', 'versus')),
        Run('c', ('Slow',), ('runs', 'c'), comparison='b', versus_where=('runs', 'c', 'versus')),
        Run('d', ('Slow',), ('runs', 'd'), comparison='d', versus_where=('runs', 'd', 'versus')),
        Run('e', ('Slow',), ('runs', 'e'), comparison='z', versus_where=('runs', 'e', 'versus')),
    )
    message = 'a run is the comparison of another run that is no comparison itself, not {!r}'
    assert found(scenario(runs=runs)) == [
        ('runs/c/versus', message.format('b')),
        ('runs/d/versus', message.format('d')),
        ('runs/e/versus', message.format('z')),
    ]


def test_profiles_of_two_groups_never_set_one_value():
    # Two entities of one template share the template's lines, so the diagnostic is given once, at the
    # line of the second group (in the order of the groups' names: Pace, then Team).
    lines = (('Slow', ('Template', 'Slow', 'delay')), ('Human', ('Template', 'Human', 'delay')))
    entities = tuple(
        Entity(e, e, None, 'Template', (value('delay', *lines),), (e,)) for e in ('north', 'south')
    )
    assert found(scenario(entities=entities)) == [
        ('Template/Human/delay', "delay is set by options of two groups: ['Human', 'Slow']")
    ]


def test_two_entities_never_take_one_name_in_the_structure():
    # Copy 1 of the set `wave` is `wave_1` in the structure, as is an entity named `wave_1`.
    assert flat_clashes(['wave.1', 'wave_1', 'crew'], 'simulate') == ['wave_1']
    assert flat_clashes(['simulate', 'crew'], 'simulate') == ['simulate']
    assert flat_clashes(['wave.1', 'wave.2'], 'simulate') == []
