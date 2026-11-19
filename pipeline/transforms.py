"""Derived series. Every transformation here is documented in config.py."""
from __future__ import annotations

import pandas as pd

from .common import PEG, ValidationError, make_df

BASE_YEAR = 2010


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


def real_exchange_rate(xof_usd_daily, ci_cpi, us_cpi, base_year: int = BASE_YEAR) -> pd.DataFrame:
    """RER_t = (S_t * P*_t / P_t) / (S_b * P*_b / P_b) * 100, annual, base year b.

    S = annual mean XOF per USD, P* = US CPI index, P = Ivorian CPI index.
    Only years present in all three inputs are produced (no filling).
    """
    s = annual_mean(xof_usd_daily)
    frames = {
        "s": s.assign(y=s["date"].dt.year).set_index("y")["value"],
        "p": ci_cpi.assign(y=ci_cpi["date"].dt.year).set_index("y")["value"],
        "ps": us_cpi.assign(y=us_cpi["date"].dt.year).set_index("y")["value"],
    }
    j = pd.concat(frames, axis=1, join="inner").sort_index()
    if base_year not in j.index:
        raise ValidationError(f"base year {base_year} missing from RER inputs")
    raw = j["s"] * j["ps"] / j["p"]
    rer = raw / raw.loc[base_year] * 100.0
    return make_df([f"{y}-12-31" for y in rer.index], rer.values)


def cocoa_in_xof(cocoa_usd: pd.DataFrame, xof_usd_daily: pd.DataFrame) -> pd.DataFrame:
    """Cocoa in XOF million per tonne = USD/t * monthly-mean XOF/USD / 1e6."""
    m = monthly_mean(xof_usd_daily).set_index("date")["value"]
    c = cocoa_usd.set_index("date")["value"]
    j = pd.concat({"c": c, "s": m}, axis=1, join="inner").sort_index()
    return make_df(j.index, j["c"] * j["s"] / 1e6)
