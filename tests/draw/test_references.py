"""The References list of a picture (docs/draw.md, D-55): its entries, their kinds and numbers, and
the marks of the cited places (`napkin/draw/references.py`).

The synthetic model cites a test library of its own, with records of every kind: sources with and
without a DOI, an author or a link, claims, assumptions of each review status, with and without a
title, and conventions. Each input of the model rests on other records, so each expectation follows
from the records that the test reads back from the model and the library. The IDs and the names of
the records are distinctive, so that a search of the visible text finds any of them. The catalogue
test builds the list of the inputs of each scenario and checks the same properties.
"""

from __future__ import annotations

import functools
import re
from urllib.parse import unquote, urlsplit

import pytest

from napkin.draw.references import (
    COLOUR_KIND,
    COLOURS,
    KIND_WORDS,
    KINDS,
    PLACE_ROOM,
    REVIEW_WORDS,
    first_sentence,
    link_of,
    references,
    shorten,
)
from napkin.model.ir import thaw
from tests.build import block, compiled, document, entity, fixture_claim, in_place, library, parameter, quote
from tests.helpers import SCENARIO_IDS, catalogue_model

SOURCE_KINDS = ('source', 'source_transfer')
VISIBLE = ('label', 'text', 'link_text', 'hover')

# ---- the test library and the model ---------------------------------------------------------------


def source(identifier, title, **fields):
    return {
        'id': identifier,
        'title': title,
        **fields,
        'custom': {
            'verification': {
                'status': 'unverified',
                'date': '2026-11-11',
                'method': 'access_attempt',
                'notes': 'Synthetic.',
            }
        },
    }


def claim(identifier, source_id, locator, shows, limits):
    return fixture_claim(identifier, source=source_id, locator=locator, shows=shows, limits=limits)


def assumption(identifier, statement, rationale, status='unreviewed', title=None):
    return {
        'id': identifier,
        **({'title': title} if title else {}),
        'statement': statement,
        'rationale': rationale,
        'review': {'status': status},
    }


