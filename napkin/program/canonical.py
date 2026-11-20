"""Canonical bytes of a program and of a configuration, for the key of a stored run, and of any value
that they are made of (`value_bytes`), for the hash of a model.

Two builds of one model give equal bytes; a change of a number, a unit, a name or the structure
gives different bytes. The encoding is tagged and length-prefixed, so two different values never
share bytes: a record by its class's name and its fields in order, a tuple by its length, a number
by its type (an int, a float bit for bit, a fraction as its two whole numbers), a text by its
length and its UTF-8, and a node of an expression by its kind and its parts. Nothing depends on the
identity of an object, the order of a dictionary or the process. A value of any other type is a
TypeError, so nothing is keyed by its `repr`.

The run store combines the configuration's bytes with the canonical bytes of the request. A model's
identity combines them with its horizon (`model.identity`).

`decode` reads the bytes back: it gives a value equal to the one that was encoded, whose nodes are the
nodes of `napkin/core/expr` themselves (each is made once), so a program saved by one process and
loaded by another has the same bytes and runs the same (`artifact.py` keeps a program in a file).
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


# ---- reading the bytes back ----------------------------------------------------------------------

# The maker of each kind of node by its tag: each takes the fields of its node in their order.
_MAKERS = {
    b'r': nodes.ref,
    b'u': nodes.unary,
    b'b': nodes.binary,
    b'p': nodes.compare,
    b'o': nodes.boolean,
    b'i': nodes.if_else,
    b'l': nodes.call,
}
_FIELDS = {tag: len(names) for _, tag, names in _NODES}


class Malformed(ValueError):
    """Bytes that are no canonical value: where they stop being one, and why."""


def decode(data, records):
    """The value of canonical bytes: equal to the value that `value_bytes` encoded, with the nodes of
    `napkin/core/expr` themselves. `records` maps the qualified name of each class of record that
    the bytes may hold to the class, and a record must have the fields of its class, in their order.
    Raises `Malformed` with the byte at which the bytes stop being a value."""
    reader = _Reader(bytes(data), records)
    value = reader.value()
    if reader.at != len(reader.data):
        reader.fail('the value ends before the bytes do')
    return value


class _Reader:
    """A cursor over canonical bytes."""

    def __init__(self, data, records):
        self.data, self.records, self.at = data, records, 0

    def fail(self, message):
        raise Malformed(f'byte {self.at}: {message}')

    def take(self, size):
        end = self.at + size
        if end > len(self.data):
            self.fail('the bytes end inside a value')
        found, self.at = self.data[self.at : end], end
        return found

    def until(self, stop):
        """The bytes up to `stop`, which is passed."""
        end = self.data.find(stop, self.at)
        if end < 0:
            self.fail(f'no {stop.decode()} ends the value')
        found, self.at = self.data[self.at : end], end + 1
        return found

    def size(self):
        written = self.until(b':')
        if not written.isdigit():
            self.fail(f'a size is a whole number, not {written!r}')
        return int(written)

    def expect(self, mark):
        if self.take(1) != mark:
            self.at -= 1
            self.fail(f'{mark.decode()} was expected')

    def number(self, read):
        written = self.until(b';')
        try:
            return read(written.decode('ascii'))
        except (ValueError, ZeroDivisionError):
            self.fail(f'no number is written {written!r}')

    def value(self):
        tag = self.take(1)
        if tag == b'N':
            return None
        if tag in (b'T', b'F'):
            return tag == b'T'
        if tag == b'i':
            return self.number(int)
        if tag == b'f':
            return self.number(float.fromhex)
        if tag == b'q':
            return self.number(lambda text: Fraction(*map(int, text.split('/'))))
        if tag == b's':
            return self.take(self.size()).decode('utf-8', 'surrogatepass')
        if tag == b'(':
            items = tuple(self.value() for _ in range(self.size()))
            self.expect(b')')
            return items
        if tag == b'E':
            return self.node()
        if tag == b'R':
            return self.record()
        self.at -= 1
        self.fail(f'no value starts with {tag!r}')

    def node(self):
        tag = self.take(1)
        if tag == b'c':
            return nodes.const(self.value())
        if tag not in _MAKERS:
            self.at -= 1
            self.fail(f'no node of a program has the tag {tag!r}')
        return _MAKERS[tag](*(self.value() for _ in range(_FIELDS[tag])))

    def record(self):
        name = self.take(self.size()).decode('utf-8')
        kind = self.records.get(name)
        if kind is None:
            self.fail(f'no record of this napkin is named {name}')
        self.expect(b'{')
        values = {}
        for item in fields(kind):
            if self.data[self.at : self.at + 1] == b'}':
                self.fail(f'the record {name} ends before its field {item.name}')
            found = self.value()
            if found != item.name:
                self.fail(f'the record {name} has the field {item.name} here, not {found!r}')
            values[item.name] = self.value()
        if self.data[self.at : self.at + 1] != b'}':
            self.fail(f'the record {name} has more fields than this napkin gives it')
        self.at += 1
        try:
            return kind(**values)
        except (TypeError, ValueError) as error:
            self.fail(f'the record {name} cannot be made: {error}')
