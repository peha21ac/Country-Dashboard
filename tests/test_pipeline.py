"""Tests use SYNTHETIC data only. They exercise logic, not real-world values."""
import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from pipeline import build, common, config, sources, transforms
from pipeline.common import PEG, ValidationError, make_df, staleness, validate

NOW = dt.datetime(2026, 11, 18, 12, 0, tzinfo=dt.timezone.utc)
SPEC = dict(min_rows=3, lo=0, hi=100)


# ------------------------------------------------------------------ parsers
def test_ecb_parser_and_drops_missing():
    text = "KEY,TIME_PERIOD,OBS_VALUE\nX,2024-01-02,1.10\nX,2024-01-03,\nX,2024-01-04,1.12\n"
    df = sources.parse_ecb_csv(text)
    assert list(df["value"]) == [1.10, 1.12]
    assert df.attrs["dropped_missing"] == 1


def test_ecb_parser_rejects_html():
    with pytest.raises(ValidationError):
        sources.parse_ecb_csv("<html><body>blocked</body></html>")


@pytest.mark.parametrize("col", ["observation_date", "DATE"])
def test_fred_parser_both_header_styles_and_dot_missing(col):
    text = f"{col},PCOCOUSDM\n2024-01-01,3000\n2024-02-01,.\n2024-03-01,3100\n"
    df = sources.parse_fred_csv(text, "PCOCOUSDM")
    assert len(df) == 2 and df["date"].iloc[-1] == pd.Timestamp("2024-03-01")


def test_wb_parser_nulls_and_old_years():
    payload = [{"page": 1}, [{"date": "2024", "value": 5.0}, {"date": "2023", "value": None},
                             {"date": "2001", "value": 9.0}, {"date": "2022", "value": 4.0}]]
    df = sources.parse_wb_json(payload)
    assert list(df["date"].dt.year) == [2022, 2024]  # sorted, null + pre-2005 dropped


def test_wb_parser_error_payload():
    with pytest.raises(ValidationError):
        sources.parse_wb_json([{"message": [{"id": "120", "value": "Invalid format"}]}])


def test_imf_parser_flags_projections():
    payload = {"values": {"NGDP_RPCH": {"CIV": {"2024": 6.0, "2026": 6.4, "2027": 6.5}}}}
    df = sources.parse_imf_datamapper(payload, "NGDP_RPCH", "CIV", current_year=2026)
    assert list(df["flag"]) == ["", "proj", "proj"]


def test_imf_parser_missing_country():
    with pytest.raises(ValidationError):
        sources.parse_imf_datamapper({"values": {}}, "NGDP_RPCH", "CIV", 2026)


# --------------------------------------------------------------- validation
def df3(vals, start="2024-01-01"):
    return make_df(pd.date_range(start, periods=len(vals), freq="D"), vals)


def test_validate_ok():
    validate(df3([1, 2, 3]), SPEC, NOW)


@pytest.mark.parametrize("df,msg", [
    (make_df([], []), "empty"),
    (df3([1, 2]), "rows"),
    (df3([1, 2, 500]), "outside"),
])
def test_validate_failures(df, msg):
    with pytest.raises(ValidationError, match=msg):
        validate(df, SPEC, NOW)


def test_validate_duplicates_and_order():
    d = df3([1, 2, 3])
    dup = pd.concat([d, d.iloc[[0]]]).reset_index(drop=True)
    with pytest.raises(ValidationError, match="duplicate"):
        validate(dup, SPEC, NOW)
    unsorted = d.iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValidationError, match="ascending"):
        validate(unsorted, SPEC, NOW)


def test_validate_future_actual_but_not_projection():
    fut = make_df(["2026-01-01", "2026-06-01", "2027-12-31"], [1, 2, 3], ["", "", ""])
    with pytest.raises(ValidationError, match="future"):
        validate(fut, SPEC, NOW)
    proj = make_df(["2026-01-01", "2026-06-01", "2027-12-31"], [1, 2, 3], ["", "", "proj"])
    validate(proj, SPEC, NOW)


