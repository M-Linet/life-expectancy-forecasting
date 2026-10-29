"""Baseline forecasts, pooled convergence model, rolling backtests, intervals and scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


def series_by_country(panel: pd.DataFrame, value: str = "life_expectancy",
                      sexes=("both", "female", "male")) -> tuple[dict, pd.DataFrame]:
    """Return {(iso3, sex): Series indexed by year} and a metadata table indexed the same way."""
    d = panel[panel["sex"].isin(sexes)].dropna(subset=[value])
    series = {key: g.set_index("year")[value].sort_index() for key, g in d.groupby(["iso3", "sex"])}
    meta = (d.sort_values("year").groupby(["iso3", "sex"])
            .agg(country=("country", "last"), who_region=("who_region", "last"), population=("population", "last")))
    return series, meta


def _slope(hist: np.ndarray, window: int) -> float:
    w = min(window, len(hist) - 1)
    return (hist[-1] - hist[-1 - w]) / w if w > 0 else 0.0


def naive(hist: np.ndarray, h: int) -> np.ndarray:
    """Tomorrow looks like today."""
    return np.repeat(hist[-1], h)


def drift(hist: np.ndarray, h: int, window: int = 10) -> np.ndarray:
    """Continue the average annual change of the last `window` years in a straight line."""
    return hist[-1] + _slope(hist, window) * np.arange(1, h + 1)


def damped(hist: np.ndarray, h: int, window: int = 10, phi: float = 0.9) -> np.ndarray:
    """Like drift, but the annual gain shrinks by a factor phi each year (gains slow down)."""
    return hist[-1] + _slope(hist, window) * np.cumsum(phi ** np.arange(1, h + 1))
@dataclass
class ConvergenceModel:
    gain_window: int = 5
    exclude_years: tuple = (2020, 2021, 2022)   # shock years are not used to learn "normal" gains
    model: object = field(default=None, repr=False)
    regions: list = field(default_factory=list)

    def _row(self, level, recent_gain, region, sex):
        return [level, recent_gain, self.regions.index(region) if region in self.regions else -1,
                {"female": 0, "male": 1, "both": 2}[sex]]

    def fit(self, series: dict, meta: pd.DataFrame, last_year: int) -> "ConvergenceModel":
        from sklearn.ensemble import HistGradientBoostingRegressor

        self.regions = sorted(meta["who_region"].dropna().unique())
        X, y = [], []
        for key, s in series.items():
            s = s[(s.index <= last_year) & ~s.index.isin(self.exclude_years)]
            values, years = s.to_numpy(), s.index.to_numpy()
            region, sex = meta.loc[key, "who_region"], key[1]
            for t in range(self.gain_window, len(values) - 1):
                if years[t + 1] - years[t] != 1 or years[t] - years[t - self.gain_window] != self.gain_window:
                    continue  # only consecutive years
                recent = (values[t] - values[t - self.gain_window]) / self.gain_window
                X.append(self._row(values[t], recent, region, sex))
                y.append(values[t + 1] - values[t])
        self.model = HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=40,
            categorical_features=[2, 3], random_state=0,
        ).fit(np.array(X), np.array(y))
        self.n_train_ = len(y)
        return self

    def forecast(self, hist: np.ndarray, region: str, sex: str, h: int) -> np.ndarray:
        path = list(hist[-(self.gain_window + 1):])
        out = []
        for _ in range(h):
            recent = (path[-1] - path[-1 - self.gain_window]) / self.gain_window
            gain = self.model.predict(np.array([self._row(path[-1], recent, region, sex)]))[0]
            path.append(path[-1] + gain)
            out.append(path[-1])
        return np.array(out)


METHODS = ["naive", "drift", "damped", "convergence"]


def forecast_all(series: dict, meta: pd.DataFrame, origin: int, h: int, conv: ConvergenceModel | None = None,
                 min_history: int = 8) -> pd.DataFrame:
    """Forecast every series h years ahead from `origin` with every method. Long format."""
    rows = []
    years = np.arange(origin + 1, origin + h + 1)
    for key, s in series.items():
        hist = s[s.index <= origin].dropna()
        if len(hist) < min_history or hist.index[-1] != origin:
            continue
        values = hist.to_numpy()
        preds = {"naive": naive(values, h), "drift": drift(values, h), "damped": damped(values, h)}
        if conv is not None:
            preds["convergence"] = conv.forecast(values, meta.loc[key, "who_region"], key[1], h)
        for method, p in preds.items():
            rows.append(pd.DataFrame({"iso3": key[0], "sex": key[1], "method": method, "origin": origin,
                                      "year": years, "h": np.arange(1, h + 1), "forecast": p}))
    return pd.concat(rows, ignore_index=True)


def backtest(series: dict, meta: pd.DataFrame, origins: list[int], horizon: int, last_valid_year: int) -> pd.DataFrame:
    """Rolling-origin backtest, scoring only years up to last_valid_year."""
    results = []
    for origin in origins:
        h = min(horizon, last_valid_year - origin)
        if h < 1:
            continue
        conv = ConvergenceModel().fit(series, meta, last_year=origin)
        fc = forecast_all(series, meta, origin, h, conv)
        actual = pd.concat({k: s for k, s in series.items()}, names=["iso3", "sex", "year"]).rename("actual").reset_index()
        results.append(fc.merge(actual, on=["iso3", "sex", "year"], how="inner"))
    out = pd.concat(results, ignore_index=True)
    out["error"] = out["forecast"] - out["actual"]
    return out


def error_summary(bt: pd.DataFrame) -> pd.DataFrame:
    """Mean absolute error (years) by method and horizon, plus overall MAE and bias."""
    mae = bt.assign(abs_err=bt["error"].abs()).pivot_table(index="method", columns="h", values="abs_err", aggfunc="mean")
    mae.columns = [f"MAE h={c}" for c in mae.columns]
    mae["MAE overall"] = bt.groupby("method")["error"].apply(lambda e: e.abs().mean())
    mae["bias (mean error)"] = bt.groupby("method")["error"].mean()
    return mae.sort_values("MAE overall")


def empirical_intervals(bt: pd.DataFrame, method: str, max_h: int, levels=(0.8, 0.95)) -> pd.DataFrame:
    """Error quantiles by horizon from the backtest. Beyond the tested horizon, widen with sqrt(h)."""
    e = bt[bt["method"] == method]
    tested = sorted(e["h"].unique())
    rows = []
    for h in range(1, max_h + 1):
        base_h = min(h, tested[-1])
        errs = e.loc[e["h"] == base_h, "error"]
        scale = np.sqrt(h / base_h)
        row = {"h": h}
        for lvl in levels:
            a = (1 - lvl) / 2
            # error = forecast - actual
            row[f"lo{int(lvl * 100)}"] = -errs.quantile(1 - a) * scale
            row[f"hi{int(lvl * 100)}"] = -errs.quantile(a) * scale
        rows.append(row)
    return pd.DataFrame(rows).set_index("h")


def build_scenarios(fc: pd.DataFrame, series: dict, intervals: pd.DataFrame, launch: int) -> pd.DataFrame:
    """Add trend / persistent shortfall / stalled scenarios and intervals to a forecast."""
    out = fc.copy()
    launch_value = out.apply(lambda r: series[(r["iso3"], r["sex"])].get(launch, np.nan), axis=1)
    out = out.join(intervals, on="h")
    for col in [c for c in intervals.columns]:
        out[col] = out["forecast"] + out[col]

    # Shortfall: latest actual minus baseline in that year (negative after COVID)
    actual = pd.concat({k: s for k, s in series.items()}, names=["iso3", "sex", "year"]).rename("actual").reset_index()
    obs = out.merge(actual, on=["iso3", "sex", "year"], how="inner")
    last_obs = obs.sort_values("year").groupby(["iso3", "sex"]).last()
    shortfall = (last_obs["actual"] - last_obs["forecast"]).rename("shortfall")
    out = out.join(shortfall, on=["iso3", "sex"])

    out["trend"] = out["forecast"]
    out["persistent"] = out["forecast"] + out["shortfall"].fillna(0).clip(upper=0)
    out["stalled"] = launch_value + 0.5 * (out["forecast"] - launch_value)
    return out