def own_library(statuses=()):
    """The test library; `statuses` gives other review statuses: ((assumption ID, status), …)."""
    lib = library()
    lib['sources'] = [
        source(
            'SRC-MANY-AUTHORS',
            'How long the repairs of a water plant take after an incident of its control system',
            author=[{'family': 'Abbot', 'given': 'Ann'}, {'family': 'Brook', 'given': 'Ben'}],
            issued={'date-parts': [[2019, 4]]},
            DOI='10.5555/ref.one',
            URL='https://example.org/one',
        ),
        source(
            'SRC-PUBLISHER',
            'Guide to emergency water',
            publisher='Water Agency',
            issued={'date-parts': [[2021]]},
            URL='https://www.example.org/guide',
        ),
        source('SRC-CONTAINER', 'Notes on supply', **{'container-title': 'Journal of Supply'}),
        source(
            'SRC-TRANSFER',
            'Pumps in another city',
            author=[{'literal': 'City Utility Office'}],
            issued={'date-parts': [[2018]]},
            URL='https://example.com/pumps',
        ),
        source('SRC-INFORMS', 'A report that informs the choice', URL='https://example.com/informs'),
        source('SRC-HIDDEN', 'A source of a part that the picture leaves out', URL='https://example.com/h'),
        source('SRC-NO-LINK', 'An archive without an address', author=[{'family': 'Cole'}]),
    ]
    lib['sources'][2]['url'] = 'http://example.net/notes'
    lib['claims'] = [
        claim(
            'CLM-MANY-TABLE',
            'SRC-MANY-AUTHORS',
            'Table 2; rows 3 to 5',
            'Repairs take two days.',
            'One plant.',
        ),
        claim(
            'CLM-MANY-TEXT',
            'SRC-MANY-AUTHORS',
            'Section 4.1, the second paragraph of the results of the field trial',
            'Crews work in shifts.',
            'A small crew.',
        ),
        claim('CLM-PUBLISHER', 'SRC-PUBLISHER', 'p. 7', 'Each person needs water each day.', 'A guide.'),
        claim('CLM-CONTAINER', 'SRC-CONTAINER', 'Figure 3', 'Supply falls in the summer.', 'One region.'),
        claim(
            'CLM-TRANSFER', 'SRC-TRANSFER', 'Appendix B', 'A pump moves water at a known rate.', 'Elsewhere.'
        ),
        claim('CLM-INFORMS', 'SRC-INFORMS', 'Chapter 1', 'Crews keep a steady pace.', 'A survey.'),
        claim('CLM-HIDDEN', 'SRC-HIDDEN', 'p. 9', 'A part that no place shows.', 'None.'),
        # Words of a record that name other records by their IDs.
        claim(
            'CLM-NO-LINK',
            'SRC-NO-LINK',
            'Box 1',
            'Old records of the plant.',
            'Paper only (claim CLM-PUBLISHER gives the counts).',
        ),
    ]
    lib['assumptions'] = [
        assumption(
            'ASM-TEMPO',
            'The crews work at a steady pace. They never stop for the night.',
            'Reports of past repairs show steady work.',
            title='How fast the crews work',
        ),
        assumption(
            'ASM-TRANSFER-FIT',
            'The pumps of the other city work as the pumps of this plant do.',
            'The two plants use pumps of one design.',
            title='The pumps of another city fit this plant',
        ),
        assumption(
            'ASM-UNTITLED',
            'The plant has one spare pump. A second spare comes from the supplier.',
            'The plant keeps a list of its parts. ASM-TEMPO gives the pace of the crews.',
            status='replaced',
        ),
    ]
    lib['conventions'] = [
        {'id': 'CNV-TITLED', 'title': 'Severity levels', 'statement': 'Harm has four levels of severity.'},
        {'id': 'CNV-UNTITLED', 'statement': 'Costs use the prices of one year. The prices change yearly.'},
    ]
    changed = dict(statuses)
    for item in lib['assumptions']:
        item['review']['status'] = changed.get(item['id'], item['review']['status'])
    return lib


def record(name, kind, explanation, *claims, identifier=None):
    """A named record for the end of the file, with the ID that it names and its claims."""
    head = f'record {name}: {kind}' + (f' {identifier}' if identifier else '') + f' {quote(explanation)}'
    return block(head, block('claims:', *claims) if claims else None)


# The records of the model, cited by name.
RECORDS = (
    record('rec_direct_first', 'source', 'The first value.', 'CLM-MANY-TABLE', 'CLM-PUBLISHER'),
    record(
        'rec_direct_second', 'source', 'The second value.', 'CLM-MANY-TEXT', 'CLM-CONTAINER', 'CLM-NO-LINK'
    ),
    record('rec_assumed', 'assumption', 'The pace of the crews.', 'CLM-INFORMS', identifier='ASM-TEMPO'),
    record(
        'rec_transfer',
        'source_transfer',
        'Pumps of another city.',
        'CLM-TRANSFER',
        identifier='ASM-TRANSFER-FIT',
    ),
    record('rec_counted', 'identity', 'Each pump is counted once. No pump is lost.', 'CLM-INFORMS'),
    record('rec_rule', 'convention', 'The levels of harm.', identifier='CNV-TITLED'),
    record('rec_rule_plain', 'convention', 'The prices.', identifier='CNV-UNTITLED'),
    record('rec_replaced', 'assumption', 'The spare pumps.', identifier='ASM-UNTITLED'),
    record('rec_transfer_bare', 'source_transfer', 'Repairs elsewhere, applied here.', 'CLM-MANY-TABLE'),
    record('rec_hidden', 'source', 'A part that the picture leaves out.', 'CLM-HIDDEN'),
)
# Each input of the model: its name, the named records that it cites, and a record written in place
# under it, without an ID.
INPUTS = (
    ('first', '@rec_direct_first', None),
    ('second', '@rec_direct_second', None),
    ('third', '@rec_assumed', None),
    ('fourth', '@rec_transfer', None),
    ('fifth', '@rec_counted', None),
    ('sixth', '@rec_rule', None),
    ('seventh', None, in_place('assumption', 'The scenario assumes four crews. No report gives the number.')),
    ('eighth', '@rec_rule_plain @rec_assumed', None),
    ('ninth', '@rec_replaced @rec_counted', None),
    ('tenth', '@rec_transfer_bare', None),
    ('eleventh', None, in_place('convention', 'Each crew hour costs the price of its year.')),
    ('unshown', '@rec_hidden', None),
)
# The input that the picture leaves out.
UNSHOWN = 'unshown'


