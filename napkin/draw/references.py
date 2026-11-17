"""The references of a picture (docs/draw.md, D-55): one numbered list of the records that the shown
symbols and equation lines rest on, and the marks that point into the list.

A caller gives the cited places in reading order, `[(place, records), …]`. A place is any hashable
key of the caller's, such as a row of the Symbols table or an equation line. Its records are the
`.records` of a part of the semantic model: None, one record, or a list of them (docs/language.md,
§2.10). `references` gives the entries, numbered 1 to n by first use, and the marks of each place.
Everything that an entry shows comes from the records of the model and of its library
(`model.library`).

Each record gives entries by its kind:

| Record | Its entries |
| --- | --- |
| `source` | a "Source" entry for the source of each of its claims |
| `source_transfer` | a "Source, applied here" entry for the source of each of its claims |
| `assumption` | the entry of the assumption that it names; without an ID, an entry of its own |
| `identity` | an entry of its own |
| `convention` | the entry of the convention that it names; without an ID, an entry of its own |

- **One entry for each source.** The claims of one source that the places cite join in one entry,
  with each place in the source that they use (the claims' locators). A source that one place cites
  directly and another place applies here has two entries, "Source" and "Source, applied here", so
  that each label stays true.
- **An assumption always shows.** A record of any kind that names an assumption also cites that
  assumption's entry: a `source_transfer` that names one gives its source entries and the
  assumption's entry. Places that cite one assumption share its entry.
- **The claims of an assumption, an identity or a convention** inform that record. They do not make
  the value sourced (as `napkin compile` counts: `SOURCED`), so they give no "Source" entry.
- **The label of an assumption** comes from its review status in the library (`REVIEW_WORDS`). An
  assumption with no ID, or with no entry in the library, is "Assumption, not reviewed".
- **No record ID shows.** The label, the text, the link text and the hover hold words of the
  records only. Where the words of a record name another record of the library by its ID, the
  entry shows that record's name instead (`_Reader.words`): a source and a claim by who and the
  year of the source, an assumption and a convention by their title in quotes. The IDs and names go
  in `record`, for a `data-record` attribute.
- **Links** go to `https://doi.org/<DOI>` when the source has a DOI, else to its URL, and only to
  `http` and `https` addresses (`link_of`).
- **`kinds`** lists the kinds of entry that the list holds (the stylesheet's `references.kinds`).
  A kind left out has no entry, no number and no mark. `assumption` cannot be left out: a `kinds`
  without it is a ValueError, as is a kind that is not one of `KINDS`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from .text import ELLIPSIS

# The kinds of entry, in the order of the stylesheet's `references.kinds`, and the words that start
# each entry. An assumption's words come from its review status.
KINDS = ('source', 'source_transfer', 'identity', 'convention', 'assumption')
KIND_WORDS = {
    'source': 'Source',
    'source_transfer': 'Source, applied here',
    'identity': 'Identity, true by definition',
    'convention': 'Convention',
    'assumption': 'Assumption, not reviewed',
}
# The kinds in the line that says which kinds a list leaves out (`left_out_words`).
LEFT_OUT_WORDS = {
    'source': 'sources',
    'source_transfer': 'sources applied here',
    'identity': 'identities',
    'convention': 'conventions',
}
REVIEW_WORDS = {
    'unreviewed': 'Assumption, not reviewed',
    'confirmed': 'Assumption, confirmed by review',
    'replaced': 'Assumption, replaced',
}
# The colour of a mark for each kind of entry: a source, a source applied here, a rule (an identity or
# a convention) and an assumption.
COLOURS = ('source', 'transfer', 'rule', 'assumption')
COLOUR_KIND = {
    'source': 'source',
    'source_transfer': 'transfer',
    'identity': 'rule',
    'convention': 'rule',
    'assumption': 'assumption',
}
# The kinds of record (docs/language.md, §2.10), and those whose claims are the sources of a value.
RECORD_KINDS = frozenset({'source', 'source_transfer', 'assumption', 'identity', 'convention'})
SOURCED = frozenset({'source', 'source_transfer'})
# The collections of the library whose records have IDs.
COLLECTIONS = ('sources', 'claims', 'assumptions', 'conventions')

# The longest title, place in a source and sentence that an entry shows, in characters.
TITLE_ROOM = 60
PLACE_ROOM = 40
SENTENCE_ROOM = 120
# The end of a sentence: a stop, then a space and a capital letter or a digit.
SENTENCE_END = re.compile(r'[.!?]["”’)\]]*\s+(?=["“‘(\[]?[A-Z0-9])')
# Words that end with a stop inside a sentence.
ABBREVIATIONS = frozenset(
    {
        'al', 'approx', 'ca', 'cf', 'ch', 'co', 'dr', 'eq', 'etc', 'fig', 'figs', 'inc', 'jr', 'ltd',
        'mr', 'mrs', 'ms', 'no', 'nos', 'p', 'pp', 'para', 'ref', 'sec', 'sr', 'st', 'tab', 'vol', 'vs',
    }
)  # fmt: skip
INITIALS = re.compile(r'(?:[a-z]\.)*[a-z]')
DOI = re.compile(r'10\.\d{4,9}/\S+')
DOI_PREFIX = re.compile(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', re.IGNORECASE)
YEAR = re.compile(r'\b(1[5-9]\d\d|2\d\d\d)\b')
# The word of a kind of record that the words of a record can write before an ID: "claim E-1".
KIND_WORD = r'(?:\b(?i:claim|source|assumption|convention)s?\s+)?'
# What a text shows for an ID whose record has no name to show.
NO_NAME = 'another record'


@dataclass(frozen=True)
class Entry:
    """One entry of the References list. `kind` is one of `KINDS`; `label` its words ("Source", …);
    `text` the rest of its line; `url` and `link_text` its link, or None; `hover` the full words of its
    records, in plain text; `record` the IDs and names of its records, for a `data-record`
    attribute, which no visible text shows."""

    number: int
    kind: str
    label: str
    text: str
    url: str | None
    link_text: str | None
    hover: str
    record: tuple


@dataclass(frozen=True)
class References:
    """The entries, in the order of their numbers, and the marks of each place: {place: ((number,
    kind), …)}, in the order of the numbers. A place that cites no entry of the listed kinds has no
    marks."""

    entries: tuple
    marks: Mapping
    left_out: tuple = ()  # the kinds of the records cited that the list leaves out, in `KINDS` order

    def entry(self, number):
        """The entry with this number."""
        return self.entries[number - 1]


def references(cited, model, *, kinds=KINDS):
    """The References list of the places `cited` (`[(place, records), …]`, in reading order) of
    `model`, with the entries of `kinds` only."""
    listed = checked_kinds(kinds)
    reader = _Reader(model)
    drafts = {}  # key -> _Draft, in the order of first use
    cites = {}  # place -> keys, in the order of the place's records
    for place, records in cited:
        keys = cites.setdefault(place, [])
        for record in reader.records(records):
            for key in reader.keys(record, drafts):
                if key not in keys:
                    keys.append(key)
    numbers, entries = {}, []
    for key, draft in drafts.items():
        if draft.kind in listed:
            numbers[key] = len(entries) + 1
            entries.append(draft.entry(numbers[key]))
    marks = {
        place: tuple(sorted((numbers[key], drafts[key].kind) for key in keys if key in numbers))
        for place, keys in cites.items()
    }
    cited_kinds = {draft.kind for draft in drafts.values()}
    left_out = tuple(kind for kind in KINDS if kind in cited_kinds and kind not in listed)
    return References(tuple(entries), marks, left_out)


def left_out_words(kinds):
    """The line that says which kinds of record the list leaves out (`References.left_out`): "Not
    listed: sources, identities."; None when it leaves out none."""
    if not kinds:
        return None
    return 'Not listed: ' + ', '.join(LEFT_OUT_WORDS[kind] for kind in kinds) + '.'


