# Life expectancy: what changed, why, and what's next

<!-- 2-3 sentences in your own words: what question you're asking and why you care about it. -->

## Findings

<!-- Fill in after running the notebooks. Use the numbers from the summary cell at the end of each one.
     One or two sentences each, plus why you think it happened (with a link if you looked something up). -->

- **What changed:**
- **Why:**
- **Outlook to 2030:**
- **Prevention:**

<!-- Add your best 1-2 charts here, e.g.
![](reports/figures/10_decomposition_gains.png) -->

## Notebooks

| | |
|---|---|
| `01_eda` | trends, sex gap, COVID drop and recovery, HALE |
| `02_why_it_changed` | Arriaga decomposition by age, cause-related mortality, fixed-effects drivers |
| `03_forecasts_to_2030` | backtested forecasts, prediction intervals, scenarios |
| `04_prevention_scenarios` | years gained if SDG 3.2 / 3.4 targets were met |

## Data

- [WHO Global Health Observatory](https://www.who.int/data/gho): life expectancy and HALE by sex, life tables (nMx)
- [World Bank WDI](https://data.worldbank.org/): economic, health and mortality indicators

All downloaded from the APIs, codes in `src/config.py`.

## Running it

```bash
python -m venv .venv
.venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run_all.py               # fetch data, build, test, run notebooks
```

`python run_all.py --skip-fetch` reruns without downloading again.

## Limitations

<!-- In your own words. Points to cover: WHO estimates are partly modelled, 2020-21 especially;
     fixed effects show associations not causes; forecasts don't include future shocks;
     the NCD share in notebook 04 is an approximation applied to both sexes. -->

## References

- Arriaga (1984), Measuring and explaining the change in life expectancies, *Demography* 21
- Raftery et al. (2013), Bayesian probabilistic projections of life expectancy for all countries, *Demography* 50
- Aburto et al. (2022), Quantifying impacts of the COVID-19 pandemic through life-expectancy losses, *IJE* 51

<!-- Add others from your literature review as you use them. -->
