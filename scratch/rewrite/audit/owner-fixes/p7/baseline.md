# Single-pass report selections

Clean engine and reference at `2a84c5fed25acbdaea34fdaf72902ac7ba6c27ef`. On two synthetic counters, `read` returns the two values selected by `iter(['first', 'second'])`, while `report` returns no rows. A selected nonexistent path also bypasses its required error. The first pass during reporting validates the lag map by collecting path names, leaving the iterator empty for the row loop.

All 300 seeded cases failed the same six observations: a plain report, lagged report and unknown path for both iterators and generators. The remaining 11 subcases per seed passed. These cover lists, tuples, direct reads and rejection of an unselected lag key. Seeds vary path order, repeated entries, counter values, query order, and full versus selective recording. The 34 direct tests gave 12 failures and 22 passes.
