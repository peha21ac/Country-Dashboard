"""Hand-entered series. Every row must carry a source link; nothing is inferred."""
from __future__ import annotations

import pandas as pd

from .common import ROOT, FetchError, ValidationError, make_df

MANUAL = ROOT / "data" / "manual" / "bceao_policy_rate.csv"
REQUIRED = {"date", "min_bid_rate_pct", "marginal_rate_pct", "precision", "kind", "source_url"}


def load_policy_rate(column: str):
    def _fetch(now=None) -> pd.DataFrame:
        if not MANUAL.exists():
            raise FetchError(f"{MANUAL.name} not found")
        df = pd.read_csv(MANUAL)
        if not REQUIRED <= set(df.columns):
            raise ValidationError(f"manual file lacks columns: {sorted(REQUIRED - set(df.columns))}")
        urls = df["source_url"].fillna("").astype(str).str.strip()
        if (~urls.str.startswith("http")).any():
            raise ValidationError("every manual row needs an http(s) source_url")
        if not set(df["kind"]) <= {"change", "confirmed"}:
            raise ValidationError("kind must be 'change' or 'confirmed'")
        if not set(df["precision"]) <= {"day", "month"}:
            raise ValidationError("precision must be 'day' or 'month'")
        return make_df(df["date"], df[column])

    return _fetch
