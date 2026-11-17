"""What the pages read from a model, generated from the model (docs/language.md, §2.2).

Only the summary and the reviewers' texts in the notes (`notes:`) are written as prose. Everything else that the
briefs and the methods show comes from the model that `build_model` gives, under the
structure's names (docs/python-api.md, "Names"): an entity is its name in the structure (`set_k`
for copy k of a set), an input and a value `entity.value`, an event and an outcome the structure's.

`Pages(model)` generates each part; `pages(model)` gives every part:

| Part | What it holds |
| --- | --- |
| `cards` | `{event: [{text, actor, occurrence}]}`: the timeline cards of the events, from the texts of the events and of their outcomes and their roles. `occurrence` (from 1) is there when a text lists one text for each time its event happens. |
| `story` | The brief of the two default runs, or None without two: `{hook, counterfactual, decisive_choice, runs, measures, key_inputs}`. |
| `texts` | `{run: {entity.value: text}}`: the text values as each run's profiles set them; a card names them in braces, `{entity.value}`. |
| `metrics` | `[{outcome, style}]`: the outputs that `show` lists (`brief.toml`), each with its style (deaths, casualties, loss or service). |
| `options` | `{axis, options, responses}`: the name of the options that each run takes besides its response, the options and the responses, in menu order. The responses are the menu's options of the group that `choice_group` names in `brief.toml` (none without it). |
| `runs` | `{run: {name, response, option, inputs, comparison_of, narrative}}`: a run's response is its option of that group, or None. |
| `controls` | The main inputs: the inputs that the options set, in menu order. |
| `groups` | `[{entity, name, doc, inputs}]`: one input group for each entity that has inputs. |
| `entities`, `statuses`, `labels` | The name of each entity, the entities that show a status, and the labels of the inputs, stocks, tallies, number states and outputs. |
| `review` | `{limitations, premises, start_limits, verification, reachability, benchmark, exposure}`: the reviewers' notes that the pages show, with their records. `start_limits` is the statement of the premise with id START: the limits of the first move. |
| `operation` | The AI operation: the entity with the role adversary, `{actor, doc, entity, basis, tempo, human_runs}`, or None without one. `tempo` is the input of its own that delays one of its events and that a run's other options set; `human_runs` are the runs in which the human team acts. |

The names of the entities and the labels of the fields are the builder's: it writes them in each
structure, and they are read here from `model.whole`, which keeps every part.

The language gives the notes no meaning and checks no key of them. The catalogue's pages define the
notes that they and the summaries read (`NOTES`), and check them when they are made: a note that
none of them reads fails at its line, as does a note in another shape, a premise or a limitation
without its `id` and `statement`, or a copy of a verification status (scenarios/docs/catalogue.md).

The pages name the options that a run takes besides its response after the groups that hold them
(docs/language.md, §2.9). A run's response is its option of the group that `choice_group` names in
`brief.toml`. The option groups are the other groups that every run names or that hold an option that sets a
start state, so runs of one option share one structure. A run's option is made of the menu's options
that it takes in the option groups: in each one, its own, or the group's first option that sets
nothing where the run names none. A run's other options set its own `inputs` (a human team's pace);
a comparison's `narrative` is the menu lines of the options that it adds to the run it compares with.
"""

from __future__ import annotations

import re

from napkin.model import resolved
from napkin.model.ir import ModelError, diagnostic, thaw
from napkin.model.runs import Runs

from . import brief as styles