def checked_kinds(kinds):
    """The kinds of entry that a list holds, as a set; a ValueError for a kind that is not one of
    `KINDS`, and for a list without `assumption`."""
    found = list(kinds)
    unknown = [kind for kind in found if kind not in KINDS]
    if unknown:
        raise ValueError(f'unknown kind of reference {unknown[0]!r}; the kinds are {", ".join(KINDS)}')
    if 'assumption' not in found:
        raise ValueError('the references cannot leave out the kind "assumption"')
    return frozenset(found)


# ---- the words of an entry ------------------------------------------------------------------------


def one_line(text):
    """A text on one line, with single spaces."""
    return ' '.join(str(text or '').split())


def shorten(text, room):
    """`text` on one line, cut at a space to at most `room` characters with "…" when it is longer."""
    text = one_line(text)
    if len(text) <= room:
        return text
    cut = text[: room - len(ELLIPSIS)]
    space = cut.rfind(' ')
    if space >= room // 2:
        cut = cut[:space]
    return cut.rstrip(' ,;:.-–—(') + ELLIPSIS


def first_sentence(text):
    """The first sentence of `text`, at most `SENTENCE_ROOM` characters. A stop after an abbreviation
    or an initial ("et al.", "U.S.") does not end a sentence."""
    text = one_line(text)
    for match in SENTENCE_END.finditer(text):
        word = text[: match.start()].rsplit(' ', 1)[-1].lstrip('"“‘([').lower()
        if text[match.start()] == '.' and (word in ABBREVIATIONS or INITIALS.fullmatch(word)):
            continue
        text = text[: match.end()].rstrip()
        break
    return shorten(text, SENTENCE_ROOM)


