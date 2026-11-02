"""Country dashboard: trend, forecast to 2030, age decomposition and prevention scenarios.

Run from the project root:  streamlit run app/streamlit_app.py
Uses data/processed/ (build it with run_all.py first).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analysis import decompose, prevention_scenarios, regional_series
from src.config import AGE_BANDS, LIFE_TABLES_PATH, PANEL_PATH
from src.forecasting import damped, empirical_intervals, series_by_country
from src.plotting import INK, INK_SECONDARY, PALETTE, SEX_COLORS

TARGET_YEAR = 2030
BANDS = [label for _, _, label in AGE_BANDS]
SEX_LABELS = {"Both sexes": "both", "Female": "female", "Male": "male"}
GRID = "#e4e3df"

st.set_page_config(page_title="Life expectancy by country", layout="wide")


@st.cache_data
def load():
    panel = pd.read_csv(PANEL_PATH)
    lt = pd.read_csv(LIFE_TABLES_PATH)
    return panel, lt


@st.cache_data
def forecast_intervals(panel):
    # damped-trend backtest from 2009/2011/2013, scored up to 2019 -> error quantiles by horizon
    series, _ = series_by_country(panel)
    rows = []
    for (iso, sex), s in series.items():
        for origin in (2009, 2011, 2013):
            hist = s[s.index <= origin]
            if len(hist) < 8 or hist.index[-1] != origin:
                continue
            h = 2019 - origin
            fc = damped(hist.to_numpy(), h)
            years = np.arange(origin + 1, origin + h + 1)
            actual = s.reindex(years).to_numpy()
            for i in range(h):
                rows.append({"method": "damped", "origin": origin, "h": i + 1, "error": fc[i] - actual[i]})
    bt = pd.DataFrame(rows).dropna()
    return empirical_intervals(bt, "damped", max_h=TARGET_YEAR - int(panel["year"].max()))


@st.cache_data
def region_prevention(_lt, panel, region, year):
    countries = panel.loc[panel["who_region"] == region, "iso3"].unique()
    return prevention_scenarios(_lt[_lt["iso3"].isin(countries)], panel, year)


def style(fig, height=420):
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="white", paper_bgcolor="white",
        font=dict(color=INK), legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


panel, lt = load()
countries = (panel[["iso3", "country"]].drop_duplicates().sort_values("country").set_index("iso3")["country"])
default = list(countries.index).index("KEN") if "KEN" in countries.index else 0

with st.sidebar:
    st.header("Life expectancy")
    iso = st.selectbox("Country", countries.index, index=default, format_func=countries.get)
    sex_label = st.radio("Sex", list(SEX_LABELS), horizontal=True)
    sex = SEX_LABELS[sex_label]
    st.caption("Data: WHO Global Health Observatory and World Bank. "
               "[Source code](https://github.com/M-Linet/life-expectancy-forecasting)")

c = panel[panel["iso3"] == iso].sort_values("year")
both = c[c["sex"] == "both"].set_index("year")
first, last = int(both.index.min()), int(both.index.max())
region = both["who_region"].iloc[-1]

st.title(countries[iso])
st.caption(f"{region} region · {both['income_group'].iloc[-1]} · WHO estimates {first}-{last}")

m1, m2, m3, m4 = st.columns(4)
m1.metric(f"Life expectancy {last}", f"{both.loc[last, 'life_expectancy']:.1f} yrs",
          f"{both.loc[last, 'life_expectancy'] - both.loc[first, 'life_expectancy']:+.1f} since {first}")
m2.metric(f"Healthy life expectancy {last}", f"{both.loc[last, 'hale']:.1f} yrs",
          help=f"Years expected in full health. The other "
               f"{both.loc[last, 'life_expectancy'] - both.loc[last, 'hale']:.1f} years are lived with illness or disability.")
m3.metric("Women live longer by", f"{both.loc[last, 'le_sex_gap']:.1f} yrs")
u5 = both["u5_mortality"].dropna()
if len(u5):
    m4.metric(f"Under-5 deaths per 1,000 ({int(u5.index[-1])})", f"{u5.iloc[-1]:.0f}",
              f"{u5.iloc[-1] - u5.iloc[0]:+.0f} since {int(u5.index[0])}", delta_color="inverse")

tab1, tab2, tab3 = st.tabs(["Trend and 2030 outlook", "Why it changed", "Prevention"])

with tab1:
    s = c[c["sex"] == sex].set_index("year")["life_expectancy"].dropna()
    iv = forecast_intervals(panel)
    h = TARGET_YEAR - last
    fc_years = np.arange(last, TARGET_YEAR + 1)
    fc = np.concatenate([[s.iloc[-1]], damped(s.to_numpy(), h)])
    lo = np.concatenate([[s.iloc[-1]], fc[1:] + iv["lo80"].to_numpy()[:h]])
    hi = np.concatenate([[s.iloc[-1]], fc[1:] + iv["hi80"].to_numpy()[:h]])
    reg = regional_series(panel, "life_expectancy", sex)
    reg = reg[reg["who_region"] == region]

    color = SEX_COLORS[sex] if sex != "both" else PALETTE[0]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=np.concatenate([fc_years, fc_years[::-1]]), y=np.concatenate([hi, lo[::-1]]),
                             mode="lines", fill="toself", fillcolor="rgba(42,120,214,0.15)" if sex != "male" else "rgba(235,104,52,0.15)",
                             line=dict(width=0), name="80% interval", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=s.index, y=s.values, name=countries[iso], mode="lines", line=dict(color=color, width=2.5),
                             hovertemplate="%{y:.1f} yrs"))
    fig.add_trace(go.Scatter(x=fc_years, y=fc, name="Forecast", mode="lines", line=dict(color=color, width=2, dash="dash"),
                             hovertemplate="%{y:.1f} yrs"))
    fig.add_trace(go.Scatter(x=reg["year"], y=reg["life_expectancy"], name=f"{region} average", mode="lines",
                             line=dict(color=INK_SECONDARY, width=1.5, dash="dot"), hovertemplate="%{y:.1f} yrs"))
    fig.update_yaxes(title=f"Life expectancy at birth, {sex_label.lower()} (years)")
    fig.update_xaxes(range=[first - 0.5, TARGET_YEAR + 0.5], dtick=5)
    st.plotly_chart(style(fig), width="stretch")
    st.markdown(f"**{TARGET_YEAR} outlook:** {fc[-1]:.1f} years (80% range {lo[-1]:.1f} to {hi[-1]:.1f}).")
    st.caption(f"Damped-trend forecast from {last}: the recent trend continues but slows each year. "
               "The band comes from how wrong this method was in backtests on 2009-2019. "
               "It doesn't include shocks like pandemics or conflict. Region average is population-weighted.")

with tab2:
    years = sorted(lt.loc[(lt["iso3"] == iso) & (lt["sex"] == sex), "year"].unique())
    if len(years) < 2:
        st.info("No life tables for this country.")
    else:
        cuts = [y for y in years if (y - years[0]) % 5 == 0 and y <= 2019]
        for y in (2019, 2021, years[-1]):
            if y in years and y > cuts[-1]:
                cuts.append(y)
        periods = pd.DataFrame({f"{a}-{b}": decompose(lt, iso, a, b, sex) for a, b in zip(cuts[:-1], cuts[1:])}).T
        fig = go.Figure()
        for i, band in enumerate(BANDS):
            fig.add_trace(go.Bar(y=periods.index, x=periods[band], name=band, orientation="h",
                                 marker=dict(color=PALETTE[i % len(PALETTE)], line=dict(color="white", width=1)),
                                 hovertemplate=f"{band}: " + "%{x:+.2f} yrs<extra></extra>"))
        fig.add_trace(go.Scatter(y=periods.index, x=periods.sum(axis=1), mode="markers", name="Net change",
                                 marker=dict(symbol="line-ns", size=22, line=dict(width=3, color=INK)),
                                 hovertemplate="Net: %{x:+.2f} yrs<extra></extra>"))
        fig.update_layout(barmode="relative", hovermode="closest")
        fig = style(fig, height=110 + 55 * len(periods))
        fig.update_layout(hovermode="closest")
        fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
        fig.update_xaxes(title="Years of life expectancy gained (+) or lost (-)", showgrid=True, gridcolor=GRID,
                         zeroline=True, zerolinecolor=INK_SECONDARY)
        st.plotly_chart(fig, width="stretch")
        top = periods[BANDS].sum().idxmax()
        st.markdown(f"Over {cuts[0]}-{cuts[-1]}, life expectancy changed by **{periods.values.sum():+.1f} years**. "
                    f"The biggest contribution came from **{top.lower()}** ({periods[top].sum():+.1f} years).")
        st.caption("Arriaga decomposition of WHO life tables. Each bar splits the change in life expectancy "
                   "into the part due to changing death rates at each age; the parts add up to the net change.")

with tab3:
    base_year = 2019
    prev = region_prevention(lt, panel, region, base_year)
    if iso not in prev.index:
        st.info("No life table for this country.")
    else:
        row = prev.loc[iso]
        w = prev["population"].fillna(prev["population"].median())
        reg_avg = {k: np.average(prev[k].fillna(0), weights=w) for k in ["child", "ncd", "combined", "frontier"]}
        labels = {"child": "Child survival target (SDG 3.2)", "ncd": "NCD deaths cut by a third (SDG 3.4)",
                  "combined": "Both targets", "frontier": "Match best performers in region"}
        fig = go.Figure()
        fig.add_trace(go.Bar(y=list(labels.values()), x=[row[k] for k in labels], orientation="h",
                             name=countries[iso], marker_color=PALETTE[0],
                             text=[f"{row[k]:.1f}" for k in labels], textposition="outside",
                             hovertemplate="%{x:.2f} yrs<extra></extra>"))
        fig.add_trace(go.Bar(y=list(labels.values()), x=[reg_avg[k] for k in labels], orientation="h",
                             name=f"{region} average", marker_color="#c3c2b7",
                             text=[f"{reg_avg[k]:.1f}" for k in labels], textposition="outside",
                             hovertemplate="%{x:.2f} yrs<extra></extra>"))
        fig = style(fig, height=340)
        fig.update_layout(barmode="group", hovermode="closest")
        fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
        fig.update_xaxes(title=f"Years of life expectancy gained ({base_year} death rates)", showgrid=True, gridcolor=GRID)
        st.plotly_chart(fig, width="stretch")
        if row["u5mr"] <= 25:
            st.markdown(f"{countries[iso]} already meets the under-5 target "
                        f"({row['u5mr']:.0f} deaths per 1,000 in {base_year}), so that scenario adds nothing.")
        else:
            st.markdown(f"Under-5 mortality was **{row['u5mr']:.0f} per 1,000** in {base_year}; "
                        f"bringing it to 25 would add **{row['child']:.1f} years**.")
        st.caption("What-if calculations, not predictions: death rates in the country's life table are lowered "
                   "and life expectancy recomputed. The NCD share of deaths is an approximation.")