def text():
    """The model: one thing whose inputs rest on the records above."""
    values = [
        parameter(name, 2, 'h', 1, 4, doc=f'Input {k}', records=cited, under=(placed,) if placed else ())
        for k, (name, cited, placed) in enumerate(INPUTS)
    ]
    return document('References fixture', entity('plant', *values, doc='A plant.'), records=RECORDS)


@functools.cache
def model(statuses=()):
    return compiled(text(), own_library(statuses))


def places(found, *, every=False):
    """The places of the inputs of a model, in reading order: (thing, input) with the input's
    records. The input `unshown` is left out unless `every`."""
    return [
        ((thing.name, value.name), value.records)
        for thing in found.scenario.entities
        for value in thing.values
        if value.kind == 'input' and (every or value.name != UNSHOWN)
    ]


def by_id(found, collection):
    return {item['id']: item for item in thaw(found.library).get(collection, [])}


def marked(refs, place):
    """The entries that a place cites."""
    return [refs.entry(number) for number, _ in refs.marks[place]]


# ---- the properties of every list ----------------------------------------------------------------


def records_of(records):
    """The records of a basis, plain: one record, a list of them, or None; without range notes."""
    found = thaw(records)
    items = found if isinstance(found, list) else [] if found is None else [found]
    return [item for item in items if isinstance(item, dict) and 'kind' in item]


def unnamed_records(cited):
    """{kind: the explanations of the records without an ID of the library that the places cite}:
    the identities, and the assumptions and conventions that name none."""
    out = {}
    for _, records in cited:
        for item in records_of(records):
            if item['kind'] == 'identity' or (
                item['kind'] in ('assumption', 'convention') and not item.get(item['kind'])
            ):
                out.setdefault(item['kind'], set()).add(' '.join(item['explanation'].split()))
    return out


def expected_entries(found, cited):
    """What the records of the cited places give, read from the records and the library: (the source
    of each claim of a `source` or `source_transfer` record, by its kind, the assumption that each
    record names and the convention that each names; {kind: how many records without an ID give
    an entry of their own}). Records with one explanation share their entry."""
    claims = by_id(found, 'claims')
    named = set()
    for _, records in cited:
        for item in records_of(records):
            kind = item['kind']
            if kind in SOURCE_KINDS:
                named |= {(kind, claims[link['claim']]['source']) for link in item.get('links', [])}
            if item.get('assumption'):
                named.add(('assumption', item['assumption']))
            if item.get('convention'):
                named.add(('convention', item['convention']))
    return named, {kind: len(texts) for kind, texts in unnamed_records(cited).items()}


def given_entries(found, refs):
    """What the entries are, by the IDs of their records: the same terms as `expected_entries`."""
    known = by_id(found, 'assumptions') | by_id(found, 'conventions')
    named, unnamed = set(), {}
    for entry in refs.entries:
        if entry.kind in SOURCE_KINDS or (entry.record and entry.record[0] in known):
            named.add((entry.kind, entry.record[0]))
        else:
            unnamed[entry.kind] = unnamed.get(entry.kind, 0) + 1
    return named, unnamed