# How many measures the brief compares the two default runs on, before the harms.
MEASURES = 2
# The reviewers' notes that the pages and the summaries read (docs/language.md, §2.11), with the shape
# that they read: a text, a record or a list of records. A note that none of them reads is a mistake,
# such as a misspelt name.
NOTES = {
    'premises': list,
    'limitations': list,
    'exposure': str,
    'verification': dict,
    'reachability': dict,
    'benchmark': dict,
    'counterfactual': str,
    'decisive': str,
}
SHAPES = {str: 'nonempty text', dict: 'a record', list: 'entries, `ID: "statement"`'}
# The keys of each entry of a note of entries: its `id` and `statement`, its records (`basis`), and
# for a premise what follows if it is false (`if_false`).
RECORDS = {
    'premises': {'id', 'statement', 'basis', 'if_false'},
    'limitations': {'id', 'statement', 'basis'},
}
# The line of the file that gives a key of an entry: `if_false` is `otherwise:`. Any other line under
# an entry is its key, `key:`.
ENTRY_LINES = {'if_false': 'otherwise:'}
# The notes whose entries the pages read as a list of `{id, statement}`, and the keys that the pages
# give an entry: a line under an entry with one of these names keeps its place, `key:`, as its key, so
# that it never stands for that key.
ENTRY_NOTES = ('premises', 'limitations')
ENTRY_KEYS = ('id', 'statement', 'basis', 'if_false')
# The library holds the verification status of each claim, so a copy of it in the notes goes stale.
VERIFICATION_COPY = 'verification_status'
# The style of an output that reports deaths, casualties or loss; any other output shows a service.
STYLES = {'deaths': 'deaths', 'casualties': 'casualties', 'loss': 'loss'}
# A text names a text value of the entity that acts in braces: `{actor}`.
BRACES = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*)\}')
# A card names a value of the entity that acts in braces, `{entity.value}`, as `cards` writes it.
NAMED = re.compile(r'\{([^}]+)\}')
# The end of a first sentence: a full stop after a word.
SENTENCE_END = re.compile(r'(?<=[a-z0-9)])\.(\s|$)')


def pages(model):
    """Every part of the pages' data of one model."""
    return Pages(model).all()


def first_sentence(text):
    """The first sentence of a text: up to the first full stop that ends a word."""
    match = SENTENCE_END.search(text)
    return text[: match.end()].strip() if match else text


def review_of(notes):
    """The notes of a model (`semantic.Note`) as the pages read them: each note by its key, with its
    value or a record of the notes under it. The entries of `premises` and `limitations` are a list of
    `{id, statement}`, with `if_false` (`otherwise:`) and `basis` (its records, as written); any other
    line under an entry, which the pages reject, keeps its key. A note of entries that the file writes
    in another shape keeps that shape."""
    out = {}
    for note in notes:
        if note.key in ENTRY_NOTES and note.value is None:
            entries = []
            for entry in note.notes:
                item = {'id': entry.key, 'statement': thaw(entry.value)}
                for sub in entry.notes:
                    if sub.key == 'otherwise' and 'if_false' not in item:
                        item['if_false'] = thaw(sub.value)
                    else:
                        item[f'{sub.key}:' if sub.key in ENTRY_KEYS or sub.key in item else sub.key] = tree(
                            sub
                        )
                if entry.records is not None:
                    item['basis'] = thaw(entry.records)
                entries.append(item)
            out[note.key] = entries
            continue
        out[note.key] = tree(note)
    return out


def tree(note):
    """The value of a note, or a record of the notes under it."""
    if note.notes:
        return {sub.key: tree(sub) for sub in note.notes}
    return thaw(note.value)


def verification_copies(notes):
    """The places of the notes named `verification_status`, at any depth."""
    out = []
    for note in notes:
        if note.key == VERIFICATION_COPY:
            out.append(note.where)
        out += verification_copies(note.notes)
    return out


def review_note(reviewed, path):
    """(the note whose records a site of the evidence holds, the key of the records), or (None, None)
    for a site outside the notes that the pages show with their records. Such a site is the place of a
    premise or a limitation, `notes:/premises:/ID:`, or of a note of a record, such as
    `notes:/benchmark:`."""
    if path[0] == 'notes:' and len(path) == 3:
        section, entry = str(path[1]).removesuffix(':'), str(path[2]).removesuffix(':')
        found = next((item for item in reviewed.get(section) or [] if item.get('id') == entry), None)
        return (found, 'basis') if found is not None else (None, None)
    if path[0] == 'notes:' and len(path) == 2:
        found = reviewed.get(str(path[1]).removesuffix(':'))
        return (found, 'basis') if isinstance(found, dict) else (None, None)
    return None, None