def place_in_source(locator):
    """The place in a source that a claim uses: its locator up to its first ";", shortened."""
    text = one_line(locator)
    head = text.split(';', 1)[0].strip() or text
    return shorten(head.rstrip('.'), PLACE_ROOM)


def author_of(source):
    """Who wrote a source (CSL-JSON): the first author's family name, with "et al." when there are
    more, else the publisher, else the title of its container; or None."""
    authors = [item for item in source.get('author') or () if isinstance(item, Mapping)]
    if authors:
        first = authors[0]
        family = first.get('family')
        if family:
            name = ' '.join(str(part) for part in (first.get('non-dropping-particle'), family) if part)
        else:
            name = first.get('literal') or first.get('given')
        if name:
            return one_line(name) + (' et al.' if len(authors) > 1 else '')
    for key in ('publisher', 'container-title'):
        if source.get(key):
            return one_line(source[key])
    return None


def year_of(source):
    """The year of a source (CSL-JSON `issued`), or None."""
    issued = source.get('issued')
    if not isinstance(issued, Mapping):
        return None
    parts = issued.get('date-parts')
    if parts and parts[0] and str(parts[0][0]).lstrip('-').isdigit():
        return str(parts[0][0])
    for key in ('literal', 'raw'):
        found = YEAR.search(str(issued.get(key) or ''))
        if found:
            return found.group(1)
    return None


def link_of(source):
    """(url, link text) of a source: `https://doi.org/<DOI>` and `doi:<DOI>` when it has a DOI, else
    its URL and the URL's host, else (None, None). Only an `http` or `https` address is a link."""
    doi = DOI_PREFIX.sub('', one_line(source.get('DOI')))
    if DOI.fullmatch(doi):
        return 'https://doi.org/' + quote(doi, safe="/:;()[]._-~!$&'*+,=@"), f'doi:{doi}'
    for key in ('URL', 'url'):
        url = source.get(key)
        host = web_host(url)
        if host:
            return url, host.removeprefix('www.')
    return None, None


