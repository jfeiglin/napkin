# Defensive attention and remediation

The model follows a security team's attention as observed workload rises and falls. It also
reports the effects of defensive tooling adoption on long-term hardening and the pace of
remediation. The default holds workload at its reference level and attention at 0.05 for 25 years.

```sh
python -m napkin run scenarios/cyber_learning_loop \
  --value observations.pressure,defender_attention,defenders.hardening,defenders.closing \
  --at 0h,1year,2years,25years
```

The package entry and the `defensive_response` entry share one model and brief. The current
report shows instantaneous readings and the records behind them. Four historical replays of the
retained defensive equations match at 200 readings. [Model and input ranges](model.scn) ·
[Selected readings](defensive_response/results/readings.md) ·
[Model scope and replay results](defensive_response/README.md)

## Historical study

The earlier study generated incident volume within a larger strategic model. The current
package accepts aggregate incident volume and defensive tooling uptake as observations.
Revision `8488047` preserves the entire earlier source, configuration and specification.
The original published results in this package describe that revision.
[Historical package](https://github.com/jfeiglin/napkin/tree/8488047/scenarios/cyber_learning_loop) ·
[Historical evidence and settings](historical/README.md) · [Historical brief](results/brief.md) ·
[Historical methods](results/methods.md)
