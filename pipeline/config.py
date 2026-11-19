"""Series registry: one entry per series, including everything the dashboard
caption block needs (units, frequency, source link, transformation)."""
from __future__ import annotations

from . import sources as S
from . import transforms as T
from .common import PEG

ECB = "European Central Bank, Data Portal"
FRED = "FRED, Federal Reserve Bank of St. Louis"
WB = "World Bank, World Development Indicators"
IMF = "IMF, World Economic Outlook via DataMapper"


def wb_link(ind, ctry="CI"):
    return f"https://data.worldbank.org/indicator/{ind}?locations={ctry}"


def imf_link(ind):
    return f"https://www.imf.org/external/datamapper/{ind}@WEO/CIV"


# Raw series: fetched from a primary source.
RAW = [
    dict(id="eurusd", title="EUR/USD reference rate", freq="daily", unit="USD per 1 EUR (up = euro stronger)",
         source=ECB, series_id="EXR.D.USD.EUR.SP00.A", url="https://data.ecb.europa.eu/data/datasets/EXR/EXR.D.USD.EUR.SP00.A",
         fetch=S.fetch_eurusd, min_rows=4000, lo=0.8, hi=1.7, transform="None, as published (ECB 14:15 CET reference rate)."),
    dict(id="cocoa_usd", title="Cocoa price", freq="monthly", unit="USD per metric tonne",
         source=FRED + " (IMF Primary Commodity Prices)", series_id="PCOCOUSDM", url="https://fred.stlouisfed.org/series/PCOCOUSDM",
         fetch=S.fetch_fred("PCOCOUSDM"), min_rows=200, lo=300, hi=40000, transform="None, as published (monthly average)."),
    dict(id="ci_cpi_idx", title="Côte d'Ivoire CPI index (RER input)", freq="annual", unit="Index, 2010 = 100",
         source=WB, series_id="FP.CPI.TOTL (CIV)", url=wb_link("FP.CPI.TOTL"),
         fetch=S.fetch_wb("FP.CPI.TOTL", "CIV"), min_rows=12, lo=30, hi=500, lag_limit_days=730,
         transform="None, as published (annual average)."),
    dict(id="us_cpi_idx", title="US CPI index (RER input)", freq="annual", unit="Index, 2010 = 100",
         source=WB, series_id="FP.CPI.TOTL (USA)", url=wb_link("FP.CPI.TOTL", "US"),
         fetch=S.fetch_wb("FP.CPI.TOTL", "USA"), min_rows=12, lo=30, hi=500, lag_limit_days=730,
         transform="None, as published (annual average)."),
    dict(id="ci_infl", title="Headline CPI inflation", freq="annual", unit="% year on year (annual average)",
         source=WB, series_id="FP.CPI.TOTL.ZG (CIV)", url=wb_link("FP.CPI.TOTL.ZG"),
         fetch=S.fetch_wb("FP.CPI.TOTL.ZG", "CIV"), min_rows=12, lo=-10, hi=40, lag_limit_days=730,
         transform="None, as published."),
    dict(id="ci_trade_bal", title="External balance on goods and services", freq="annual", unit="% of GDP",
         source=WB, series_id="NE.RSB.GNFS.ZS (CIV)", url=wb_link("NE.RSB.GNFS.ZS"),
         fetch=S.fetch_wb("NE.RSB.GNFS.ZS", "CIV"), min_rows=10, lo=-40, hi=40, lag_limit_days=730,
         transform="None, as published. Goods AND services (not goods only): used as the nearest available series."),
    dict(id="ci_gdp_growth", title="Real GDP growth", freq="annual", unit="% year on year",
         source=IMF, series_id="NGDP_RPCH", url=imf_link("NGDP_RPCH"),
         fetch=S.fetch_imf("NGDP_RPCH"), min_rows=12, lo=-20, hi=30, lag_limit_days=730,
         transform="None, as published. Years from the current year on are IMF projections (flagged)."),
    dict(id="ci_gov_bal", title="General government net lending/borrowing", freq="annual", unit="% of GDP (negative = deficit)",
         source=IMF, series_id="GGXCNL_NGDP", url=imf_link("GGXCNL_NGDP"),
         fetch=S.fetch_imf("GGXCNL_NGDP"), min_rows=12, lo=-30, hi=20, lag_limit_days=730,
         transform="None, as published. Years from the current year on are IMF projections (flagged)."),
    dict(id="ci_debt", title="General government gross debt", freq="annual", unit="% of GDP",
         source=IMF, series_id="GGXWDG_NGDP", url=imf_link("GGXWDG_NGDP"),
         fetch=S.fetch_imf("GGXWDG_NGDP"), min_rows=12, lo=5, hi=200, lag_limit_days=730,
         transform="None, as published. Years from the current year on are IMF projections (flagged)."),
]

