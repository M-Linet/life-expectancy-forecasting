"""Download raw data from the WHO GHO and World Bank APIs.

Run from the project root:

    python -m src.fetch_data            # download anything not already cached
    python -m src.fetch_data --refresh  # re-download everything

Raw responses are saved unchanged (apart from flattening to CSV) in data/raw/,
so every later step can be reproduced without hitting the APIs again.
"""

from __future__ import annotations

import argparse
import logging
import time

import pandas as pd
import requests

from src.config import (
    END_YEAR,
    GHO_API,
    GHO_INDICATORS,
    LIFE_TABLE_NAME_PATTERN,
    RAW_DIR,
    SEX_CODES,
    START_YEAR,
    WB_INDICATORS,
    WB_MORTALITY,
    WORLD_BANK_API,
)

log = logging.getLogger(__name__)

TIMEOUT = 60  # seconds
RETRIES = 3


# --- HTTP helper -------------------------------------------------------------
def get_json(url: str, params: dict | None = None, session: requests.Session | None = None):
    """GET a URL and return parsed JSON, retrying on temporary failures."""
    http = session or requests
    for attempt in range(1, RETRIES + 1):
        try:
            response = http.get(url, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as err:
            if attempt == RETRIES:
                raise RuntimeError(f"Failed to fetch {url}: {err}") from err
            wait = 2 ** attempt
            log.warning("Attempt %d for %s failed (%s); retrying in %ds", attempt, url, err, wait)
            time.sleep(wait)


# --- WHO Global Health Observatory -------------------------------------------
def parse_gho(records: list[dict], indicator_code: str) -> pd.DataFrame:
    """Turn GHO OData records into a tidy table: one row per country, year and sex."""
    df = pd.DataFrame(records)
    if df.empty:
        raise ValueError(f"No records returned for {indicator_code}")

    df = df[df["SpatialDimType"] == "COUNTRY"].copy()  # drop regional / global aggregates
    df["sex"] = df["Dim1"].map(SEX_CODES)

    unknown = df.loc[df["sex"].isna(), "Dim1"].unique()
    if len(unknown):
        log.warning("%s: unrecognised sex codes %s were dropped", indicator_code, list(unknown))
        df = df.dropna(subset=["sex"])

    tidy = pd.DataFrame({
        "iso3": df["SpatialDim"],
        "who_region_code": df.get("ParentLocationCode"),
        "who_region": df.get("ParentLocation"),
        "year": pd.to_numeric(df["TimeDim"], errors="coerce").astype("Int64"),
        "sex": df["sex"],
        "value": pd.to_numeric(df["NumericValue"], errors="coerce"),
        "low": pd.to_numeric(df.get("Low"), errors="coerce"),
        "high": pd.to_numeric(df.get("High"), errors="coerce"),
        "indicator": indicator_code,
    })
    return tidy.sort_values(["iso3", "sex", "year"]).reset_index(drop=True)


def get_gho_records(url: str, session=None) -> list[dict]:
    """Fetch every record from a GHO OData endpoint, following pagination links if present."""
    records: list[dict] = []
    while url:
        payload = get_json(url, session=session)
        records.extend(payload.get("value", []))
        url = payload.get("@odata.nextLink")
    return records


def fetch_gho(indicator_code: str, session=None) -> pd.DataFrame:
    """Download one GHO indicator for all countries, years and sexes."""
    return parse_gho(get_gho_records(f"{GHO_API}/{indicator_code}", session), indicator_code)


def fetch_gho_catalogue(session=None) -> pd.DataFrame:
    """WHO's list of every GHO indicator (code and name). Used to look codes up by name."""
    records = get_gho_records(f"{GHO_API}/Indicator", session)
    return pd.DataFrame(records)[["IndicatorCode", "IndicatorName"]]


def resolve_indicator(catalogue: pd.DataFrame, pattern: str) -> str:
    """Find the single GHO indicator whose name matches a regex, and fail loudly if it's ambiguous."""
    hits = catalogue[catalogue["IndicatorName"].str.contains(pattern, case=False, regex=True, na=False)]
    if hits.empty:
        raise LookupError(f"No GHO indicator name matches {pattern!r}")
    if len(hits) > 1:
        log.warning("Several indicators match %r; using the first:\n%s", pattern, hits.to_string(index=False))
    code, name = hits.iloc[0]
    log.info("Resolved %r -> %s (%s)", pattern, code, name)
    return code


def _dimension_columns(df: pd.DataFrame) -> tuple[str, str]:
    """Work out which GHO 'Dim' column holds sex and which holds age group."""
    sex_col = age_col = None
    for col in [c for c in df.columns if c.startswith("Dim") and not c.endswith("Type")]:
        values = df[col].dropna().astype(str)
        if values.empty:
            continue
        if values.isin(SEX_CODES.keys()).mean() > 0.9:
            sex_col = col
        elif values.str.upper().str.contains("AGE|YEARS").mean() > 0.9:
            age_col = col
    if not (sex_col and age_col):
        raise ValueError(f"Could not identify sex and age columns among {list(df.columns)}")
    return sex_col, age_col


def parse_gho_life_table(records: list[dict], indicator_code: str) -> pd.DataFrame:
    """Tidy life-table rows: one row per country, year, sex and age group (age code kept raw)."""
    df = pd.DataFrame(records)
    df = df[df["SpatialDimType"] == "COUNTRY"].copy()
    sex_col, age_col = _dimension_columns(df)
    tidy = pd.DataFrame({
        "iso3": df["SpatialDim"],
        "year": pd.to_numeric(df["TimeDim"], errors="coerce").astype("Int64"),
        "sex": df[sex_col].map(SEX_CODES),
        "age_code": df[age_col],
        "value": pd.to_numeric(df["NumericValue"], errors="coerce"),
        "indicator": indicator_code,
    }).dropna(subset=["sex", "value"])
    return tidy.reset_index(drop=True)


def fetch_life_table(session=None) -> pd.DataFrame:
    catalogue = fetch_gho_catalogue(session)
    catalogue.to_csv(RAW_DIR / "gho_indicator_catalogue.csv", index=False)
    code = resolve_indicator(catalogue, LIFE_TABLE_NAME_PATTERN)
    return parse_gho_life_table(get_gho_records(f"{GHO_API}/{code}", session), code)


# --- World Bank ----------------------------------------------------------------
def parse_wb_indicator(rows: list[dict], indicator_code: str) -> pd.DataFrame:
    """Turn World Bank API rows into a tidy table: one row per country and year."""
    df = pd.DataFrame({
        "iso3": [r.get("countryiso3code") for r in rows],
        "year": [r.get("date") for r in rows],
        "value": [r.get("value") for r in rows],
    })
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["indicator"] = indicator_code
    # Aggregates such as "Sub-Saharan Africa" have no ISO3 code here; drop them.
    df = df[df["iso3"].fillna("").str.len() == 3]
    return df.dropna(subset=["year"]).reset_index(drop=True)


def fetch_wb_indicator(indicator_code: str, session=None) -> pd.DataFrame:
    """Download one World Bank indicator for all countries, following pagination."""
    url = f"{WORLD_BANK_API}/country/all/indicator/{indicator_code}"
    params = {"format": "json", "date": f"{START_YEAR}:{END_YEAR}", "per_page": 20000, "page": 1}
    rows: list[dict] = []
    while True:
        payload = get_json(url, params=params, session=session)
        if not isinstance(payload, list) or len(payload) < 2:
            raise RuntimeError(f"Unexpected World Bank response for {indicator_code}: {payload}")
        meta, data = payload[0], payload[1] or []
        rows.extend(data)
        if params["page"] >= int(meta.get("pages", 1)):
            break
        params["page"] += 1
    return parse_wb_indicator(rows, indicator_code)


def parse_wb_countries(rows: list[dict]) -> pd.DataFrame:
    """Country metadata: names, World Bank region and income group (aggregates removed)."""
    df = pd.DataFrame({
        "iso3": [r.get("id") for r in rows],
        "country": [r.get("name") for r in rows],
        "wb_region": [(r.get("region") or {}).get("value") for r in rows],
        "income_group": [(r.get("incomeLevel") or {}).get("value") for r in rows],
    })
    df["wb_region"] = df["wb_region"].str.strip()
    return df[df["wb_region"] != "Aggregates"].reset_index(drop=True)


def fetch_wb_countries(session=None) -> pd.DataFrame:
    payload = get_json(f"{WORLD_BANK_API}/country", params={"format": "json", "per_page": 400}, session=session)
    return parse_wb_countries(payload[1])


# --- Orchestration -----------------------------------------------------------
def _save(df: pd.DataFrame, name: str) -> None:
    path = RAW_DIR / f"{name}.csv"
    df.to_csv(path, index=False)
    log.info("Saved %-40s %6d rows", path.relative_to(RAW_DIR.parent.parent), len(df))


def fetch_all(refresh: bool = False, session=None) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    http = session or requests.Session()

    jobs = [(f"gho_{code}", lambda c=code: fetch_gho(c, http)) for code in GHO_INDICATORS]
    jobs += [(f"wb_{code}", lambda c=code: fetch_wb_indicator(c, http)) for code in {**WB_INDICATORS, **WB_MORTALITY}]
    jobs.append(("wb_countries", lambda: fetch_wb_countries(http)))
    jobs.append(("gho_life_table_nmx", lambda: fetch_life_table(http)))

    failed = []
    for name, job in jobs:
        if (RAW_DIR / f"{name}.csv").exists() and not refresh:
            log.info("Cached  %s (use --refresh to re-download)", name)
            continue
        try:
            _save(job(), name)
        except Exception as err:  # keep going so one bad indicator doesn't stop the rest
            log.error("Could not fetch %s: %s", name, err)
            failed.append(name)

    if failed:
        raise SystemExit(f"Finished with errors. Failed downloads: {failed}")
    log.info("All downloads complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="re-download files that are already cached")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    fetch_all(refresh=args.refresh)


if __name__ == "__main__":
    main()
