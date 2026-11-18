# Piano tuners

The tuners of a town tune the pianos that need a tuning. The model counts the tunings that they do
in one year.

It shows:

- units of its own: `units.json` declares `tunings` and `tuner`, and the rate is in
  `tunings/(tuner * year)`, a unit made of them with `*` and `/` that needs no entry;
- a stock (`due`, the tunings that the pianos still need, never below zero: `in [0,]`) and a flow
  (`tune`) that moves tunings out of it at the rate times the number of tuners, its request and its
  capacity both;
- a distribution on one input: the default of the rate draws from `pert(600, 1000, 1200)`, in the
  declared unit, and a run can set the rate to any value in `[500, 1500]`;
- records written in place: an assumption on each input and an identity on `tunings_done`, with no
  source file.

A median run takes the median of the distribution.
