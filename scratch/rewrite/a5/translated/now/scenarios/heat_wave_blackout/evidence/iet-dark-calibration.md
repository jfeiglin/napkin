# SC41: experienced temperature in full darkness

SC41 needs the experienced temperature (IET) that a group's homes approach when the power stays off: IET in full darkness. The source study reports only means over its whole event (claim `E-STONE23-IET`): in Phoenix, 26.3 °C with power on and 32.7 °C with power off. The power-off mean includes the 72 hours in which power returns. This note derives IET in full darkness from those means.

## Calculation

The source event lasts 120 hours. Every home is dark for 48 hours, then power returns over the remaining 72 hours in order of distance from the substations (claim `V-P01`). The source gives no shape for the return; SC41 uses an even return, so the time at which a home's power returns is spread evenly from 48 to 120 hours.

While a home is dark, its IET approaches IET in full darkness with a time constant τ. After power returns, IET falls back toward IET with power on with the same time constant. For a home whose power returns at time r, with Δ = IET in full darkness − IET with power on:

- the excess while dark is Δ (r − τ (1 − e^(−r/τ)));
- the excess after power returns is Δ (1 − e^(−r/τ)) τ (1 − e^(−(120 − r)/τ)).

The mean excess over the 120 hours and over all return times must equal 32.7 − 26.3 = 6.4 °C. Solving for Δ gives:

| Heat-up time τ | IET in full darkness |
|---|---|
| 6 h | 35.5 °C |
| 12 h | 35.7 °C |
| 24 h | 36.3 °C |
| 48 h | 38.5 °C |
| 74 h | 41.3 °C |

## Use in SC41

The default heat-up time is 12 hours, so IET in full darkness is 35.7 °C for the default hot, dry setting. Building simulations give 6 to 74 hours for indoor air to warm from 25 to 32 °C (claim `E-NAHLIK17`). The source's own distribution of IET with power off spans about 28 to 39 °C (Figure S1, claim `E-STONE23-SI-FIGS`). Heat-up times above about 50 hours need IET in full darkness above that span, so they do not fit the source's results.

## Limits

The even return of power and the equal heating and cooling rates are conventions. The means are population averages from a simulation, so IET in full darkness is a group mean, not a measured temperature.
