# Côte d'Ivoire: keep the CFA peg or float?

An auto-refreshing dashboard of public indicators for judging the peg of the West African CFA franc (XOF) to the euro (1 EUR = 655.957 XOF).

**Live dashboard:** `https://peha21ac.github.io/Country-Dashboard/` (after GitHub Pages is switched on, see below)
**Methodology and limitations:** `methodology.html` on the same site.

## What it shows

| Chart | Series | Source | Frequency |
|---|---|---|---|
| Nominal exchange rate | EUR/USD; XOF per USD (derived); fixed parity | ECB Data Portal `EXR.D.USD.EUR.SP00.A` | Daily |
| Real exchange rate vs USD | Derived from the above and CPI | World Bank `FP.CPI.TOTL` (CIV, USA) | Annual |
| Cocoa | USD per tonne; XOF per tonne (derived) | FRED `PCOCOUSDM` | Monthly |
| External balance | Goods and services, % of GDP | World Bank `NE.RSB.GNFS.ZS` | Annual |
| Inflation | Headline CPI, % y/y | World Bank `FP.CPI.TOTL.ZG` | Annual |
| Public finances | Net lending/borrowing, gross debt, % of GDP | IMF DataMapper `GGXCNL_NGDP`, `GGXWDG_NGDP` | Annual |
| Real GDP growth | % y/y | IMF DataMapper `NGDP_RPCH` | Annual |

Not available (shown on the dashboard as gaps, never estimated): BCEAO policy rate, Côte d'Ivoire 10-year yield and Bund spread, core CPI, foreign-currency share of public debt.

## How the refresh works

`.github/workflows/refresh.yml` runs daily (06:17 UTC), on manual dispatch and on pushes to `main`:

1. Run the unit tests.
2. `python -m pipeline.build` fetches each series, validates it, writes `data/*.csv` and `data/status.json`, derives the computed series and writes `site/data.json`.
3. Commit changed data back to the repository, so the last good values survive a failed run.
4. Deploy `site/` to GitHub Pages.
5. If any series failed, the run is marked failed after deploying, so you get an email.

**Two timestamps, kept apart.** *Last successful refresh* only moves when every series updated. *Latest observation* is read from each series' own data.

**Failure handling.** A failed fetch or failed sanity check keeps the last good CSV and marks the series stale with its last good date. Derived series inherit staleness from their inputs. Warnings show when data is older than its expected release lag.

## One-time setup

In the repository, open **Settings → Pages** and set **Source** to **GitHub Actions**. Then run the workflow once from the **Actions** tab.

## Run locally

```bash
pip install -r requirements.txt
python -m pytest -q          # tests use synthetic data only
python -m pipeline.build     # needs internet access to the four data hosts
python -m http.server -d site 8000
```

## Verification status

The fetchers follow the documented API formats and are unit-tested on synthetic data. They were written in an environment that could not reach the data hosts, so the first real run is the first test against live responses. Check the first Actions run and the **Data status** section of the dashboard.

## Adding or changing a series

Add an entry to `RAW` or `DERIVED` in `pipeline/config.py` (units, frequency, source link, plausible range, transformation text) and a chart in `site/app.js`. Captions, the status table and the methodology table are generated from the registry.

## Data terms

Data belongs to the ECB, FRED/IMF, the World Bank and the IMF and is used under their terms for public data. Nothing is scraped. BCEAO, UMOA-Titres and INS were not used because they offer no API.
