"""Shared helpers: paths, HTTP, validation, staleness, CSV/JSON IO."""
from __future__ import annotations

import datetime as dt
import json
import math
import pathlib
import sys
import time

import pandas as pd
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SITE = ROOT / "site"

# Legal parity fixed by the EU Council (Decision 98/683/EC): XOF per 1 EUR.
# Usually quoted as 655.96; the exact figure is 655.957.
PEG = 655.957
START = "2005-01-01"
UA = "civ-peg-dashboard/1.0 (+https://github.com/peha21ac/Country-Dashboard)"

# Warn when the newest observation is older than this many days after the
# end of its period (expected release lag).
LAG_LIMIT_DAYS = {"daily": 5, "monthly": 60, "annual": 548}


class FetchError(Exception):
    """A source could not be reached or returned an error."""


class ValidationError(Exception):
    """A source answered, but the data failed a sanity check."""


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(ts: dt.datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def http_get(url, params=None, retries=3, timeout=60):
    last = "no attempt made"
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": UA})
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code} from {url}"
            if r.status_code in (400, 401, 403, 404):
                break  # not transient, do not hammer the source
        except requests.RequestException as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(2 * (attempt + 1))
    raise FetchError(last)


# ---------------------------------------------------------------- data frames
def make_df(dates, values, flags=None) -> pd.DataFrame:
    """Build the canonical frame: date (datetime64), value (float), flag (str).

    Rows with missing values are DROPPED (never filled); the count is kept in
    df.attrs['dropped_missing'] so it can be reported.
    """
    dates, values = list(dates), list(values)
    flags = list(flags) if flags is not None else [""] * len(dates)
    if not (len(dates) == len(values) == len(flags)):
        raise ValueError("dates, values and flags differ in length")
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(pd.Series(dates)),
            "value": pd.to_numeric(pd.Series(values), errors="coerce"),
            "flag": flags,
        }
    )
    dropped = int(df["value"].isna().sum())
    df = df.dropna(subset=["value"]).sort_values("date").reset_index(drop=True)
    df.attrs["dropped_missing"] = dropped
    return df


def validate(df: pd.DataFrame, spec: dict, now: dt.datetime | None = None) -> None:
    """Schema and sanity checks. Raises ValidationError on the first failure."""
    now = now or utcnow()
    if df is None or df.empty:
        raise ValidationError("series is empty")
    if len(df) < spec["min_rows"]:
        raise ValidationError(f"only {len(df)} rows, expected at least {spec['min_rows']}")
    if df["date"].duplicated().any():
        raise ValidationError("duplicate dates")
    if not df["date"].is_monotonic_increasing:
        raise ValidationError("dates are not ascending")
    if not all(math.isfinite(v) for v in df["value"]):
        raise ValidationError("non-finite values")
    lo, hi = spec["lo"], spec["hi"]
    bad = df[(df["value"] < lo) | (df["value"] > hi)]
    if len(bad):
        first = bad.iloc[0]
        raise ValidationError(
            f"{len(bad)} value(s) outside plausible range [{lo}, {hi}]; "
            f"first: {first['date'].date()} = {first['value']}"
        )
    actual = df[df["flag"] == ""]
    limit = pd.Timestamp(now.replace(tzinfo=None).date()) + pd.Timedelta(days=1)
    if len(actual) and actual["date"].max() > limit:
        raise ValidationError(f"observation dated in the future: {actual['date'].max().date()}")


def period_end(date, freq: str) -> pd.Timestamp:
    d = pd.Timestamp(date)
    if freq == "daily":
        return d
    if freq == "monthly":
        return d + pd.offsets.MonthEnd(0)
    if freq == "annual":
        return pd.Timestamp(year=d.year, month=12, day=31)
    raise ValueError(f"unknown frequency {freq}")


def staleness(freq: str, last_obs, now: dt.datetime | None = None) -> dict:
    now = now or utcnow()
    age = (pd.Timestamp(now.replace(tzinfo=None).date()) - period_end(last_obs, freq)).days
    limit = LAG_LIMIT_DAYS[freq]
    return {"age_days": int(age), "limit_days": limit, "warn": bool(age > limit)}


def fmt_obs(date, freq: str) -> str:
    d = pd.Timestamp(date)
    if freq == "annual":
        return f"{d.year}"
    if freq == "monthly":
        return d.strftime("%Y-%m")
    return d.strftime("%Y-%m-%d")


# ------------------------------------------------------------------------ IO
def write_series(sid: str, df: pd.DataFrame) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    out = df[["date", "value", "flag"]].copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(DATA / f"{sid}.csv", index=False)


def read_series(sid: str) -> pd.DataFrame | None:
    path = DATA / f"{sid}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    df["flag"] = df["flag"].fillna("")
    return df


def load_json(path: pathlib.Path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def save_json(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
