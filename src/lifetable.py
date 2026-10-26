"""Life tables, decomposition and counterfactual scenarios.

A life table turns age-specific death rates (nMx) into life expectancy. Once we
can do that, we can ask demographic questions directly:

* **Decomposition (Arriaga, 1984):** which age groups were responsible for a
  change in life expectancy between two years? The age contributions add up
  exactly to the total change.
* **Counterfactuals:** what would life expectancy be if death rates at certain
  ages were lower, for example if a country met an SDG target?

References
----------
Preston, Heuveline & Guillot (2001). *Demography: Measuring and Modeling
Population Processes*. Blackwell. (life table construction, a-values)
Arriaga (1984). Measuring and explaining the change in life expectancies.
*Demography* 21(1):83-96.
Andreev & Kingkade (2015). Average age at death in infancy and infant mortality
level. *Demographic Research* 33:363-390. (a0 formulas)
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from src.config import AGE_BANDS


# --- Age codes -----------------------------------------------------------------
def parse_age_code(code: str) -> tuple[float, float]:
    """Convert a WHO age-group code to (start, width). Open-ended groups get width inf.

    Handles forms such as AGELT1, AGE1-4, AGE5-9, AGE85PLUS, YEARS100PLUS, AGE100+.
    """
    text = str(code).upper()
    numbers = [int(n) for n in re.findall(r"\d+", text)]
    if "LT1" in text or text.endswith("LT01") or numbers == [0, 1] or numbers == [0, 0]:
        return 0.0, 1.0
    if "PLUS" in text or text.endswith("+"):
        return float(numbers[0]), np.inf
    if len(numbers) >= 2:
        return float(numbers[0]), float(numbers[1] - numbers[0] + 1)
    raise ValueError(f"Unrecognised age code: {code!r}")


# --- Life table ---------------------------------------------------------------
def _a0(m0: float, sex: str) -> float:
    """Average years lived in the first year by infants who die (Andreev-Kingkade 2015)."""
    def male(m):
        return 0.14929 - 1.99545 * m if m < 0.02300 else (0.02832 + 3.26201 * m if m < 0.08307 else 0.29915)

    def female(m):
        return 0.14903 - 2.05527 * m if m < 0.01724 else (0.04667 + 3.88089 * m if m < 0.06891 else 0.31411)

    if sex == "male":
        return male(m0)
    if sex == "female":
        return female(m0)
    return (male(m0) + female(m0)) / 2


def _a1(m0: float, sex: str) -> float:
    """Average years lived in ages 1-4 by those who die there (Coale-Demeny West)."""
    male = 1.651 if m0 >= 0.107 else 1.859 - 3.013 * m0
    female = 1.570 if m0 >= 0.107 else 1.522 - 1.518 * m0
    return male if sex == "male" else female if sex == "female" else (male + female) / 2


def life_table(age: np.ndarray, width: np.ndarray, mx: np.ndarray, sex: str = "both") -> pd.DataFrame:
    """Build an abridged period life table from age-specific death rates.

    Parameters
    ----------
    age   : start of each age group, increasing, starting at 0
    width : width of each group; the last (open) group must be np.inf
    mx    : death rate in each group (deaths per person-year)
    sex   : "male", "female" or "both" (only affects the infant/child a-values)
    """
    age, n, m = (np.asarray(x, dtype=float) for x in (age, width, mx))
    if age[0] != 0 or not np.isinf(n[-1]):
        raise ValueError("Ages must start at 0 and the last group must be open-ended")
    m = np.maximum(m, 1e-10)

    a = n / 2
    a[-1] = 1 / m[-1]
    if n[0] == 1:
        a[0] = _a0(m[0], sex)
        if len(n) > 1 and age[1] == 1 and n[1] == 4:
            a[1] = _a1(m[0], sex)

    q = np.ones_like(m)
    q[:-1] = np.minimum(n[:-1] * m[:-1] / (1 + (n[:-1] - a[:-1]) * m[:-1]), 1.0)
    lx = np.concatenate([[1.0], np.cumprod(1 - q)[:-1]])
    dx = lx * q
    Lx = np.empty_like(m)
    Lx[:-1] = n[:-1] * (lx[:-1] - dx[:-1]) + a[:-1] * dx[:-1]
    Lx[-1] = lx[-1] / m[-1]
    Tx = Lx[::-1].cumsum()[::-1]
    ex = Tx / np.where(lx > 0, lx, np.nan)

    return pd.DataFrame({"age": age, "n": n, "mx": m, "ax": a, "qx": q, "lx": lx, "dx": dx,
                         "Lx": Lx, "Tx": Tx, "ex": ex})


def e0(age, width, mx, sex="both") -> float:
    """Life expectancy at birth from death rates."""
    return float(life_table(age, width, mx, sex)["ex"].iloc[0])


def probability_of_dying(table: pd.DataFrame, start: float, end: float) -> float:
    """Probability that someone alive at age `start` dies before `end` (e.g. 5q0, 40q30)."""
    l_start = np.interp(start, table["age"], table["lx"])
    l_end = np.interp(end, table["age"], table["lx"])
    return 1 - l_end / l_start


# --- Decomposition ----------------------------------------------------------
def arriaga(table1: pd.DataFrame, table2: pd.DataFrame) -> pd.Series:
    """Contribution of each age group to the change in e0 from table1 to table2.

    Positive values mean falling mortality at that age added years of life.
    The contributions sum exactly to e0(table2) - e0(table1).
    """
    l1, l2 = table1["lx"].to_numpy(), table2["lx"].to_numpy()
    L1, L2 = table1["Lx"].to_numpy(), table2["Lx"].to_numpy()
    T1, T2 = table1["Tx"].to_numpy(), table2["Tx"].to_numpy()
    l0 = l1[0]

    contrib = np.empty(len(l1))
    # Direct effect (change within the age group) + indirect effect (more survivors carried forward)
    contrib[:-1] = (l1[:-1] / l0) * (L2[:-1] / l2[:-1] - L1[:-1] / l1[:-1]) \
        + (T2[1:] / l0) * (l1[:-1] / l2[:-1] - l1[1:] / l2[1:])
    contrib[-1] = (l1[-1] / l0) * (T2[-1] / l2[-1] - T1[-1] / l1[-1])
    return pd.Series(contrib, index=table1["age"].to_numpy(), name="contribution")


def to_bands(contributions: pd.Series, bands=AGE_BANDS) -> pd.Series:
    """Sum age-group contributions into broader, easier-to-read age bands."""
    out = {}
    for start, end, label in bands:
        mask = (contributions.index >= start) & (contributions.index < end)
        out[label] = contributions[mask].sum()
    return pd.Series(out)


# --- Counterfactual scenarios -------------------------------------------------
def scale_child_mortality_to_target(table: pd.DataFrame, target_5q0: float) -> np.ndarray:
    """Death rates with ages 0-4 scaled down (proportionally) until 5q0 equals the target.

    Returns the original rates unchanged if the country already meets the target.
    """
    mx = table["mx"].to_numpy().copy()
    ages, widths = table["age"].to_numpy(), table["n"].to_numpy()
    if probability_of_dying(table, 0, 5) <= target_5q0:
        return mx
    child = ages < 5
    lo, hi = 0.0, 1.0
    for _ in range(60):  # bisection on the scaling factor
        k = (lo + hi) / 2
        trial = mx.copy()
        trial[child] *= k
        q5 = probability_of_dying(life_table(ages, widths, trial), 0, 5)
        lo, hi = (k, hi) if q5 < target_5q0 else (lo, k)
    mx[child] *= (lo + hi) / 2
    return mx


def reduce_mortality_share(table: pd.DataFrame, start: float, end: float, hazard_share: float,
                           reduction: float) -> np.ndarray:
    """Death rates with one cause group's share of mortality at ages [start, end) cut by `reduction`.

    Example: NCDs make up 60% of the death rate at 30-69 (hazard_share=0.6) and the SDG
    target cuts NCD mortality by a third (reduction=1/3), so rates there fall by 20%.
    """
    mx = table["mx"].to_numpy().copy()
    mask = (table["age"].to_numpy() >= start) & (table["age"].to_numpy() < end)
    mx[mask] *= 1 - float(np.clip(hazard_share, 0, 1)) * reduction
    return mx


def hazard_share(p_cause: float, p_all: float) -> float:
    """Share of the all-cause death rate due to one cause group, from two probabilities of dying.

    Probabilities don't add up across causes, but under competing risks the
    underlying rates do: share = ln(1 - p_cause) / ln(1 - p_all).
    """
    if not (0 < p_cause < 1 and 0 < p_all < 1):
        return np.nan
    return float(np.clip(np.log(1 - p_cause) / np.log(1 - p_all), 0, 1))
