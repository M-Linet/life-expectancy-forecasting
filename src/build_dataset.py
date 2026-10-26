"""Merge the raw WHO and World Bank files into one analysis-ready panel.

Run from the project root after fetching:

    python -m src.build_dataset

Output: data/processed/life_expectancy_panel.csv with one row per
country x year x sex. Outcome columns come from WHO; explanatory variables from
the World Bank are country-level, so they repeat across the three sex rows.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.config import (
    GHO_INDICATORS, LIFE_TABLES_PATH, PANEL_PATH, PROCESSED_DIR, RAW_DIR, WB_INDICATORS, WB_MORTALITY,
)
from src.lifetable import parse_age_code

log = logging.getLogger(__name__)

KEYS = ["iso3", "year", "sex"]


def load_outcomes() -> pd.DataFrame:
    """WHO life expectancy and HALE, wide: one column per measure plus WHO's uncertainty bounds."""
    frames = []
    for code, name in GHO_INDICATORS.items():
        df = pd.read_csv(RAW_DIR / f"gho_{code}.csv")
        df = df.rename(columns={"value": name, "low": f"{name}_low", "high": f"{name}_high"})
        frames.append(df[KEYS + ["who_region_code", "who_region", name, f"{name}_low", f"{name}_high"]])

    out = frames[0]
    for df in frames[1:]:
        out = out.merge(df.drop(columns=["who_region_code", "who_region"]), on=KEYS, how="outer")

    # Region can be missing on rows that only exist in the second indicator; fill per country.
    for col in ["who_region_code", "who_region"]:
        out[col] = out.groupby("iso3")[col].transform(lambda s: s.ffill().bfill())

    # Drop bound columns WHO doesn't publish, so the panel isn't padded with empty columns.
    return out.dropna(axis=1, how="all")


def load_covariates() -> pd.DataFrame:
    """World Bank indicators, wide: one row per country-year, one column per indicator."""
    frames = []
    for code, name in {**WB_INDICATORS, **WB_MORTALITY}.items():
        path = RAW_DIR / f"wb_{code}.csv"
        if not path.exists():
            log.warning("Missing %s; column %s will be empty", path.name, name)
            continue
        df = pd.read_csv(path)
        frames.append(df[["iso3", "year", "value"]].rename(columns={"value": name}).set_index(["iso3", "year"]))
    return pd.concat(frames, axis=1).reset_index()


def build_panel() -> pd.DataFrame:
    outcomes = load_outcomes()
    covariates = load_covariates()
    countries = pd.read_csv(RAW_DIR / "wb_countries.csv")

    panel = (
        outcomes
        .merge(countries, on="iso3", how="left")
        .merge(covariates, on=["iso3", "year"], how="left")
    )
    panel["country"] = panel["country"].fillna(panel["iso3"])

    # Income is right-skewed; most analyses use it on a log scale.
    if "gdp_pc_ppp" in panel:
        panel["log_gdp_pc_ppp"] = np.log(panel["gdp_pc_ppp"])

    # Sex gap (female minus male) as its own country-year series: useful for equity analysis.
    wide = panel.pivot_table(index=["iso3", "year"], columns="sex", values="life_expectancy")
    if {"female", "male"} <= set(wide.columns):
        gap = (wide["female"] - wide["male"]).rename("le_sex_gap").reset_index()
        panel = panel.merge(gap, on=["iso3", "year"], how="left")

    front = ["iso3", "country", "who_region_code", "who_region", "wb_region", "income_group", "year", "sex"]
    panel = panel[front + [c for c in panel.columns if c not in front]]
    return panel.sort_values(["iso3", "sex", "year"]).reset_index(drop=True)


def build_life_tables() -> pd.DataFrame | None:
    """Age-specific death rates in a clean long format: iso3, year, sex, age, width, mx."""
    path = RAW_DIR / "gho_life_table_nmx.csv"
    if not path.exists():
        log.warning("No life-table file; the decomposition and prevention notebooks will be skipped")
        return None
    raw = pd.read_csv(path)
    ages = raw["age_code"].drop_duplicates()
    parsed = pd.DataFrame([parse_age_code(c) for c in ages], index=ages, columns=["age", "width"])
    lt = raw.join(parsed, on="age_code").rename(columns={"value": "mx"})
    lt = lt[["iso3", "year", "sex", "age", "width", "mx"]].sort_values(["iso3", "year", "sex", "age"])

    # Keep only complete schedules (every age group present, starting at 0, ending open-ended).
    n_groups = lt["age"].nunique()
    sizes = lt.groupby(["iso3", "year", "sex"])["age"].transform("size")
    dropped = (sizes != n_groups).sum()
    if dropped:
        log.warning("Dropped %d life-table rows from incomplete schedules", dropped)
    return lt[sizes == n_groups].reset_index(drop=True)


def quality_report(panel: pd.DataFrame) -> None:
    """Print a short data quality summary. Read it before modelling anything."""
    both = panel[panel["sex"] == "both"]
    print("\n=== Data quality report ===")
    print(f"Countries: {panel['iso3'].nunique()}   Years: {panel['year'].min()}-{panel['year'].max()}   Rows: {len(panel):,}")
    print("Countries per WHO region:")
    print(both.groupby("who_region")["iso3"].nunique().sort_values(ascending=False).to_string())
    print("\nMissing values (% of country-years, both sexes):")
    numeric = both.select_dtypes("number").drop(columns=["year"], errors="ignore")
    print((numeric.isna().mean() * 100).round(1).sort_values().to_string())
    missing_country = panel[panel["country"] == panel["iso3"]]["iso3"].unique()
    if len(missing_country):
        print(f"\nNo World Bank match (name shown as ISO3): {sorted(missing_country)}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    panel = build_panel()
    panel.to_csv(PANEL_PATH, index=False)
    log.info("Saved %s (%d rows, %d columns)", PANEL_PATH.name, len(panel), panel.shape[1])
    life_tables = build_life_tables()
    if life_tables is not None:
        life_tables.to_csv(LIFE_TABLES_PATH, index=False)
        log.info("Saved %s (%d rows, %d countries, years %d-%d)", LIFE_TABLES_PATH.name, len(life_tables),
                 life_tables["iso3"].nunique(), life_tables["year"].min(), life_tables["year"].max())
    quality_report(panel)


if __name__ == "__main__":
    main()
