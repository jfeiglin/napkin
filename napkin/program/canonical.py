"""Canonical bytes of a program and of a configuration, for the key of a stored run, and of any value
that they are made of (`value_bytes`), for the hash of a model.

Two builds of one model give equal bytes; a change of a number, a unit, a name or the structure
gives different bytes. The encoding is tagged and length-prefixed, so two different values never
share bytes: a record by its class's name and its fields in order, a tuple by its length, a number
by its type (an int, a float bit for bit, a fraction as its two whole numbers), a text by its
length and its UTF-8, and a node of an expression by its kind and its parts. Nothing depends on the
identity of an object, the order of a dictionary or the process. A value of any other type is a
TypeError, so nothing is keyed by its `repr`.

A configuration's bytes leave out its request (what to record, and the horizon): a stored run serves
any request that its manifest covers (R-A4a-08). A median run has no seed (`config.Configuration`),
so two median runs of one setup have one key.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from fractions import Fraction

from ..core import expr as nodes

# The tag of each kind of node, and the fields that it is made of, in order.
_NODES = (
    (nodes.Ref, b'r', ('name',)),
    (nodes.Unary, b'u', ('op', 'operand')),
    (nodes.Binary, b'b', ('op', 'left', 'right')),
    (nodes.Compare, b'p', ('ops', 'operands')),
    (nodes.BoolOp, b'o', ('op', 'values')),
    (nodes.IfElse, b'i', ('test', 'body', 'orelse')),
    (nodes.Call, b'l', ('function', 'args')),
)


def _node(node, out, memo):
    """A node of an expression; a node that appears again is encoded once and copied."""
    found = memo.get(id(node))
    if found is not None:
        out.append(found)
        return
    own = []
    if isinstance(node, nodes.Const):
        own.append(b'Ec')
        _encode(node.value, own, memo)
    else:
        for kind, tag, names in _NODES:
            if isinstance(node, kind):
                own.append(b'E' + tag)
                for name in names:
                    _encode(getattr(node, name), own, memo)
                break
        else:
            raise TypeError(f'no node of a program: {type(node).__name__}')
    written = b''.join(own)
    # The node lives while the program holds it, so its id stays its own during the encoding.
    memo[id(node)] = written
    out.append(written)


def _encode(value, out, memo):
    kind = type(value)
    if value is None:
        out.append(b'N')
    elif kind is bool:
        out.append(b'T' if value else b'F')
    elif kind is int:
        out.append(b'i%d;' % value)
    elif kind is float:
        out.append(b'f' + value.hex().encode() + b';')
    elif kind is Fraction:
        out.append(b'q%d/%d;' % (value.numerator, value.denominator))
    elif kind is str:
        data = value.encode('utf-8', 'surrogatepass')
        out.append(b's%d:' % len(data))
        out.append(data)
    elif kind is tuple:
        out.append(b'(%d:' % len(value))
        for item in value:
            _encode(item, out, memo)
        out.append(b')')
    elif isinstance(value, nodes.Node):
        _node(value, out, memo)
    elif is_dataclass(value) and not isinstance(value, type):
        name = kind.__qualname__.encode()
        out.append(b'R%d:' % len(name) + name + b'{')
        for item in fields(value):
            _encode(item.name, out, memo)
            _encode(getattr(value, item.name), out, memo)
        out.append(b'}')
    else:
        raise TypeError(f'no canonical bytes of a {kind.__qualname__}')


def _bytes(value):
    out = []
    _encode(value, out, {})
    return b''.join(out)


def program_bytes(program):
    """The canonical bytes of a program."""
    return _bytes(program)


def value_bytes(value):
    """The canonical bytes of any value that programs and configurations are made of (a record, a
    tuple, a number, a text, a node), such as the options of a model, which its hash covers."""
    return _bytes(value)


def configuration_bytes(configuration):
    """The canonical bytes of a configuration, without its request."""
    out, memo = [b'Configuration{'], {}
    for item in fields(configuration):
        if item.name != 'request':
            _encode(item.name, out, memo)
            _encode(getattr(configuration, item.name), out, memo)
    out.append(b'}')
    return b''.join(out)