def assert_numbered(refs, cited):
    """Each mark names exactly one entry of its kind, each entry has a mark, and the numbers run
    from 1 by first use in reading order."""
    numbers = [entry.number for entry in refs.entries]
    assert numbers == list(range(1, len(numbers) + 1))
    assert list(refs.marks) == list(dict.fromkeys(place for place, _ in cited))
    first_uses = []
    for place, marks in refs.marks.items():
        assert [number for number, _ in marks] == sorted({number for number, _ in marks}), place
        for number, kind in marks:
            assert 1 <= number <= len(refs.entries) and refs.entry(number).kind == kind, (place, number)
            if number not in first_uses:
                first_uses.append(number)
    assert first_uses == numbers


def assert_words(refs):
    """Each entry starts with the words of its kind, has a text and plain one-line visible words, and
    a colour of a mark."""
    for entry in refs.entries:
        assert entry.kind in KINDS and COLOUR_KIND[entry.kind] in COLOURS
        if entry.kind == 'assumption':
            assert entry.label in REVIEW_WORDS.values()
        else:
            assert entry.label == KIND_WORDS[entry.kind]
        assert entry.text and entry.hover
        assert all('\n' not in getattr(entry, field) for field in ('label', 'text'))
        if entry.kind in SOURCE_KINDS:
            places = entry.text.rsplit(' — ', 1)[1].split('; ')
            assert len(places) == len(set(places)) and all(len(place) <= PLACE_ROOM for place in places)


def assert_links(found, refs):
    """A link goes to an http or https address: the DOI's when the source has a DOI, else the source's
    URL; an entry without one has no link text."""
    sources = by_id(found, 'sources')
    for entry in refs.entries:
        if entry.kind not in SOURCE_KINDS:
            assert entry.url is None and entry.link_text is None
            continue
        item = sources[entry.record[0]]
        url = item.get('URL') or item.get('url')
        if item.get('DOI'):
            assert unquote(entry.url) == f'https://doi.org/{item["DOI"]}'
            assert entry.link_text == f'doi:{item["DOI"]}'
        elif url:
            assert entry.url == url and entry.link_text == urlsplit(url).hostname.removeprefix('www.')
        else:
            assert entry.url is None and entry.link_text is None
        if entry.url is not None:
            assert urlsplit(entry.url).scheme in ('http', 'https') and urlsplit(entry.url).hostname


def ids_of(found):
    """Every ID of the library of a model, and the name of each named record of the model."""
    lib = thaw(found.library)
    ids = {
        item['id']
        for collection in ('sources', 'claims', 'assumptions', 'conventions')
        for item in lib.get(collection, [])
    }
    return ids | {item.name for item in found.scenario.records}


def leaks(refs, ids):
    """(entry number, field, ID) of each ID that a visible field shows, as a whole word."""
    pattern = re.compile(
        r'(?<![\w-])(' + '|'.join(map(re.escape, sorted(ids, key=len, reverse=True))) + r')(?![\w-])'
    )
    return [
        (entry.number, field, hit.group(1))
        for entry in refs.entries
        for field in VISIBLE
        for hit in pattern.finditer(getattr(entry, field) or '')
    ]


def assert_holds(found, cited, refs):
    assert_numbered(refs, cited)
    assert_words(refs)
    assert_links(found, refs)
    assert given_entries(found, refs) == expected_entries(found, cited)


def entries_of(refs, kind, source_id):
    return [entry for entry in refs.entries if entry.kind == kind and entry.record[0] == source_id]


# ---- the synthetic model -------------------------------------------------------------------------


def test_every_mark_names_one_entry_and_the_numbers_follow_first_use():
    found = model()
    cited = places(found)
    refs = references(cited, found)
    assert_holds(found, cited, refs)
    # Every record kind gives an entry, and each place cites at least one.
    assert {entry.kind for entry in refs.entries} == set(KINDS)
    assert all(refs.marks[place] for place, _ in cited)
    # The entry of a record without an ID of the library shows the record's explanation.
    known = by_id(found, 'assumptions') | by_id(found, 'conventions')
    unnamed = unnamed_records(cited)
    own = [
        entry
        for entry in refs.entries
        if entry.kind not in SOURCE_KINDS and not set(entry.record) & set(known)
    ]
    assert sorted(entry.kind for entry in own) == sorted(
        kind for kind, texts in unnamed.items() for _ in texts
    )
    assert all(entry.hover in unnamed[entry.kind] for entry in own)