class Pages:
    """The pages' data of one model, from its semantic model (`model.scenario`). The model has been
    read, built and checked."""

    def __init__(self, model):
        self.model = model
        self.scenario = model.scenario
        # What the pages show first: the brief settings beside the model's file (`brief.toml`). The
        # pages never read the picture (`style.toml`).
        self.brief = styles.brief_of(model)
        self.reviewed = self.notes()
        self.menu = thaw(model.menu)
        self.group_of = {option: group for group, options in self.menu.items() for option in options}
        self.flat = {name: flat for flat, name in model.entities.items()}
        # Every part, also the parts that a run leaves out: the names and labels are the builder's.
        self.whole = next(iter(model.whole.values()))

    def all(self):
        return {
            'cards': self.cards(),
            'story': self.story(),
            'texts': self.texts(),
            'metrics': self.metrics(),
            'options': self.options(),
            'runs': self.runs(),
            'controls': self.controls(),
            'groups': self.groups(),
            'entities': self.entity_names(),
            'statuses': self.statuses(),
            'labels': self.labels(),
            'review': self.review(),
            'operation': self.operation(),
        }

    # ---- helpers ------------------------------------------------------------------------------

    def notes(self):
        """The notes of the file as the pages read them (`review_of`), each note that the pages and the
        summaries read in the shape that they read it (`NOTES`): a note that none of them reads fails,
        as a misspelt name does, and so does a copy of a verification status at any depth. The language
        gives the notes no meaning; the catalogue's pages define the keys that they read and check them
        here. Each problem is at the place of its note, `notes:/limitations:`, of its entry,
        `notes:/limitations:/L1:`, or of a line under the entry."""
        for where in verification_copies(self.scenario.notes):
            self.fail(where, 'the library holds the verification status: a copy in the notes goes stale')
        review = review_of(self.scenario.notes)
        for key, note in review.items():
            where = ('notes:', f'{key}:')
            if key not in NOTES:
                self.fail(where, f'no page reads the note {key!r}; they read {sorted(NOTES)}')
            if not isinstance(note, NOTES[key]) or (isinstance(note, str) and not note.strip()):
                self.fail(where, f'the note {key} is {SHAPES[NOTES[key]]}')
            for item in note if key in RECORDS else ():
                if not isinstance(item, dict):
                    self.fail(where, f'the note {key} holds entries, `ID: "statement"`')
                entry = (*where, f'{item["id"]}:')
                for name in item:
                    if name not in RECORDS[key]:
                        line = ENTRY_LINES.get(name) or (name if name.endswith(':') else f'{name}:')
                        self.fail((*entry, line), f'an entry of {key} has no line {line}')
                if not isinstance(item['statement'], str) or not item['statement'].strip():
                    self.fail(entry, f'an entry of {key} is `ID: "statement"`, its statement nonempty text')
                if 'if_false' in item and (
                    not isinstance(item['if_false'], str) or not item['if_false'].strip()
                ):
                    self.fail((*entry, 'otherwise:'), 'otherwise: is nonempty text')
        return review

    def fail(self, path, message):
        """A diagnostic of the file at `path`, with the line of the nearest key that it has."""
        key = tuple(path)
        while key and key not in self.model.lines:
            key = key[:-1]
        line = self.model.lines.get(key) if key else None
        item = diagnostic('pages', '/'.join(map(str, path)), message)
        file = self.model.files.get(key) or self.model.origin  # a line of a module is in the module
        raise ModelError([{**item, **({'line': line} if line else {}), 'file': file}])

    def field_name(self, key):
        """The structure's name of `entity.field` of the file, or None for an entity it does not have."""
        entity, _, member = key.rpartition('.')
        return f'{self.flat[entity]}.{member}' if entity in self.flat else None

    def reports(self, output):
        """The category of an output as its file writes it, a tag such as `deaths`, or None
        (`entity.field`, or an output of the main)."""
        return self.scenario.output(output).reports

    def sets_something(self, option):
        """Whether an option sets a field of some entity; one that sets nothing means the defaults."""
        return any(
            setting.profile == option for entity in self.scenario.entities for setting in entity.settings
        )

    @staticmethod
    def role(entity):
        """The role of an entity as written, or `responder`."""
        return thaw(entity.role) if entity.role is not None else 'responder'

    def adversary(self):
        """The entity with the role adversary, whose class the pages show as the AI operation, or None:
        a document outside the catalogue can have none. The role is a tag that only the pages read, and
        the pages show one operation, so at most one entity has it."""
        found = [entity for entity in self.scenario.entities if entity.role == 'adversary']
        if len(found) > 1:
            names = [entity.name for entity in found]
            self.fail(
                (*found[1].where, 'role:'),
                f'the pages show one AI operation: {names} have the role adversary',
            )
        return found[0].name if found else None

    # ---- the timeline -------------------------------------------------------------------------

    def cards(self):
        """The timeline cards of the events, from the texts of the events and of their outcomes.

        An event that waits shows the card of its text when it triggers. Each outcome shows the cards
        of what happens when the event fires with it: the event's text, for an event that does not
        wait, and the outcome's text. The actor of a card is the outcome's role, else the event's, else
        its entity's. Braces name a value of the entity that acts, `{entity.value}`, which the pages
        fill for each run (`texts`)."""
        out = {}

        def cards_of(doc, actor, owner):
            texts = [self.braced(text, owner) for text in (doc if isinstance(doc, list) else [doc])]
            if len(texts) == 1:
                return [{'text': texts[0], 'actor': actor}]
            # One text for each time the event happens; the last one for every later time.
            return [{'text': text, 'actor': actor, 'occurrence': i} for i, text in enumerate(texts, 1)]

        for entity in self.scenario.entities:
            e = entity.name
            role = self.role(entity)
            for event in entity.events:
                key = f'{e}.{event.name}'
                actor = thaw(event.role) if event.role is not None else role
                doc = thaw(event.text)
                if event.after is not None and doc:
                    out[self.model.events[key]] = cards_of(doc, actor, e)
                for outcome in event.outcomes or (None,):
                    found = cards_of(doc, actor, e) if event.after is None and doc else []
                    if outcome is not None and outcome.text is not None:
                        own = thaw(outcome.role) if outcome.role is not None else actor
                        found += cards_of(thaw(outcome.text), own, e)
                    if found:
                        name = outcome.name if outcome is not None else 'done'
                        out[self.model.events[f'{key}.{name}']] = found
        return out

    def braced(self, text, owner):
        """A text whose braces name text values of the entity `owner`, `{name}`, with each brace as
        `{entity.name}`, the form that the pages fill for each run (`texts`)."""
        return BRACES.sub(lambda m: '{' + self.flat[owner] + '.' + m.group(1) + '}', text)

    def texts(self):
        """{run: {entity.value: text}}: each text value, as the run's profiles set it (the run
        resolution's texts)."""
        runs = Runs.from_table(self.model.run_table)
        out = {}
        for run, info in self.model.runs.items():
            texts = runs.values_of(info['options']).texts
            out[run] = {self.field_name(key): text for key, text in texts.items()}
        return out

    # ---- the brief ----------------------------------------------------------------------------

    def story(self):
        """The two default runs side by side, or None without two: the first is the main run, the
        second its comparison. The hook is the summary's first sentence; the counterfactual and the
        decisive choice are the reviewers' texts."""
        runs = styles.featured(self.brief, self.model)
        if len(runs) != 2:
            return None
        return {
            'hook': first_sentence(thaw(self.scenario.summary) or ''),
            'counterfactual': self.reviewed.get('counterfactual', ''),
            'decisive_choice': self.reviewed.get('decisive', ''),
            'runs': runs,
            'measures': self.measures(),
            'key_inputs': self.key_inputs(),
        }

    def measures(self):
        """The outputs that the brief compares the two default runs on, before the harms: the first
        outputs of `show` that report nothing (no harm and no exposure) and count a total over the run."""
        totals = [
            self.model.outputs[x]
            for x in styles.shown(self.brief, self.model)
            if not self.reports(x) and self.whole.outcomes[self.model.outputs[x]].kind == 'cumulative'
        ]
        return totals[:MEASURES]

    def key_inputs(self):
        """The inputs that the brief lists: the brief's `drivers`, in its order, or the controls."""
        return styles.drivers(self.brief, self.model)

    def metrics(self):
        """The outputs that the pages show, in the order of `show`, each with its style."""
        return [
            {'outcome': self.model.outputs[x], 'style': STYLES.get(self.reports(x), 'service')}
            for x in styles.shown(self.brief, self.model)
        ]

    # ---- options and runs ---------------------------------------------------------------------

    def option_groups(self):
        """The menu groups whose options make the runs' options, in menu order: besides the brief's
        `choice_group`, each group that every run names, or that holds an option that sets a start
        state."""
        starts = set(self.model.start_options)
        runs = self.model.runs.values()
        return [
            group
            for group, options in self.menu.items()
            if group != self.brief.choice_group
            and (
                all(any(self.group_of[p] == group for p in run['options']) for run in runs)
                or starts & set(options)
            )
        ]

    def option(self, run_options, groups):
        """The menu's options that make a run's option: in each option group, the option of
        `run_options` (the run's), or else the group's first option that sets nothing."""
        chosen = []
        for group in groups:
            picked = [p for p in run_options if self.group_of[p] == group]
            empty = [p for p in self.menu[group] if not self.sets_something(p)]
            chosen += picked or empty[:1]
        return chosen

    def options(self):
        """The name of the options (the groups that hold them, joined by " · "), the options that the
        runs take, and the responses, each with its menu line, in menu order."""
        groups = self.option_groups()
        order = {option: i for i, option in enumerate(self.group_of)}
        found = []
        for run in self.model.runs.values():
            chosen = self.option(run['options'], groups)
            if chosen not in found:
                found.append(chosen)
        found.sort(key=lambda chosen: [order[p] for p in chosen])
        return {
            'axis': {'name': ' · '.join(groups), 'groups': groups} if groups else None,
            'options': [
                {
                    'name': ' · '.join(chosen),
                    'options': chosen,
                    'doc': ' '.join(self.menu[self.group_of[p]][p] for p in chosen) or None,
                }
                for chosen in found
            ],
            'responses': [
                {'name': option, 'doc': line}
                for option, line in (self.menu.get(self.brief.choice_group) or {}).items()
            ],
        }

    def runs(self):
        """Each run's name, its response, its option, the inputs that its other options set, the run
        that it is the comparison of, and the narrative of a comparison: the menu lines of the
        options that it adds to that run."""
        groups = self.option_groups()
        out = {}
        for run, info in self.model.runs.items():
            run_options = list(info['options'])
            response = next((p for p in run_options if self.group_of[p] == self.brief.choice_group), None)
            others = [p for p in run_options if self.group_of[p] not in (self.brief.choice_group, *groups)]
            inputs = {
                name: spec['options'][option]['value']
                for option in others
                for name, spec in self.model.inputs.items()
                if option in spec['options']
            }
            other = info['comparison_of']
            own = [p for p in run_options if p not in self.model.runs[other]['options']] if other else []
            out[run] = {
                'name': info['name'],
                'response': response,
                'option': ' · '.join(self.option(run_options, groups)),
                'inputs': inputs,
                'comparison_of': other,
                'narrative': ' '.join(self.menu[self.group_of[p]][p] for p in own) or None,
            }
        return out

    # ---- the inputs ---------------------------------------------------------------------------

    def controls(self):
        """The main inputs: the inputs that the options set, in menu order."""
        return styles.controls(self.model)

    def groups(self):
        """One input group for each entity that has inputs: the entity's name, and its doc as the
        group's description."""
        names = self.entity_names()
        out = []
        for declared in self.scenario.entities:
            entity = self.flat[declared.name]
            inputs = [name for name, info in self.model.inputs.items() if info['entity'] == entity]
            if inputs:
                out.append(
                    {'entity': entity, 'name': names[entity], 'doc': thaw(declared.text), 'inputs': inputs}
                )
        return out

    # ---- names and labels ---------------------------------------------------------------------

    def entity_names(self):
        """{entity: its name on the pages}, as the builder writes it in the structure: the file's
        entities in its order, then the main's (`simulate`), which the pages do not list."""
        entities = self.whole.entities
        own = [self.flat[entity.name] for entity in self.scenario.entities]
        return {entity: entities[entity].label for entity in [*own, *(e for e in entities if e not in own)]}

    def statuses(self):
        """The entities that show a status, in the file's order."""
        return [self.flat[entity.name] for entity in self.scenario.entities if entity.status is not None]

    def labels(self):
        """The labels of the inputs, of the stocks, tallies and number states, and of the outputs, as
        the builder writes them in the structure."""
        whole = self.whole
        return {
            'inputs': {name: parameter.label for name, parameter in whole.parameters.items()},
            'quantities': {qid: q.label for qid, q in whole.quantities.items() if q.label},
            'outcomes': {oid: outcome.label for oid, outcome in whole.outcomes.items()},
        }

    # ---- the review and the attacker ----------------------------------------------------------

    def review(self):
        """The review's records that the pages show: the limitations, the premises, the limits of the
        first move (`start_limits`: the statement of the premise with id START, which needs no basis
        and is not one of the premises), the consequence review, the reachability assessment, the
        source benchmark, and how to read the output that reports exposure. A named basis in them is
        written out as its record."""
        reviewed = thaw(self.reviewed)
        for path, value in self.model.evidence['sites'].items():
            holder, key = review_note(reviewed, path)
            if holder is not None:
                holder[key] = thaw(value)
        premises = reviewed.get('premises') or []
        out = {
            'limitations': [
                {'id': item['id'], 'statement': item['statement']}
                for item in reviewed.get('limitations') or []
            ],
            'premises': [p for p in premises if p.get('id') != 'START'],
        }
        limits = [p['statement'] for p in premises if p.get('id') == 'START']
        if limits:
            out['start_limits'] = limits[0]
        for key in ('verification', 'reachability', 'benchmark'):
            if key in reviewed:
                out[key] = reviewed[key]
        exposure = next((x for x in self.model.outputs if self.reports(x) == 'exposure'), None)
        if exposure is not None:
            outcome = self.model.outputs[exposure]
            out['exposure'] = {'outcome': outcome, 'scope': self.whole.outcomes[outcome].scope}
            if 'exposure' in reviewed:
                out['exposure']['interpretation'] = reviewed['exposure']
        return out

    def operation(self):
        """The AI operation: the entity with the role adversary, or None without one. Its text describes
        it, and the text's first sentence names the actor; its actions are its events that wait (and
        the first move, when it makes it). Its tempo is the input that a wait of its events names and
        that a run's other profiles set (a human team's pace), when there is one such input.

        A value that the entity's cards name in braces (`{actor}`) names the attacker that acts,
        because braces start a sentence. The attacker is the AI agent or the human team (the glossary
        of CONTRIBUTING.md, "Writing style"), so the human team acts in each run whose options give such a field
        another text than its own (`human_runs`). The tempo does not decide this: an option can change
        the AI's pace, a human team can differ from the AI in other inputs only, and a human team can
        be an option of the runs, whose menu options the tempo leaves out."""
        e = self.adversary()
        if e is None:
            return None
        declared = self.scenario.entity(e)
        entity = self.flat[e]
        groups = {self.brief.choice_group, *self.option_groups()}
        tempo = set()
        # A delay of one of its events that is a value of its own.
        for event in declared.events:
            delay = event.after.node if event.after is not None else None
            if not isinstance(delay, resolved.Ref) or delay.entity != e:
                continue
            name = f'{entity}.{delay.member}'
            if name in self.model.inputs and any(
                self.group_of[p] not in groups for p in self.model.inputs[name]['options']
            ):
                tempo.add(name)
        named = {
            name
            for cards in self.cards().values()
            for card in cards
            for name in NAMED.findall(card['text'])
            if name.rpartition('.')[0] == entity
        }
        own = {
            self.field_name(key): text for key, text in Runs.from_table(self.model.run_table).texts.items()
        }
        texts = self.texts()
        doc = thaw(declared.text)
        return {
            'actor': doc.split('. ')[0].rstrip('.'),
            'doc': doc,
            'entity': entity,
            'basis': thaw(declared.records),
            'tempo': tempo.pop() if len(tempo) == 1 else None,
            'human_runs': [run for run in self.model.runs if any(texts[run][n] != own[n] for n in named)],
        }
