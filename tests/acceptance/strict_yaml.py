"""The strict YAML loader of the frozen expectations of the acceptance tests (`*.expect.yaml`): a
subset of YAML with one JSON-equivalent meaning.

The loader rejects duplicate keys, anchors and aliases, explicit tags, non-finite numbers, dates,
and every YAML 1.1 implicit type other than JSON's: `yes`, `no`, `on`, `off`, `1:20` and `0x1F`
stay strings. It returns the data and the line of every mapping key and list item, so a failure can
name the line it is about.
"""

from __future__ import annotations

import json
import math
import re
from typing import ClassVar

import yaml

from napkin.model.load import SourceError

_JSON_SCALARS = [
    ('tag:yaml.org,2002:bool', re.compile(r'^(?:true|false)$'), list('tf')),
    ('tag:yaml.org,2002:null', re.compile(r'^(?:null)$'), ['n']),
    ('tag:yaml.org,2002:int', re.compile(r'^-?(?:0|[1-9][0-9]*)$'), list('-0123456789')),
    (
        'tag:yaml.org,2002:float',
        re.compile(r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?$'),
        list('-0123456789'),
    ),
]


# libyaml's parser when PyYAML has it (the pinned wheels do); the checks below stay in Python.
_Parser = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)


class _Loader(_Parser):
    yaml_implicit_resolvers: ClassVar[dict] = {}

    def construct_mapping(self, node, deep=False):
        keys = set()
        for key_node, _ in node.value:
            if not isinstance(key_node, yaml.ScalarNode) or key_node.tag != 'tag:yaml.org,2002:str':
                raise SourceError(self.name, key_node.start_mark.line + 1, 'mapping keys must be text')
            if key_node.value in keys:
                raise SourceError(
                    self.name, key_node.start_mark.line + 1, f'duplicate key {key_node.value!r}'
                )
            keys.add(key_node.value)
        return super().construct_mapping(node, deep=True)

    def construct_yaml_float(self, node):
        value = float(node.value)
        if not math.isfinite(value):
            raise SourceError(self.name, node.start_mark.line + 1, 'numbers must be finite')
        return value


for _tag, _pattern, _first in _JSON_SCALARS:
    _Loader.add_implicit_resolver(_tag, _pattern, _first)
_Loader.add_constructor('tag:yaml.org,2002:float', _Loader.construct_yaml_float)


def _lines(node, path=(), out=None):
    """The line of each mapping value and list item, by its key path."""
    out = {} if out is None else out
    out[path] = node.start_mark.line + 1
    if isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            child = (*path, key.value)
            out[child] = key.start_mark.line + 1
            _lines(value, child, out)
            out[child] = key.start_mark.line + 1
    elif isinstance(node, yaml.SequenceNode):
        for i, value in enumerate(node.value):
            _lines(value, (*path, i), out)
    return out


def _plain(text, name):
    """Reject anchors, aliases and explicit tags: each value is written once, as it reads."""
    for event in yaml.parse(text, Loader=_Parser):
        if isinstance(event, yaml.AliasEvent) or getattr(event, 'anchor', None):
            raise SourceError(name, event.start_mark.line + 1, 'anchors and aliases are not allowed')
        tag = getattr(event, 'tag', None)
        if tag not in (None, '!') and not (isinstance(event, yaml.ScalarEvent) and event.implicit[0]):
            raise SourceError(name, event.start_mark.line + 1, f'explicit tag {tag} is not allowed')


def parse(text, name='<source>'):
    """Data and line map of one source text."""
    loader = _Loader(text)
    loader.name = name
    try:
        _plain(text, name)
        node = loader.get_single_node()
        if node is None:
            raise SourceError(name, 0, 'the file is empty')
        data = loader.construct_document(node)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        raise SourceError(name, mark.line + 1 if mark else 0, exc.problem or str(exc)) from exc
    finally:
        loader.dispose()
    # The data must survive a JSON round trip unchanged: one meaning, no Python-only values.
    if json.loads(json.dumps(data, allow_nan=False)) != data:
        raise SourceError(name, 0, 'the file holds values that have no JSON form')
    return data, _lines(node)