def test_an_id_in_the_words_of_a_record_shows_as_the_name_of_its_record():
    """The words of a claim and of an assumption name other records by their IDs: the entries show
    the names of those records instead."""
    found = model()
    refs = references(places(found), found)
    claims, sources, assumptions = (by_id(found, kind) for kind in ('claims', 'sources', 'assumptions'))
    named = [(item, 'limits') for item in claims.values()] + [
        (item, 'rationale') for item in assumptions.values()
    ]
    hits = [
        (item, field, other)
        for item, field in named
        for other in claims | assumptions
        if other in item[field]
    ]
    assert {(item['id'], other) for item, _, other in hits} == {
        ('CLM-NO-LINK', 'CLM-PUBLISHER'),
        ('ASM-UNTITLED', 'ASM-TEMPO'),
    }
    for item, _, other in hits:
        (entry,) = [entry for entry in refs.entries if item['id'] in entry.record]
        assert other not in entry.hover
        if other in claims:
            cited = sources[claims[other]['source']]
            assert (
                cited['publisher'] in entry.hover and str(cited['issued']['date-parts'][0][0]) in entry.hover
            )
        else:
            assert assumptions[other]['title'] in entry.hover


def test_one_entry_joins_the_claims_of_one_source():
    found = model()
    refs = references(places(found), found)
    claims = by_id(found, 'claims')
    plant = found.scenario.entity('plant')
    # The places `first` and `second` cite two different claims of one source, each as a source.
    cited = {
        name: [
            claims[link['claim']] for item in records_of(plant.value(name).records) for link in item['links']
        ]
        for name in ('first', 'second')
    }
    (source_id,) = {item['source'] for item in cited['first']} & {item['source'] for item in cited['second']}
    used = [item for name in cited for item in cited[name] if item['source'] == source_id]
    assert len({item['id'] for item in used}) == 2
    (entry,) = entries_of(refs, 'source', source_id)
    assert entry in marked(refs, ('plant', 'first')) and entry in marked(refs, ('plant', 'second'))
    assert {item['id'] for item in used} <= set(entry.record)
    for item in used:
        head = item['locator'].split(';')[0].strip()
        # Each place used in the source shows, up to its first ";" and shortened.
        assert head[:12] in entry.text
        assert item['shows'] in entry.hover and item['limits'] in entry.hover
        for rest in item['locator'].split(';')[1:]:
            assert rest.strip() not in entry.text
    assert entry.text.count(' — ') == 1


def test_a_source_applied_here_has_its_own_entry():
    """A source that one place cites as a source and another applies here has an entry of each kind,
    so that neither label says more than its records."""
    found = model()
    refs = references(places(found), found)
    (direct,) = entries_of(refs, 'source', 'SRC-MANY-AUTHORS')
    (applied,) = entries_of(refs, 'source_transfer', 'SRC-MANY-AUTHORS')
    assert direct.number != applied.number and direct.label != applied.label
    assert marked(refs, ('plant', 'tenth')) == [applied]
    assert applied not in marked(refs, ('plant', 'first'))


@pytest.mark.parametrize('status', ['unreviewed', 'confirmed', 'replaced'])
def test_an_input_that_rests_on_an_assumption_has_only_its_assumption_entry(status):
    found = model((('ASM-TEMPO', status),))
    refs = references(places(found), found)
    (entry,) = marked(refs, ('plant', 'third'))
    assert entry.kind == 'assumption' and entry.record == ('ASM-TEMPO',)
    assert entry.label == REVIEW_WORDS[by_id(found, 'assumptions')['ASM-TEMPO']['review']['status']]
    # The claims of an assumption and of an identity inform the record: they give no source entry.
    informs = {by_id(found, 'claims')['CLM-INFORMS']['source']}
    assert not [item for item in refs.entries if item.kind in SOURCE_KINDS and item.record[0] in informs]
    # An assumption without an ID is not reviewed, whatever the library's other reviews say.
    (own,) = marked(refs, ('plant', 'seventh'))
    assert own.kind == 'assumption' and own.label == REVIEW_WORDS['unreviewed']


