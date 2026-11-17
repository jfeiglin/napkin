# SC41: age bands, death rates and device users

SC41 splits each group of people into three age bands: under 65, 65 to 74, and 75 and over. Each band needs its share of the population, its normal death rate and its share of people on home devices. This note gives the arithmetic behind the defaults.

## Shares and death rates

- Population: the Census Bureau's July 2023 estimates of the US resident population by single year of age, both sexes (claim `E-CENSUS-AGE-2023`).
- Death rates: the WHO life table for the United States, 2023, both sexes: the death rate of each age group per person-year (claim `E-WHO-NMX-USA-2023`).

The death rate of a band is the mean of the WHO rates of its single years of age, each weighted by the population at that age. A single year takes the rate of the WHO age group that holds it (under 1, 1 to 4, then five-year groups up to 85 and over).

| Band | Share of the population | Normal death rate (per person-year) |
|---|---|---|
| Under 65 | 0.8231 | 0.002758 |
| 65 to 74 | 0.1036 | 0.018009 |
| 75 and over | 0.0733 | 0.067012 |

The mean over all ages is 0.00905 deaths per person-year. The rates include external causes; the mortality curves of the method are for non-external or natural causes, so the rates slightly overstate the matching normal rate.

## People on home devices

The prevalence of home oxygen concentrators and ventilators comes from Molinari et al. 2017 (claim `E-MOLINARI17-MIX`): 242.0 per 100,000 in the West census region, and 2,185.3 per 100,000 at ages 65 and over. SC41 applies the first to people under 65 and the second to both older bands. With the shares above, 0.59% of the people outside the compound are device users. Concentrators are 99.14% of the device mix and ventilators 0.86%.

## Limits

The age mix and the death rates are national, not local. The device prevalence comes from people with employer-sponsored private insurance, and the regional figure covers all ages.
