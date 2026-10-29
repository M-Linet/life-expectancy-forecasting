"""Reusable analysis helpers: weighting, life-table lookups, decomposition and the drivers model."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import LIFE_TABLES_PATH
from src.lifetable import arriaga, life_table, to_bands


def weighted_mean(df: pd.DataFrame, value: str, weight: str = "population") -> float:
    ok = df[value].notna() & df[weight].notna()
    return float(np.average(df.loc[ok, value], weights=df.loc[ok, weight])) if ok.any() else np.nan


def regional_series(panel: pd.DataFrame, value: str, sex: str = "both", by: str = "who_region") -> pd.DataFrame:
    """Population-weighted mean of `value` per region and year. Returns region x year table (long)."""
    d = panel[panel["sex"] == sex]
    out = (d.groupby([by, "year"]).apply(lambda g: weighted_mean(g, value), include_groups=False)
           .rename(value).reset_index())
    return out.dropna()


def load_life_tables() -> pd.DataFrame | None:
    return pd.read_csv(LIFE_TABLES_PATH) if LIFE_TABLES_PATH.exists() else None


def table_for(lt: pd.DataFrame, iso3: str, year: int, sex: str = "both") -> pd.DataFrame:
    rows = lt[(lt["iso3"] == iso3) & (lt["year"] == year) & (lt["sex"] == sex)].sort_values("age")
    if rows.empty:
        raise KeyError(f"No life table for {iso3} {year} {sex}")
    return life_table(rows["age"], rows["width"], rows["mx"], sex)


def decompose(lt: pd.DataFrame, iso3: str, year1: int, year2: int, sex: str = "both") -> pd.Series:
    """Years of life expectancy gained (or lost) in each age band between two years."""
    return to_bands(arriaga(table_for(lt, iso3, year1, sex), table_for(lt, iso3, year2, sex)))


def decompose_all(lt: pd.DataFrame, panel: pd.DataFrame, year1: int, year2: int, sex: str = "both") -> pd.DataFrame:
    """Age-band decomposition for every country with life tables in both years."""
    have = lt[lt["sex"] == sex].groupby("iso3")["year"].agg(set)
    countries = [iso for iso, years in have.items() if {year1, year2} <= years]
    rows = {iso: decompose(lt, iso, year1, year2, sex) for iso in countries}
    out = pd.DataFrame(rows).T
    out["total"] = out.sum(axis=1)
    meta = (panel[(panel["sex"] == sex) & (panel["year"] == year2)]
            .set_index("iso3")[["country", "who_region", "income_group", "population"]])
    return out.join(meta)


def regional_decomposition(decomp: pd.DataFrame, bands: list[str], by: str = "who_region") -> pd.DataFrame:
    """Population-weighted average country decomposition per region (plus a World row)."""
    def agg(g):
        return pd.Series({b: weighted_mean(g, b) for b in bands + ["total"]})
    regional = decomp.groupby(by).apply(agg, include_groups=False)
    regional.loc["World"] = agg(decomp)
    return regional


def fixed_effects_drivers(panel: pd.DataFrame, outcome: str, factors: list[str], sex: str = "both",
                          country_effects: bool = True):
    """OLS with country + year fixed effects (or year only), factors standardised, SEs clustered by country."""
    import statsmodels.formula.api as smf

    d = panel[panel["sex"] == sex][["iso3", "year", outcome] + factors].dropna()
    for f in factors:  # standardise so coefficients are comparable: years per 1 SD
        d[f] = (d[f] - d[f].mean()) / d[f].std()
    rhs = " + ".join(factors) + (" + C(iso3) + C(year)" if country_effects else " + C(year)")
    model = smf.ols(f"{outcome} ~ {rhs}", data=d).fit(cov_type="cluster", cov_kwds={"groups": d["iso3"]})
    ci = model.conf_int().loc[factors]
    table = pd.DataFrame({"coef": model.params[factors], "low": ci[0], "high": ci[1], "p": model.pvalues[factors]})
    table.attrs.update(n_obs=int(model.nobs), n_countries=d["iso3"].nunique(), r2=model.rsquared)
    return table
SDG_U5MR_TARGET = 0.025   # SDG 3.2.1: under-5 mortality of at most 25 per 1,000 live births
SDG_NCD_REDUCTION = 1 / 3  # SDG 3.4: cut premature (30-70) NCD mortality by one third


def prevention_scenarios(lt: pd.DataFrame, panel: pd.DataFrame, year: int, sex: str = "both",
                         frontier_quantile: float = 0.25) -> pd.DataFrame:
    """Years of e0 gained per country under child, NCD, combined and regional-frontier scenarios."""
    from src.lifetable import (e0, hazard_share, life_table, probability_of_dying,
                               reduce_mortality_share, scale_child_mortality_to_target)

    d = lt[(lt["year"] == year) & (lt["sex"] == sex)]
    region = panel.drop_duplicates("iso3").set_index("iso3")["who_region"]
    ncd = (panel[(panel["sex"] == "both") & panel["ncd_mortality_30_70"].notna()]
           .assign(dist=lambda x: (x["year"] - year).abs()).sort_values("dist")
           .drop_duplicates("iso3").set_index("iso3")["ncd_mortality_30_70"] / 100)

    # NCD share from the both-sexes table (WB series isn't by sex), applied to either sex
    shares = {}
    for iso, g in lt[(lt["year"] == year) & (lt["sex"] == "both")].groupby("iso3"):
        g = g.sort_values("age")
        both_table = life_table(g["age"].to_numpy(), g["width"].to_numpy(), g["mx"].to_numpy(), "both")
        shares[iso] = hazard_share(ncd.get(iso, np.nan), probability_of_dying(both_table, 30, 70))

    # Regional frontier: 25th percentile of each age group's death rate within the region
    d_reg = d.assign(who_region=d["iso3"].map(region))
    frontier = d_reg.groupby(["who_region", "age"])["mx"].quantile(frontier_quantile)

    rows = []
    for iso, g in d.groupby("iso3"):
        g = g.sort_values("age")
        ages, widths = g["age"].to_numpy(), g["width"].to_numpy()
        table = life_table(ages, widths, g["mx"].to_numpy(), sex)
        base = table["ex"].iloc[0]

        child_mx = scale_child_mortality_to_target(table, SDG_U5MR_TARGET)
        share = shares.get(iso, np.nan)
        ncd_mx = reduce_mortality_share(table, 30, 70, share, SDG_NCD_REDUCTION) if np.isfinite(share) else table["mx"].to_numpy()
        combined_mx = child_mx * (ncd_mx / table["mx"].to_numpy())
        reg = region.get(iso)
        fr = frontier.loc[reg].reindex(ages).to_numpy() if reg in frontier.index.get_level_values(0) else table["mx"].to_numpy()
        frontier_mx = np.minimum(table["mx"].to_numpy(), fr)

        rows.append({
            "iso3": iso, "who_region": reg, "e0": base,
            "u5mr": probability_of_dying(table, 0, 5) * 1000, "ncd_share_30_70": share,
            "child": e0(ages, widths, child_mx, sex) - base,
            "ncd": e0(ages, widths, ncd_mx, sex) - base if np.isfinite(share) else np.nan,
            "combined": e0(ages, widths, combined_mx, sex) - base,
            "frontier": e0(ages, widths, frontier_mx, sex) - base,
        })
    out = pd.DataFrame(rows).set_index("iso3")
    meta = panel[(panel["sex"] == "both") & (panel["year"] == year)].set_index("iso3")[["country", "population"]]
    return out.join(meta)
