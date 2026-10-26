"""Tests for the life-table engine. Each checks a property that must hold mathematically."""

import numpy as np
import pytest

from src.lifetable import (
    arriaga, e0, hazard_share, life_table, parse_age_code, probability_of_dying,
    reduce_mortality_share, scale_child_mortality_to_target, to_bands,
)

AGES = np.array([0, 1] + list(range(5, 90, 5)), dtype=float)
WIDTHS = np.array([1, 4] + [5] * 16 + [np.inf])


def gompertz(level=1.0):
    """A realistic-shaped mortality schedule: high in infancy, low in childhood, rising with age."""
    mx = 0.0002 * np.exp(0.085 * AGES) + 0.0005
    mx[0], mx[1] = 0.04, 0.004
    return mx * level


@pytest.mark.parametrize("code, expected", [
    ("AGELT1", (0, 1)), ("AGE1-4", (1, 4)), ("AGE5-9", (5, 5)), ("AGE85PLUS", (85, np.inf)), ("AGE100+", (100, np.inf)),
])
def test_parse_age_code(code, expected):
    assert parse_age_code(code) == expected


def test_constant_hazard_gives_life_expectancy_of_one_over_m():
    ages = np.arange(0, 120, 5, dtype=float)
    widths = np.array([5.0] * (len(ages) - 1) + [np.inf])
    assert e0(ages, widths, np.full(len(ages), 0.02)) == pytest.approx(50, abs=0.3)


def test_life_table_is_internally_consistent():
    lt = life_table(AGES, WIDTHS, gompertz(), "female")
    assert lt["lx"].iloc[0] == 1
    assert (np.diff(lt["lx"]) <= 0).all()          # survivors never increase
    assert lt["dx"].sum() == pytest.approx(1)       # everyone dies eventually
    assert 40 < lt["ex"].iloc[0] < 90


def test_arriaga_contributions_sum_to_total_change():
    t1 = life_table(AGES, WIDTHS, gompertz(1.3))
    t2 = life_table(AGES, WIDTHS, gompertz(1.0))
    contrib = arriaga(t1, t2)
    assert contrib.sum() == pytest.approx(t2["ex"].iloc[0] - t1["ex"].iloc[0], abs=1e-9)
    assert (contrib > 0).all()                      # mortality fell everywhere
    assert to_bands(contrib).sum() == pytest.approx(contrib.sum())


def test_child_target_is_met_exactly_and_only_children_change():
    lt = life_table(AGES, WIDTHS, gompertz())
    new = scale_child_mortality_to_target(lt, 0.025)
    assert probability_of_dying(life_table(AGES, WIDTHS, new), 0, 5) == pytest.approx(0.025, abs=1e-6)
    assert np.allclose(new[AGES >= 5], lt["mx"][AGES >= 5])


def test_reducing_mortality_raises_life_expectancy():
    lt = life_table(AGES, WIDTHS, gompertz())
    new = reduce_mortality_share(lt, 30, 70, hazard_share=0.6, reduction=1 / 3)
    assert e0(AGES, WIDTHS, new) > lt["ex"].iloc[0]


def test_hazard_share_bounds():
    assert hazard_share(0.2, 0.4) == pytest.approx(np.log(0.8) / np.log(0.6))
    assert np.isnan(hazard_share(0, 0.4))
