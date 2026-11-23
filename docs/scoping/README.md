# Feature scoping

This folder holds one page for each future feature that needs more than a row of a table. The page
gives its scope and its plan, before the work starts. The table of possible future features in
[known-issues.md](../known-issues.md) gives the short list. A row of that table links to its page
here when the feature has one.

## A page

Name a page for its feature, in lowercase words with hyphens: `notebook-smoke-test.md`. Start it
with its title and its status. Then cover these parts, under the headings that suit the feature, and
leave out a part that has nothing to say:

| Part | What it holds |
| --- | --- |
| Title and status | The name of the feature, and one of: draft, agreed, in progress, done |
| The need | What a reader or a maintainer cannot do now, and the evidence for it |
| The scope | What the feature does, and what it does not do |
| The design | How it works, the choices that were weighed, and why one was taken |
| The changes | The files and the parts that change, and what stays the same |
| The checks | The tests and the comparisons that show that it works, and their cost in time |
| The risks and the open questions | What can go wrong, and what a person must decide first |

Write each page to the writing style of [CONTRIBUTING.md](../../CONTRIBUTING.md#writing-style). Give
each value its basis, as the models do: a measurement with how it was made, or an assumption that
says so.

## When a feature is done

The change that does the feature sets the status of its page to done, removes its row from the
table, and says so in [CHANGELOG.md](../../CHANGELOG.md). The page stays as the record of the plan.