def test_peg_constant_is_legal_parity():
    assert abs(PEG - 655.957) < 1e-9
    assert round(PEG, 2) == 655.96  # the figure shown on the dashboard


# ---------------------------------------------------------------- staleness
@pytest.mark.parametrize("freq,last,warn", [
    ("daily", "2026-11-14", False),      # 4 days
    ("daily", "2026-11-10", True),       # 8 days
    ("monthly", "2026-09-01", False),    # month-end Sep 30 -> 49 days
    ("monthly", "2026-08-01", True),     # month-end Aug 31 -> 79 days
    ("annual", "2025-12-31", False),
    ("annual", "2024-12-31", True),      # 687 days > 548 default
])
def test_staleness(freq, last, warn):
    assert staleness(freq, pd.Timestamp(last), NOW)["warn"] is warn


# --------------------------------------------------------------- transforms
def synthetic_eurusd(rate=1.25):
    d = pd.bdate_range("2005-01-03", "2026-11-13")
    return make_df(d, np.full(len(d), rate))


def test_xof_per_usd_hand_calc():
    out = transforms.xof_per_usd(make_df(["2024-01-02"], [1.25]))
    assert out["value"].iloc[0] == pytest.approx(655.957 / 1.25)
    # round trip: XOF/USD * USD/EUR returns the peg exactly
    assert out["value"].iloc[0] * 1.25 == pytest.approx(PEG)


def test_rer_hand_calc_and_base():
    # S constant 500; US CPI doubles 2010->2020, CIV CPI rises 50%:
    # RER_2020 = (500*200/150) / (500*100/100) * 100 = 133.33
    days = pd.bdate_range("2009-01-01", "2021-01-01")
    xof = make_df(days, np.full(len(days), 500.0))
    ci = make_df(["2010-12-31", "2020-12-31"], [100.0, 150.0])
    us = make_df(["2010-12-31", "2020-12-31"], [100.0, 200.0])
    rer = transforms.real_exchange_rate(xof, ci, us, base_year=2010).set_index("date")["value"]
    assert rer[pd.Timestamp("2010-12-31")] == pytest.approx(100.0)
    assert rer[pd.Timestamp("2020-12-31")] == pytest.approx(133.3333, rel=1e-4)


def test_rer_missing_base_year():
    days = pd.bdate_range("2015-01-01", "2021-01-01")
    xof = make_df(days, np.full(len(days), 500.0))
    cpi = make_df(["2016-12-31", "2017-12-31"], [100.0, 101.0])
    with pytest.raises(ValidationError, match="base year"):
        transforms.real_exchange_rate(xof, cpi, cpi, base_year=2010)


def test_annual_mean_skips_incomplete_year():
    d = pd.bdate_range("2025-01-01", "2026-03-01")  # 2026 incomplete
    out = transforms.annual_mean(make_df(d, np.ones(len(d))))
    assert list(out["date"].dt.year) == [2025]


def test_cocoa_in_xof_hand_calc():
    days = pd.bdate_range("2024-01-01", "2024-01-31")
    xof = make_df(days, np.full(len(days), 600.0))
    cocoa = make_df(["2024-01-01", "2024-02-01"], [5000.0, 5200.0])
    out = transforms.cocoa_in_xof(cocoa, xof)
    assert len(out) == 1 and out["value"].iloc[0] == pytest.approx(3.0)  # 5000*600/1e6