def web_host(url):
    """The host of an `http` or `https` address, or None for anything else."""
    if not isinstance(url, str) or not url or any(char.isspace() or ord(char) < 32 for char in url):
        return None
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return None
    return host if parts.scheme in ('http', 'https') and host else None


def plain(*texts):
    """Texts on their own lines, each on one line; an empty one is left out."""
    return '\n'.join(one_line(text) for text in texts if one_line(text))


# ---- the records --------------------------------------------------------------------------------


class _Draft:
    """An entry before its number: what its records give so far. A source's draft holds the words of
    the source (`head`: who, the year and the title) and adds the claims that the places cite."""

    def __init__(self, kind, label, text, hover, *, head=None, link=(None, None)):
        self.kind, self.label, self.text, self.hover, self.head = kind, label, text, hover, head
        self.url, self.link_text = link
        self.places, self.claims, self.ids = [], [], []

    def note(self, *ids):
        for name in ids:
            if name and name not in self.ids:
                self.ids.append(name)

    def cite(self, claim_id, place, about):
        """Add a claim of this entry's source: its ID, its place in the source and its hover line."""
        if claim_id in self.claims:
            return
        self.note(claim_id)
        self.claims.append(claim_id)
        self.hover = plain(self.hover, about)
        if place not in self.places:
            self.places.append(place)

    def entry(self, number):
        text = f'{self.head} — {"; ".join(self.places)}' if self.places else (self.head or self.text)
        return Entry(
            number, self.kind, self.label, text, self.url, self.link_text, self.hover, tuple(self.ids)
        )


