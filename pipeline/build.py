"""Refresh pipeline: fetch -> validate -> write CSV -> derive -> export site data.

Failure policy
  * A raw series that fails to fetch or validate keeps its last good CSV and
    is marked 'stale' (or 'unavailable' if there never was one).
  * A derived series built from a stale input is itself marked stale.
  * 'last_successful_refresh' only moves when EVERY series succeeded.
  * Latest observation dates always come from the data, never from the clock.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys

import pandas as pd

from . import config
from .common import (DATA, PEG, ROOT, SITE, fmt_obs, iso, load_json, log,
                     read_series, save_json, staleness, utcnow, validate,
                     write_series)

STATUS_PATH = DATA / "status.json"

# Annual series change about once or twice a year, so do not hit the source every day
# (the IMF's firewall began refusing the build servers after repeated daily requests).
REFETCH_DAYS = {"annual": 7}


def _due(spec, entry, now) -> bool:
    days = REFETCH_DAYS.get(spec["freq"])
    if not days or entry.get("status") != "ok" or read_series(spec["id"]) is None or not entry.get("last_fetch_ok"):
        return True      # failing, missing or never fetched: always retry
    last = dt.datetime.strptime(entry["last_fetch_ok"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    return now - last >= dt.timedelta(days=days)


def _latest_actual(df: pd.DataFrame):
    actual = df[df["flag"] == ""]
    return actual["date"].max() if len(actual) else None


def _refresh_raw(spec, now, prev):
    sid = spec["id"]
    entry = dict(prev.get(sid, {}))
    if not _due(spec, entry, now):
        log(f"[skip]  {sid}: fetched OK {entry['last_fetch_ok']}, next fetch due in under {REFETCH_DAYS[spec['freq']]} days")
        return entry
    try:
        df = spec["fetch"](now)
        validate(df, spec, now)
        write_series(sid, df)
        entry.update(status="ok", error=None, last_fetch_ok=iso(now))
        log(f"[ok]    {sid}: {len(df)} rows, dropped {df.attrs.get('dropped_missing', 0)} missing")
    except Exception as e:  # any failure: keep last good data
        had = read_series(sid) is not None
        entry.update(status="stale" if had else "unavailable", error=f"{type(e).__name__}: {str(e)[:300]}")
        log(f"[FAIL]  {sid}: {entry['error']} -> {'keeping last good data' if had else 'no data'}")
    return entry


def _refresh_derived(spec, now, prev, statuses):
    sid = spec["id"]
    entry = dict(prev.get(sid, {}))
    inputs = {}
    for dep in spec["inputs"]:
        df = read_series(dep)
        if df is None:
            entry.update(status="unavailable", error=f"input '{dep}' has no data")
            return entry
        inputs[dep] = df
    stale_inputs = [d for d in spec["inputs"] if statuses[d]["status"] != "ok"]
    try:
        out = spec["compute"](inputs)
        validate(out, spec, now)
        write_series(sid, out)
        if stale_inputs:
            entry.update(status="stale", error=f"built from stale input(s): {', '.join(stale_inputs)}")
        else:
            entry.update(status="ok", error=None, last_fetch_ok=iso(now))
        log(f"[{entry['status']:<5}] {sid}: {len(out)} rows (derived)")
    except Exception as e:
        had = read_series(sid) is not None
        entry.update(status="stale" if had else "unavailable", error=f"{type(e).__name__}: {str(e)[:300]}")
        log(f"[FAIL]  {sid}: {entry['error']}")
    return entry


def _export(statuses, now, status_doc):
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "data").mkdir(exist_ok=True)
    series = {}
    for spec in config.ALL:
        sid = spec["id"]
        st = statuses[sid]
        df = read_series(sid)
        item = {k: spec[k] for k in ("id", "title", "freq", "unit", "source", "series_id", "url", "transform")}
        item.update(status=st["status"], error=st.get("error"), last_fetch_ok=st.get("last_fetch_ok"),
                    derived="inputs" in spec, base_label=None, rows=0, last_obs=None, last_obs_label=None, age_days=None,
                    limit_days=None, warn=False, proj_from=None, dates=[], values=[], flags=[])
        if df is not None and len(df):
            last = _latest_actual(df)
            lag = dict(spec).get("lag_limit_days")
            if last is not None:
                s = staleness(spec["freq"], last, now)
                if lag:
                    s["limit_days"], s["warn"] = lag, s["age_days"] > lag
                item.update(last_obs=last.strftime("%Y-%m-%d"), last_obs_label=fmt_obs(last, spec["freq"]),
                            age_days=s["age_days"], limit_days=s["limit_days"], warn=s["warn"])
            if "describe" in spec:
                item.update(spec["describe"](df))
            proj = df[df["flag"] == "proj"]
            if len(proj):
                item["proj_from"] = fmt_obs(proj["date"].min(), spec["freq"])
            item.update(rows=len(df), dates=df["date"].dt.strftime("%Y-%m-%d").tolist(),
                        values=[round(float(v), 6) for v in df["value"]], flags=df["flag"].tolist())
            shutil.copyfile(DATA / f"{sid}.csv", SITE / "data" / f"{sid}.csv")
        series[sid] = item
    doc = {
        "meta": {"peg_xof_per_eur": PEG, "peg_display": 655.96,
                 "last_successful_refresh": status_doc.get("last_successful_refresh"),
                 "last_attempt": status_doc.get("last_attempt"),
                 "generated": iso(now)},
        "series": series,
        "unavailable": config.UNAVAILABLE,
    }
    (SITE / "data.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    return doc


def run(now=None) -> int:
    now = now or utcnow()
    if abs(PEG - 655.957) > 1e-9:  # legal parity must never drift
        raise SystemExit(f"PEG constant is {PEG}, expected 655.957")
    DATA.mkdir(exist_ok=True)
    status_doc = load_json(STATUS_PATH, {"series": {}, "last_successful_refresh": None, "last_attempt": None})
    prev = status_doc.get("series", {})
    statuses = {}
    for spec in config.RAW:
        statuses[spec["id"]] = _refresh_raw(spec, now, prev)
    for spec in config.DERIVED:
        statuses[spec["id"]] = _refresh_derived(spec, now, prev, statuses)

    all_ok = all(s["status"] == "ok" for s in statuses.values())
    status_doc["series"] = statuses
    status_doc["last_attempt"] = iso(now)
    if all_ok:
        status_doc["last_successful_refresh"] = iso(now)
    save_json(STATUS_PATH, status_doc)
    _export(statuses, now, status_doc)

    bad = {k: v["status"] for k, v in statuses.items() if v["status"] != "ok"}
    if bad:
        log(f"DEGRADED: {bad}")
        print(f"::warning::Degraded refresh, series not ok: {bad}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"degraded={'true' if bad else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(run())
