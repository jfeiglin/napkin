# Piano tuners

The tuners of a town tune the pianos that need a tuning. The model counts the tunings that they do
in one year.

It shows:

- units of its own: `units.json` declares `tunings` and `tuner`, and the rate is in
  `tunings/tuner-year`, a unit made of them that needs no entry;
- a stock (`due`, the tunings that the pianos still need) and a flow (`tune`) that moves tunings
  out of it, at the rate times the number of tuners;
- a distribution on one input: the rate is `pert(…)`, so each sample draws its own rate;
- records written in place: an assumption on each input and an identity on the output, with no
  source file.

Run it from the folder that holds `examples/`:

```sh
napkin run examples/piano_tuners
napkin sample examples/piano_tuners --samples 50
napkin run examples/piano_tuners --set tuners.staff=5
napkin draw examples/piano_tuners -o piano_tuners.svg
```

A run without samples takes the median of the distribution. `napkin sample` draws the rate for each
sample and prints the spread of the tunings done.
