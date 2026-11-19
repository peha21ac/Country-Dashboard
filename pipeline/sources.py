"""Fetchers + parsers for each primary source.

Parsers are pure functions (text/JSON in, canonical DataFrame out) so they can
be unit-tested without network access. Fetchers only add the HTTP call.
"""
from __future__ import annotations

import io

import pandas as pd

from .common import START, FetchError, ValidationError, http_get, make_df, utcnow

START_YEAR = int(START[:4])

ECB_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
WB_URL = "https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
IMF_URL = "https://www.imf.org/external/datamapper/api/v1/{indicator}/{country}"


# ----------------------------------------------------------------------- ECB
def parse_ecb_csv(text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text))
    if not {"TIME_PERIOD", "OBS_VALUE"} <= set(df.columns):
        raise ValidationError(f"unexpected ECB columns: {list(df.columns)[:8]}")
    return make_df(df["TIME_PERIOD"], df["OBS_VALUE"])


def fetch_eurusd(now=None) -> pd.DataFrame:
    r = http_get(ECB_URL, params={"format": "csvdata", "startPeriod": START})
    return parse_ecb_csv(r.text)


# ---------------------------------------------------------------------- FRED
def parse_fred_csv(text: str, series_id: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text), na_values=["."])
    date_col = next((c for c in ("observation_date", "DATE") if c in df.columns), None)
    if date_col is None or series_id not in df.columns:
        raise ValidationError(f"unexpected FRED columns: {list(df.columns)[:8]}")
    return make_df(df[date_col], df[series_id])


def fetch_fred(series_id: str):
    def _fetch(now=None) -> pd.DataFrame:
        r = http_get(FRED_URL, params={"id": series_id, "cosd": START})
        return parse_fred_csv(r.text, series_id)

    return _fetch


# --------------------------------------------------------------- World Bank
def parse_wb_json(payload, current_year: int | None = None) -> pd.DataFrame:
    """World Bank API v2 JSON: [meta, [ {date: '2020', value: 1.2}, ... ]].

    Null values are dropped (not filled). Annual dates are stored as Dec 31.
    """
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        raise ValidationError(f"unexpected World Bank response: {str(payload)[:200]}")
    dates, values = [], []
    for row in payload[1]:
        try:
            year = int(row["date"])
        except (KeyError, ValueError, TypeError):
            raise ValidationError(f"bad World Bank row: {str(row)[:120]}")
        if year < START_YEAR:
            continue
        dates.append(f"{year}-12-31")
        values.append(row.get("value"))
    return make_df(dates, values)


def fetch_wb(indicator: str, country: str = "CIV"):
    def _fetch(now=None) -> pd.DataFrame:
        now = now or utcnow()
        r = http_get(
            WB_URL.format(country=country, indicator=indicator),
            params={"format": "json", "per_page": 20000, "date": f"{START_YEAR}:{now.year}"},
        )
        return parse_wb_json(r.json(), now.year)

    return _fetch


# ---------------------------------------------------------------------- IMF
def parse_imf_datamapper(payload, indicator: str, country: str, current_year: int) -> pd.DataFrame:
    """IMF DataMapper JSON: {'values': {IND: {CTRY: {'2020': 1.2, ...}}}}.

    The API mixes actuals, estimates and WEO projections without labelling
    them. Years >= the current calendar year are flagged 'proj'; the most
    recent actual years may still be IMF-staff estimates (see methodology).
    """
    try:
        series = payload["values"][indicator][country]
    except (KeyError, TypeError):
        raise ValidationError(f"IMF response lacks values/{indicator}/{country}")
    dates, values, flags = [], [], []
    for year, val in series.items():
        y = int(year)
        if y < START_YEAR:
            continue
        dates.append(f"{y}-12-31")
        values.append(val)
        flags.append("proj" if y >= current_year else "")
    return make_df(dates, values, flags)


def fetch_imf(indicator: str, country: str = "CIV"):
    def _fetch(now=None) -> pd.DataFrame:
        now = now or utcnow()
        r = http_get(IMF_URL.format(indicator=indicator, country=country))
        return parse_imf_datamapper(r.json(), indicator, country, now.year)

    return _fetch


__all__ = [n for n in dir() if n.startswith(("fetch_", "parse_"))] + ["FetchError"]
