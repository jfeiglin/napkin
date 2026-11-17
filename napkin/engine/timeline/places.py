"""The places of the graph of influence that are no names of a run (`influence.py`): a rule and an
output. A run names them in its notes (`Run.note`), and the graph has them as its places."""

from __future__ import annotations


def rule_place(index):
    """The place of the rule with this index in the plan."""
    return ('rule', index)


def output_place(name):
    """The place of the output with this name."""
    return ('output', name)