def test_the_review_status_changes_the_label():
    """Counterexample: a confirmed assumption is not "not reviewed", and a replaced one is neither."""
    labels = {}
    for status in ('unreviewed', 'confirmed', 'replaced'):
        found = model((('ASM-TEMPO', status),))
        (entry,) = marked(references(places(found), found), ('plant', 'third'))
        labels[status] = entry.label
    assert len(set(labels.values())) == 3
    assert labels['confirmed'] != REVIEW_WORDS['unreviewed']
    # The library's own status of another assumption gives its label.
    found = model()
    (entry,) = [
        e for e in marked(references(places(found), found), ('plant', 'ninth')) if e.kind == 'assumption'
    ]
    assert entry.label == REVIEW_WORDS[by_id(found, 'assumptions')[entry.record[0]]['review']['status']]


def test_a_source_transfer_cites_its_sources_and_its_assumption():
    found = model()
    (item,) = records_of(found.scenario.entity('plant').value('fourth').records)
    assert item['kind'] == 'source_transfer' and item['assumption']
    claims = by_id(found, 'claims')
    for kinds in (KINDS, ('source', 'assumption'), ('assumption',)):
        refs = references(places(found), found, kinds=kinds)
        entries = marked(refs, ('plant', 'fourth'))
        # The assumption of the transfer always shows, even when the transfers are left out.
        assert [entry.record for entry in entries if entry.kind == 'assumption'] == [(item['assumption'],)]
        sources = {entry.record[0] for entry in entries if entry.kind == 'source_transfer'}
        listed = 'source_transfer' in kinds
        assert sources == ({claims[link['claim']]['source'] for link in item['links']} if listed else set())
        assert {kind for _, kind in refs.marks[('plant', 'fourth')]} == (
            {'source_transfer', 'assumption'} if listed else {'assumption'}
        )


def test_no_visible_text_shows_an_id():
    found = model()
    refs = references(places(found, every=True), found)
    ids = ids_of(found)
    assert not leaks(refs, ids)
    # The search finds the IDs where they belong: in the records of the entries.
    assert {name for entry in refs.entries for name in entry.record} & ids


def test_links_go_to_the_doi_or_the_url():
    found = model()
    refs = references(places(found), found)
    assert_links(found, refs)
    linked = {entry.link_text.startswith('doi:') for entry in refs.entries if entry.link_text}
    # The fixture has a DOI link, a URL link and a source without a link.
    assert linked == {True, False}
    assert any(entry.kind in SOURCE_KINDS and entry.url is None for entry in refs.entries)


@pytest.mark.parametrize(
    ('fields', 'url'),
    [
        ({'DOI': '10.1234/ab#c', 'URL': 'https://example.org'}, 'https://doi.org/10.1234/ab%23c'),
        ({'DOI': 'https://doi.org/10.1234/x', 'URL': 'https://example.org'}, 'https://doi.org/10.1234/x'),
        ({'DOI': 'pending', 'URL': 'https://example.org/a'}, 'https://example.org/a'),
        ({'url': 'http://example.org/b'}, 'http://example.org/b'),
        ({'URL': 'ftp://example.org/c'}, None),
        ({'URL': 'javascript:alert(1)'}, None),
        ({'URL': 'https://'}, None),
        ({'URL': 'https://example.org/a b'}, None),
        ({}, None),
    ],
)
def test_a_link_is_an_http_address_only(fields, url):
    found, text = link_of(fields)
    assert found == url and (text is None) == (url is None)
    if url is not None:
        assert urlsplit(found).scheme in ('http', 'https')


