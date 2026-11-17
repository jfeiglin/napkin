"""The library's links from an assumption to a claim keep their relation, and the briefs mark the
claims that only limit or contradict an assumption."""

import json

from napkin.schema import FOLDER as SCHEMAS
from tools.publish.briefs import EVIDENCE_MARKS


def test_every_library_relation_that_is_not_support_has_a_mark():
    relations = json.loads((SCHEMAS / 'library.schema.json').read_text(encoding='utf-8'))['$defs']['relation']
    marked = {relation for relation in relations['enum'] if relation in EVIDENCE_MARKS}
    assert marked == {'bounds', 'context_limitations', 'contradicts'}
    assert set(EVIDENCE_MARKS) <= set(relations['enum'])