# Derived series: computed from raw inputs, never fetched.
DERIVED = [
    dict(id="xof_usd", title="XOF per USD (derived)", freq="daily", unit="XOF per 1 USD (up = XOF weaker)",
         inputs=["eurusd"], compute=lambda d: T.xof_per_usd(d["eurusd"]), min_rows=4000, lo=300, hi=900,
         source="Derived from ECB EUR/USD and the legal parity of 655.957 XOF per EUR", series_id="derived", url="https://data.ecb.europa.eu/data/datasets/EXR/EXR.D.USD.EUR.SP00.A",
         transform=f"XOF/USD = {PEG} / EURUSD. The XOF/EUR line is the fixed legal parity, not a market quote."),
    dict(id="rer", title="Real exchange rate vs USD", freq="annual", unit=f"Index, {T.BASE_YEAR} = 100 (up = XOF real depreciation)",
         inputs=["xof_usd", "ci_cpi_idx", "us_cpi_idx"],
         compute=lambda d: T.real_exchange_rate(d["xof_usd"], d["ci_cpi_idx"], d["us_cpi_idx"]),
         min_rows=10, lo=40, hi=250, lag_limit_days=730,
         source="Derived from ECB EUR/USD and World Bank CPI (CIV, USA)", series_id="derived", url=wb_link("FP.CPI.TOTL"),
         transform=f"RER = (S x P*/P) rebased so {T.BASE_YEAR} = 100. S = annual mean XOF per USD (years with >= 200 daily obs), "
                   "P* = US CPI, P = Ivorian CPI. Only years present in all inputs."),
    dict(id="cocoa_xof", title="Cocoa price in XOF (derived)", freq="monthly", unit="XOF million per tonne",
         inputs=["cocoa_usd", "xof_usd"], compute=lambda d: T.cocoa_in_xof(d["cocoa_usd"], d["xof_usd"]),
         min_rows=200, lo=0.1, hi=60,
         source="Derived from FRED PCOCOUSDM and ECB EUR/USD", series_id="derived", url="https://fred.stlouisfed.org/series/PCOCOUSDM",
         transform="Cocoa XOF/t = cocoa USD/t x monthly mean XOF/USD (months with >= 15 daily obs), divided by 1e6."),
]

ALL = RAW + DERIVED
BY_ID = {s["id"]: s for s in ALL}

# Series we cannot provide. Shown on the dashboard as explicit gaps.
UNAVAILABLE = [
    dict(id="bceao_rate", title="BCEAO policy rate",
         why="No machine-readable BCEAO API was found and the host is blocked from the build sandbox. Rate changes appear only in press releases.",
         fallback="Manual, source-linked entries in data/manual/bceao_policy_rate.csv (not yet populated).",
         link="https://www.bceao.int"),
    dict(id="civ_10y", title="Côte d'Ivoire 10-year yield and spread over the Bund",
         why="No free, licence-clean daily 10-year series. Auction yields on UMOA-Titres are the nearest primary data but have no stable API.",
         fallback="Export UMOA-Titres auction results by hand, or license a data feed; the Bund leg is available from FRED (IRLTLT01DEM156N).",
         link="https://www.umoatitres.org"),
    dict(id="core_cpi", title="Core CPI inflation",
         why="No core CPI series for Côte d'Ivoire was found in the primary sources used here.",
         fallback="None used. No proxy is shown, because a mislabelled proxy would mislead.",
         link="https://www.ins.ci"),
    dict(id="fx_debt_share", title="Share of public debt in foreign currency",
         why="Published only in IMF/World Bank debt sustainability reports and the national debt office bulletins, not as an API series.",
         fallback="Read from the latest IMF Article IV / DSA by hand.",
         link="https://www.imf.org/en/Countries/CIV"),
]
