"""Tests for the forecasting module on small synthetic series with known behaviour."""

import numpy as np
import pandas as pd
import pytest

from src.forecasting import (
    ConvergenceModel, backtest, damped, drift, empirical_intervals, error_summary, naive,
)


def test_baselines_on_a_straight_line():
    hist = np.arange(50.0, 60.0, 0.5)  # +0.5 years per year
    assert np.allclose(naive(hist, 3), hist[-1])
    assert np.allclose(drift(hist, 3), hist[-1] + 0.5 * np.array([1, 2, 3]))
    assert (damped(hist, 5) < drift(hist, 5)).all()  # damping always slows gains


def synthetic_world(n=40, years=range(2000, 2020)):
    """Countries converging: gains shrink as life expectancy rises, plus noise."""
    rng = np.random.default_rng(0)
    series, meta = {}, []
    for i in range(n):
        le = rng.uniform(45, 80)
        values = []
        for _ in years:
            values.append(le)
            le += 0.03 * (85 - le) + rng.normal(0, 0.05)
        key = (f"C{i:02d}", "both")
        series[key] = pd.Series(values, index=list(years))
        meta.append({"iso3": key[0], "sex": "both", "country": key[0], "who_region": "R1" if i % 2 else "R2", "population": 1e6})
    return series, pd.DataFrame(meta).set_index(["iso3", "sex"])


def test_convergence_model_learns_faster_gains_at_lower_levels():
    series, meta = synthetic_world()
    model = ConvergenceModel().fit(series, meta, last_year=2015)
    low = model.forecast(np.linspace(48, 53, 10), "R1", "both", 1)[0] - 53
    high = model.forecast(np.linspace(77, 78, 10), "R1", "both", 1)[0] - 78
    assert low > high > -0.5


def test_backtest_and_intervals():
    series, meta = synthetic_world()
    bt = backtest(series, meta, origins=[2010, 2013], horizon=5, last_valid_year=2019)
    assert set(bt["method"]) == {"naive", "drift", "damped", "convergence"}
    assert bt["year"].max() <= 2019
    summary = error_summary(bt)
    assert summary.loc["naive", "MAE overall"] > summary.loc["convergence", "MAE overall"]  # trend exists, naive must lose
    iv = empirical_intervals(bt, "convergence", max_h=10)
    assert (iv["hi95"] - iv["lo95"] >= iv["hi80"] - iv["lo80"]).all()
    assert iv.loc[10, "hi95"] - iv.loc[10, "lo95"] > iv.loc[1, "hi95"] - iv.loc[1, "lo95"]