# ------------------------------------------- end-to-end refresh + failures
def synthetic_fetchers():
    def eurusd(now=None):
        return synthetic_eurusd(1.1)

    def cocoa(now=None):
        d = pd.date_range("2005-01-01", "2026-10-01", freq="MS")
        return make_df(d, 2000 + 10 * np.arange(len(d)))

    def annual(base, slope, flag_from=None):
        def f(now=None):
            yrs = list(range(2005, 2026))
            return make_df([f"{y}-12-31" for y in yrs], [base + slope * (y - 2005) for y in yrs])
        return f

    def imf(base):
        def f(now=None):
            yrs = list(range(2005, 2031))
            return make_df([f"{y}-12-31" for y in yrs], [base + 0.1 * (y - 2005) for y in yrs],
                           ["proj" if y >= 2026 else "" for y in yrs])
        return f

    return {
        "eurusd": eurusd, "cocoa_usd": cocoa,
        "ci_cpi_idx": annual(70, 3), "us_cpi_idx": annual(80, 2),
        "ci_infl": annual(2, 0.05), "ci_trade_bal": annual(1, 0.1),
        "ci_gdp_growth": imf(5), "ci_gov_bal": imf(-3), "ci_debt": imf(40),
    }


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "DATA", tmp_path / "data")
    monkeypatch.setattr(build, "DATA", tmp_path / "data")
    monkeypatch.setattr(build, "SITE", tmp_path / "site")
    monkeypatch.setattr(build, "STATUS_PATH", tmp_path / "data" / "status.json")
    fetchers = synthetic_fetchers()
    for spec in config.RAW:
        monkeypatch.setitem(spec, "fetch", fetchers[spec["id"]])
    return tmp_path, fetchers


def load(tmp):
    return (json.loads((tmp / "data" / "status.json").read_text()),
            json.loads((tmp / "site" / "data.json").read_text()))


def test_full_refresh_ok(sandbox):
    tmp, _ = sandbox
    build.run(NOW)
    status, site = load(tmp)
    assert all(s["status"] == "ok" for s in status["series"].values())
    assert status["last_successful_refresh"] == "2026-11-18T12:00:00Z"
    s = site["series"]
    assert s["ci_gdp_growth"]["proj_from"] == "2026"
    assert s["ci_gdp_growth"]["last_obs_label"] == "2025"     # latest ACTUAL, not projection
    assert s["rer"]["values"][s["rer"]["dates"].index("2010-12-31")] == pytest.approx(100.0)
    assert s["eurusd"]["last_obs"] == "2026-11-13"            # from data, not from the clock


def test_failure_keeps_last_good_and_freezes_refresh_time(sandbox, monkeypatch):
    tmp, fetchers = sandbox
    build.run(NOW)
    good_csv = (tmp / "data" / "cocoa_usd.csv").read_text()

    later = NOW + dt.timedelta(days=1)

    def boom(now=None):
        raise common.FetchError("HTTP 503 from source")

    monkeypatch.setitem(config.BY_ID["cocoa_usd"], "fetch", boom)
    build.run(later)
    status, site = load(tmp)
    assert status["series"]["cocoa_usd"]["status"] == "stale"
    assert "503" in status["series"]["cocoa_usd"]["error"]
    assert (tmp / "data" / "cocoa_usd.csv").read_text() == good_csv       # data untouched
    assert status["series"]["cocoa_xof"]["status"] == "stale"             # derived inherits
    assert status["last_successful_refresh"] == "2026-11-18T12:00:00Z"    # NOT advanced
    assert status["last_attempt"] == "2026-11-19T12:00:00Z"
    assert site["series"]["cocoa_usd"]["last_obs"] == "2026-10-01"        # last good date retained


def test_bad_data_rejected_not_written(sandbox, monkeypatch):
    tmp, _ = sandbox
    build.run(NOW)
    good = (tmp / "data" / "eurusd.csv").read_text()

    def garbage(now=None):
        return synthetic_eurusd(9.9)     # outside plausible range

    monkeypatch.setitem(config.BY_ID["eurusd"], "fetch", garbage)
    build.run(NOW + dt.timedelta(days=1))
    status, _ = load(tmp)
    assert status["series"]["eurusd"]["status"] == "stale"
    assert "outside plausible range" in status["series"]["eurusd"]["error"]
    assert (tmp / "data" / "eurusd.csv").read_text() == good


def test_first_run_failure_is_unavailable_not_fabricated(sandbox, monkeypatch):
    tmp, _ = sandbox

    def boom(now=None):
        raise common.FetchError("blocked")

    monkeypatch.setitem(config.BY_ID["ci_debt"], "fetch", boom)
    build.run(NOW)
    status, site = load(tmp)
    assert status["series"]["ci_debt"]["status"] == "unavailable"
    assert site["series"]["ci_debt"]["values"] == []
    assert status["last_successful_refresh"] is None