class _Reader:
    """The records of a model and of its library, by ID, and the words that an entry shows of them."""

    def __init__(self, model):
        library = model.library

        def by_id(collection):
            return {item['id']: item for item in library.get(collection) or ()}

        self.sources, self.claims = by_id('sources'), by_id('claims')
        self.assumptions, self.conventions = by_id('assumptions'), by_id('conventions')
        scenario = getattr(model, 'scenario', None)
        self.named = {record.name: record.content for record in getattr(scenario, 'records', ())}
        ids = sorted(
            {item for collection in COLLECTIONS for item in by_id(collection)}, key=len, reverse=True
        )
        self.pattern = (
            re.compile(KIND_WORD + r'(?<![\w-])(' + '|'.join(map(re.escape, ids)) + r')(?![\w-])')
            if ids
            else None
        )
        self.names = {}

    # ---- words

    def words(self, text):
        """A text of a record on one line, each ID of the library in it written as the name of its
        record (`name`)."""
        text = one_line(text)
        if self.pattern is None:
            return text
        return self.pattern.sub(lambda found: self.name(found.group(1)), text)

    def name(self, identifier):
        """The name that a text shows for a record of the library: who wrote a source, and the year,
        for a source and for a claim of it; the title of an assumption or a convention, in quotes."""
        if identifier not in self.names:
            name = None
            claim = self.claims.get(identifier)
            source = self.sources.get(claim['source'] if claim else identifier)
            if source is not None:
                who, year = author_of(source), year_of(source)
                name = ' '.join(
                    part for part in (who or f'“{shorten(source.get("title"), TITLE_ROOM)}”', year) if part
                )
            for found in (self.assumptions.get(identifier), self.conventions.get(identifier)):
                if found is not None:
                    name = f'“{shorten(found.get("title") or first_sentence(found.get("statement")), TITLE_ROOM)}”'
            # A name never shows an ID, not even one that a title writes.
            self.names[identifier] = self.pattern.sub(NO_NAME, one_line(name)) if name else NO_NAME
        return self.names[identifier]

    # ---- records

    def records(self, records):
        """The records of a basis: one record, a list of them, or None. A name, as the notes write a
        record, is that named record. A range note gives the reasons for a range: it is no record."""
        items = records if isinstance(records, (list, tuple)) else () if records is None else (records,)
        for item in items:
            record = item
            if isinstance(item, str):
                found = self.named.get(item)
                if found is None:
                    raise ValueError(f'no record is named {item!r}')
                record = {**found, 'name': item}
            if not isinstance(record, Mapping) or 'kind' not in record:
                continue
            if record['kind'] not in RECORD_KINDS:
                raise ValueError(f'unknown kind of record {record["kind"]!r}')
            yield record

    def keys(self, record, drafts):
        """The keys of the entries that a record cites, in order, each draft made or added to."""
        kind = record['kind']
        explanation = one_line(record.get('explanation'))
        name = record.get('name')
        out = []
        if kind in SOURCED:
            for link in record.get('links') or ():
                out.append(self.source_key(kind, link.get('claim'), drafts))
        elif kind == 'identity':
            key = ('identity', None, explanation)
            if key not in drafts:
                drafts[key] = self.own_draft('identity', explanation)
            drafts[key].note(name)
            out.append(key)
        elif kind == 'convention':
            out.append(self.named_key('convention', record.get('convention'), explanation, name, drafts))
        if record.get('assumption') is not None or kind == 'assumption':
            out.append(self.named_key('assumption', record.get('assumption'), explanation, name, drafts))
        return out

    def source_key(self, kind, claim_id, drafts):
        """The key of the entry of the source of a claim, cited as `kind`, with the claim added."""
        claim = self.claims.get(claim_id)
        if claim is None:
            raise ValueError(f'the library has no claim {claim_id!r}')
        key = ('source', kind, claim['source'])
        if key not in drafts:
            source = self.sources.get(claim['source'])
            if source is None:
                raise ValueError(f'the library has no source {claim["source"]!r}')
            who, year = self.words(author_of(source)), year_of(source)
            title = shorten(self.words(source.get('title')), TITLE_ROOM).rstrip(' .')
            if who:
                head = f'{who} ({year}). {title}' if year else f'{who}. {title}'
            else:
                head = f'{title} ({year})' if year else title
            drafts[key] = _Draft(kind, KIND_WORDS[kind], '', '', head=head.strip(' .'), link=link_of(source))
            drafts[key].note(claim['source'])
        locator = self.words(claim['locator'])
        about = f'{locator.rstrip(".")}: {self.words(claim["shows"])} Limits: {self.words(claim["limits"])}'
        drafts[key].cite(claim['id'], place_in_source(locator), about)
        return key

    def own_draft(self, kind, explanation):
        """The draft of a record without an ID: its explanation."""
        words = self.words(explanation)
        return _Draft(kind, KIND_WORDS[kind], first_sentence(words), plain(words))

    def named_key(self, kind, identifier, explanation, name, drafts):
        """The key of the entry of the assumption or the convention `identifier` of the library, or of
        the record itself when it names none that the library has."""
        found = (self.assumptions if kind == 'assumption' else self.conventions).get(identifier)
        if kind == 'convention' and found is None:
            identifier = None
        key = (kind, identifier) if identifier is not None else (kind, None, explanation)
        if key not in drafts:
            if found is None:
                drafts[key] = self.own_draft(kind, explanation)
            else:
                status = (found.get('review') or {}).get('status')
                title = self.words(found.get('title'))
                statement = self.words(found.get('statement'))
                drafts[key] = _Draft(
                    kind,
                    REVIEW_WORDS.get(status, KIND_WORDS[kind]) if kind == 'assumption' else KIND_WORDS[kind],
                    shorten(title, SENTENCE_ROOM) if title else first_sentence(statement),
                    plain(statement, self.words(found.get('rationale'))),
                )
            drafts[key].note(identifier)
        if found is None:
            drafts[key].note(name)
        return key


__all__ = [
    'COLOURS',
    'COLOUR_KIND',
    'KINDS',
    'KIND_WORDS',
    'REVIEW_WORDS',
    'Entry',
    'References',
    'checked_kinds',
    'first_sentence',
    'link_of',
    'references',
    'shorten',
]
