# Electricity consequence calculations

Research date: 18 October 2026. Current case: SC41.

SC41 follows one blackout in a heat wave from the first move to its human consequences. Each pathway reports deaths, serious casualties including deaths, and economic loss. The setting names no city: the population, its groups, the climate, the buildings and the protection are inputs. The default setting is a hot, dry supply of 60,000 people with the weather of the July 2006 Phoenix heat wave. Each value in the calculation has its own basis in the model, with its source, its transfer to the scenario or its assumption.

## Heat risk from the temperature that people feel

The heat risk follows the experienced-temperature method of [Stone and colleagues (2023)](https://doi.org/10.1021/acs.est.2c09588) and [Gronlund and colleagues (2026)](https://doi.org/10.1289/EHP15223). The method turns the temperature that people feel at home into an equivalent outdoor temperature, and reads published heat-health curves at that temperature.

For a group in building `b`, without power for `t` hours:

```
rise(t)    = D * (1 - exp(-t / tau))
T'(t)      = T_out + rise(t) / beta
T'_cap(t)  = min(cap, T'(t))
```

`tau` is the heat-up time of the buildings and `beta` the group's slope: the rise in the felt temperature for each degree of outdoor temperature with power. The default slope, 0.208, is the method's average for Phoenix (claim `E-GRONLUND26-S5-PHX`); measured sensors give 0.189 ([slope check](slope-cross-check.md)). One slope for each group keeps the equivalent temperature within reach of the curves. A slope for each person, as in the 2023 study, gives equivalent temperatures up to 229 °C.

`D` is the rise in full darkness. It makes the felt temperature, averaged over the source's 48 hours of full blackout and an even return of power over the next 72 hours, equal the source's mean of 32.7 °C ([calibration](iet-dark-calibration.md)). With the default heat-up time of 12 hours the felt temperature in full darkness is 35.7 °C.

## Deaths

The outage adds deaths at the larger of two excess rates for each age band:

```
all-cause:     mu_band * (RR_all(T') - RR_all(T_out))
heat-related:  r_heat * (RR_heat(T'_cap) - RR_heat(T_out))
```

- `RR_all` is the all-cause curve of Gasparrini and colleagues (2015) for the setting: the log risk ratio rises in a straight line to 1.21 at 40.6 °C from 33.3 °C, and by 0.0539 for each degree above (claim `E-GRONLUND26-S1-PHX`). It has no cap, as in the 2026 method. The paper reports Phoenix all-cause risk ratios up to 6.38. A pool of the four studies with equal weights reaches that only at about 150 °C, so the authors' pool must give this curve most of the weight. The pool with equal weights, and each other study alone, are rows of the [run table](../results/runs.csv).
- `RR_heat` is the curve of Phoenix heat-related deaths (Petitti and colleagues, 2016): 0.440 in the log risk ratio for each degree above 34 °C. It reads the equivalent temperature up to 55 °C, the cap that the 2026 paper uses for these estimates (claim `E-GRONLUND26-CAP55`). Its normal rate is the method's 0.07 deaths a day in 1.39 million people (claim `E-IETCODE-EXTRAPOLATION`).
- `mu_band` is the national death rate of the age band in 2023 ([age bands](age-band-rates.md)).

Heat-related deaths are part of all deaths, so the excess of all deaths is at least the larger of the two. With the grid operating, the 2026 paper gives 20 deaths in Phoenix from the all-cause curves and 220 from the heat-related curve for the same heat (claim `E-GRONLUND26-PHX-BURDEN`).

People with backup cooling or power, in a cooled place, moved away or in hospital keep the temperature that they feel with power, so the outage adds no risk for them. The excess applies only while the heat wave lasts.

## Serious illness

Heat emergency visits follow the Phoenix heat-related curve (0.179 in the log risk ratio for each degree above 33 °C, claim `E-STONE23-ERF`) from a normal rate of 5.9 visits a day in 1.39 million people (claim `E-GRONLUND26-S4-PHX`). The method sums each person's risk over the heat wave and limits it to one (claim `E-STONE23-ANALOG`), so each person counts at most one visit:

```
V(t)          = r_ed * (RR_ed(T') - RR_ed(T_out)), summed over the hours without power in the heat wave
first visit   = 1 - exp(-V(t))
```

`V` is the number of visits that a person at home would have so far. The model treats it as it treats the risk of death, so the share of people with a first visit never passes one. In the delayed response with the default inputs a person at home has about 0.15 visits by the end of the heat wave, and the limit removes about 7% of the heatstroke. At the lowest slopes the curve gives each person at home more than one visit an hour, and the limit then holds heatstroke near 5% of the people at home.

5.4% of the first visits are heatstroke (claim `RB-T04`); the heatstroke visits that end in death, 3.5% (claim `E-WU14`), are already counted among the deaths. A share of the survivors chosen for this scenario, 10%, is as severe as the Chicago 1995 intensive-care patients, of whom a further 28% died within a year (claim `E-DEMATTE98-ICU`). The model reports those later deaths as a one-year figure.

## Restoration and the attacker

Switching starts when the utility has cut the attacker's known route, determined the cyber cause and checked the protection settings: 24 hours after the determination by default. With intact equipment and no checks, the standard crews switch every circuit back on in 15 hours, within the 6 to 30 hours observed after blackouts with intact plant. Circuits come back one by one and stay back.

An attacker that keeps its hidden route changes the settings again when crews start to switch. Crews cannot switch safely while the settings keep changing (claim `E-NASEM17-ENERGIZE`), so they stop until the attacker has stopped, then redo one third of the work still to do. An AI that obeys the stop order stops when the order reaches it. One that refuses goes on until staff force it down, 24, 48 or 120 hours after the outage in the three responses. Its timed job runs 60 hours after the outage, unless staff have cancelled it or every circuit is back.

## Costs

Economic loss adds customers' interruption costs, the restoration work, cooled places, private moves and extra medical care, in 2025 US dollars. Each customer's interruption cost is its 24-hour cost from the ICE 2 calculator times the outage hours divided by 24 to a fitted power (claim `E-ICE2-COSTS`). The calculator was not designed for outages longer than 24 hours (claim `E-ICE2-SCOPE`), so the longer part is a convention. A lineworker-hour costs twice the 2025 median wage.

## Source benchmark

The 2023 study gives about 13,231 additional deaths in 1,445,630 people over its five-day blackout, 917 per 100,000 (claim `V-P01`). SC41 gives far fewer for the same outage profile. One slope for each group removes the near-zero personal slopes behind the source's highest equivalent temperatures, and heat-related deaths stop at the 55 °C cap of the later paper. With the cap of the earlier code, 72 °C, nearly everyone without cooling dies within the heat wave; that row of the run table shows where the method stops being usable.

## Not estimated

Deaths from failed home devices, harm from strained hospitals and urgent care, harm to unsheltered people and wider economic effects are not estimated. Each is an output that reports its reason, never a zero.