def test_entries_are_the_records_of_the_cited_places_only():
    found = model()
    shown = places(found)
    every = places(found, every=True)
    hidden = [place for place in every if place not in shown]
    assert hidden
    refs = references(shown, found)
    hidden_sources = expected_entries(found, hidden)[0] - expected_entries(found, shown)[0]
    assert hidden_sources
    assert not hidden_sources & given_entries(found, refs)[0]
    titles = [by_id(found, 'sources')[source_id]['title'] for _, source_id in hidden_sources]
    assert not [entry for entry in refs.entries for title in titles if title[:20] in entry.text + entry.hover]
    # Counterexample: shown, the left-out input brings its source in.
    assert hidden_sources <= given_entries(found, references(every, found))[0]


def test_kinds_leave_entries_out_but_never_the_assumptions():
    found = model()
    cited = places(found)
    whole = references(cited, found)
    for kinds in (('assumption',), ('source', 'assumption'), ('identity', 'convention', 'assumption')):
        refs = references(cited, found, kinds=kinds)
        assert_numbered(refs, cited)
        assert {entry.kind for entry in refs.entries} == set(kinds)
        kept = [(entry.kind, entry.text) for entry in whole.entries if entry.kind in kinds]
        assert [(entry.kind, entry.text) for entry in refs.entries] == kept
    with pytest.raises(ValueError, match='assumption'):
        references(cited, found, kinds=('source', 'source_transfer', 'identity', 'convention'))
    with pytest.raises(ValueError, match='kind'):
        references(cited, found, kinds=('assumption', 'sources'))


def test_the_list_is_the_same_for_the_same_input():
    found = model()
    cited = places(found)
    refs = references(cited, found)
    assert references(cited, found) == refs
    again = compiled(text(), own_library())
    assert references(places(again), again) == refs
    # Another reading order numbers the same entries by their first use there.
    backwards = references(cited[::-1], found)
    assert_holds(found, cited[::-1], backwards)
    assert {(e.kind, frozenset(e.record)) for e in backwards.entries} == {
        (e.kind, frozenset(e.record)) for e in refs.entries
    }


def test_a_place_without_records_has_no_marks_and_a_name_is_its_record():
    found = model()
    refs = references([('empty', None), ('named', ('rec_assumed',)), ('note', {'status': 'chosen'})], found)
    assert refs.marks['empty'] == () and refs.marks['note'] == ()
    (entry,) = marked(refs, 'named')
    assert entry.record == ('ASM-TEMPO',)


# ---- the words -----------------------------------------------------------------------------------


@pytest.mark.parametrize('room', [8, 20, 40, 60])
def test_a_shortened_text_fits_its_room(room):
    words = 'one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen'
    short = shorten(words, room)
    assert len(short) <= room and short.endswith('…')
    assert words.startswith(short[:-1].rstrip())
    fits = words[:room].strip()
    assert shorten(fits, room) == fits


@pytest.mark.parametrize(
    ('written', 'first'),
    [
        ('One sentence. Another one.', 'One sentence.'),
        ('Data of Smith et al. 2020 show it. Then more.', 'Data of Smith et al. 2020 show it.'),
        ('The U.S. plants. Then more.', 'The U.S. plants.'),
        ('A rate of 3.5 a day. Then more.', 'A rate of 3.5 a day.'),
        ('See Table 2 (p. 5). Then more.', 'See Table 2 (p. 5).'),
        ('No stop at the end', 'No stop at the end'),
    ],
)
def test_the_first_sentence_ends_at_its_stop(written, first):
    assert first_sentence(written) == first


# ---- every scenario ------------------------------------------------------------------------------


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_the_references_of_every_scenario_hold_their_properties(scenario_id):
    """The References list of all the inputs of a scenario, as if the picture showed each one."""
    found = catalogue_model(scenario_id)
    cited = places(found, every=True)
    refs = references(cited, found)
    assert refs.entries
    assert_holds(found, cited, refs)
    assert not leaks(refs, ids_of(found) - {item.name for item in found.scenario.records})
    assert references(cited, found) == refs
