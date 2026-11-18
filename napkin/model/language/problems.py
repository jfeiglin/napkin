"""Diagnostics of the front end: each has a code and the place in the file that it is about.

The lexer and the parser raise `SyntaxProblem` at the first line that the language does not read;
the declared model and the lowering collect `Problem`s and raise `LanguageError` with all of them. A
code names the rule (`unit`, `unknown_name`, `later_slice`, ...), so a test and a caller can tell two
refusals apart without reading their messages.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Problem:
    """One diagnostic: its code, its message, its line (1 is the first line of the file, 0 none), its
    column (from 1, 0 none) and its file ('' for a text with no file)."""

    code: str
    message: str
    line: int = 0
    column: int = 0
    file: str = ''

    def __str__(self):
        where = ':'.join(str(part) for part in (self.file, self.line or '', self.column or '') if part != '')
        return f'{where}: {self.message} [{self.code}]' if where else f'{self.message} [{self.code}]'


class SyntaxProblem(Exception):
    """A line that is not written as the language writes it: a `Problem` with the code `syntax` or a
    more precise one."""

    def __init__(self, message, line, column=0, code='syntax'):
        self.problem = Problem(code, message, line, column or 0)
        super().__init__(str(self.problem))

    @property
    def code(self):
        return self.problem.code

    @property
    def line(self):
        return self.problem.line


class LanguageError(ValueError):
    """A model text that the front end refuses, with every `Problem` that it found."""

    def __init__(self, problems, file=''):
        self.problems = tuple(
            item if item.file or not file else Problem(item.code, item.message, item.line, item.column, file)
            for item in problems
        )
        super().__init__('\n'.join(str(item) for item in self.problems))

    @property
    def codes(self):
        """The codes of the problems, in order."""
        return [item.code for item in self.problems]
