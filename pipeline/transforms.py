"""Derived series. Every transformation here is documented in config.py."""
from __future__ import annotations

import pandas as pd

from .common import PEG, ValidationError, make_df

BASE_START = 2005     # first year of the base window
BASE_END = None       # None = latest year available, so the window is the whole sample
MIN_BASE_YEARS = 5


def xof_per_usd(eurusd: pd.DataFrame) -> pd.DataFrame:
    """XOF per 1 USD = PEG / EURUSD, where EURUSD is USD per 1 EUR."""
    return make_df(eurusd["date"], PEG / eurusd["value"])


def annual_mean(daily: pd.DataFrame, min_obs: int = 200) -> pd.DataFrame:
    g = daily.groupby(daily["date"].dt.year)["value"].agg(["mean", "count"])
    g = g[g["count"] >= min_obs]
    return make_df([f"{y}-12-31" for y in g.index], g["mean"])


def monthly_mean(daily: pd.DataFrame, min_obs: int = 15) -> pd.DataFrame:
    key = daily["date"].dt.to_period("M")
    g = daily.groupby(key)["value"].agg(["mean", "count"])
    g = g[g["count"] >= min_obs]
    return make_df([p.start_time for p in g.index], g["mean"])


def real_exchange_rate(xof_usd_daily, ci_cpi, us_cpi, base_start: int = BASE_START, base_end: int | None = BASE_END,
                        min_years: int = MIN_BASE_YEARS) -> pd.DataFrame:
    """RER_t = (S_t * P*_t / P_t) / mean_b(S_b * P*_b / P_b) * 100, annual,
    with P* = Ivorian CPI and P = US CPI (the specification asked for; see the methodology page).

    S = annual mean XOF per USD, P* = Ivorian CPI index, P = US CPI index.
    The base is the AVERAGE of S x P_CI/P_US over the years base_start..base_end
    (base_end None = latest year), so 100 means "equal to its historic average",
    taken as the neutral level. Only years present in all inputs are produced.
    """
    s = annual_mean(xof_usd_daily)
    frames = {
        "s": s.assign(y=s["date"].dt.year).set_index("y")["value"],
        "p": ci_cpi.assign(y=ci_cpi["date"].dt.year).set_index("y")["value"],
        "ps": us_cpi.assign(y=us_cpi["date"].dt.year).set_index("y")["value"],
    }
    j = pd.concat(frames, axis=1, join="inner").sort_index()
    raw = j["s"] * j["p"] / j["ps"]
    end = base_end if base_end is not None else int(raw.index.max()) if len(raw) else base_start
    window = raw[(raw.index >= base_start) & (raw.index <= end)]
    if len(window) < min_years:
        raise ValidationError(f"only {len(window)} year(s) in base window {base_start}-{end}, need {min_years}")
    rer = raw / window.mean() * 100.0
    return make_df([f"{y}-12-31" for y in rer.index], rer.values)


def cocoa_in_xof(cocoa_usd: pd.DataFrame, xof_usd_daily: pd.DataFrame) -> pd.DataFrame:
    """Cocoa in XOF million per tonne = USD/t * monthly-mean XOF/USD / 1e6."""
    m = monthly_mean(xof_usd_daily).set_index("date")["value"]
    c = cocoa_usd.set_index("date")["value"]
    j = pd.concat({"c": c, "s": m}, axis=1, join="inner").sort_index()
    return make_df(j.index, j["c"] * j["s"] / 1e6)
