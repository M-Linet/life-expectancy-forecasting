"""Tests for the API parsers, using small hand-written samples of each API's format.

Run with:  pytest
"""

from src.fetch_data import parse_gho, parse_wb_countries, parse_wb_indicator


def gho_record(country, year, sex, value, kind="COUNTRY"):
    return {
        "SpatialDimType": kind, "SpatialDim": country,
        "ParentLocationCode": "AFR", "ParentLocation": "Africa",
        "TimeDim": year, "Dim1": sex, "NumericValue": value,
        "Low": value - 1, "High": value + 1,
    }


def test_parse_gho_keeps_countries_and_maps_sex():
    records = [
        gho_record("KEN", 2019, "SEX_FMLE", 66.0),
        gho_record("KEN", 2019, "SEX_MLE", 61.0),
        gho_record("KEN", 2019, "SEX_BTSX", 63.5),
        gho_record("AFR", 2019, "SEX_BTSX", 64.0, kind="REGION"),  # aggregate: must be dropped
    ]
    df = parse_gho(records, "WHOSIS_000001")
    assert set(df["iso3"]) == {"KEN"}
    assert set(df["sex"]) == {"female", "male", "both"}
    assert df.loc[df["sex"] == "female", "value"].item() == 66.0


def test_parse_gho_drops_unknown_sex_codes():
    records = [gho_record("KEN", 2019, "SEX_BTSX", 63.5), gho_record("KEN", 2019, "SEX_UNK", 1.0)]
    assert len(parse_gho(records, "WHOSIS_000001")) == 1


def test_parse_wb_indicator_drops_aggregates_and_handles_nulls():
    rows = [
        {"countryiso3code": "KEN", "date": "2020", "value": 4.3},
        {"countryiso3code": "KEN", "date": "2021", "value": None},
        {"countryiso3code": "", "date": "2020", "value": 5.0},  # aggregate rows have no ISO3
    ]
    df = parse_wb_indicator(rows, "SH.XPD.CHEX.GD.ZS")
    assert list(df["iso3"]) == ["KEN", "KEN"]
    assert df["value"].isna().sum() == 1


def test_parse_wb_countries_removes_aggregates():
    rows = [
        {"id": "KEN", "name": "Kenya", "region": {"value": "Sub-Saharan Africa "}, "incomeLevel": {"value": "Lower middle income"}},
        {"id": "SSF", "name": "Sub-Saharan Africa", "region": {"value": "Aggregates"}, "incomeLevel": {"value": "Aggregates"}},
    ]
    df = parse_wb_countries(rows)
    assert list(df["iso3"]) == ["KEN"]
    assert df["wb_region"].item() == "Sub-Saharan Africa"
