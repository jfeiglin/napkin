"""The typed core of the compiler: what an expression is, apart from how it was written.

- `expr`: the nodes of an expression, each made once (`read` takes one from an expression text).
- `ops`: the contract of each operation of the language, and the check that a consumer handles each.
- `evaluation`: the value of a node, and the programs of many nodes.
- `units`: the units, and the unit of a node.
- `intervals`: the interval of a node over ranges, which proves its domains.
- `faces`: the stocks on whose zero face a node is constant.
- `errors`: the error of an expression.
"""
