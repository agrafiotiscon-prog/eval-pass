"""Daily regime features (known before the session starts) and entry filters built on them."""
import numpy as np
import pandas as pd

from bt import Intents, Market


def daily_features(mkt: Market, clock="ny_min", open_min=570, close_min=960) -> pd.DataFrame:
    """One row per session date; every column only uses information up to the PREVIOUS session."""
    s = mkt.sig
    clk = s[clock].values
    date = s.ny_date.values if clock == "ny_min" else s.day.values
    rth = (clk >= open_min) & (clk < close_min)
    d = pd.DataFrame({"date": date[rth], "o": s.bo.values[rth], "h": s.bh.values[rth], "l": s.bl.values[rth], "c": s.bc.values[rth]})
    g = d.groupby("date").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    ret = np.log(g.c).diff()
    f = pd.DataFrame(index=g.index)
    for n in (10, 20, 50, 100, 200):
        f[f"above_ma{n}"] = (g.c > g.c.rolling(n, min_periods=n).mean()).astype(float).where(g.c.rolling(n).count() >= n)
    f["vol20"] = ret.rolling(20).std() * np.sqrt(252)
    f["vol_pct"] = f.vol20.rolling(252, min_periods=120).rank(pct=True)
    f["dd20"] = g.c / g.c.rolling(20).max() - 1
    f["ret5"] = g.c / g.c.shift(5) - 1
    f["eff"] = (g.c - g.o).abs() / (g.h - g.l)
    f["eff10"] = f.eff.rolling(10).mean()
    f["eff_pct"] = f.eff10.rolling(252, min_periods=120).rank(pct=True)
    return f.shift(1)          # known at the start of each session


def apply_filter(mkt: Market, it: Intents, feats: pd.DataFrame, allow_long: pd.Series, allow_short: pd.Series,
                 clock="ny_min") -> Intents:
    date = mkt.sig.ny_date.values if clock == "ny_min" else mkt.sig.day.values
    al = pd.Series(allow_long.values, index=feats.index).reindex(date).fillna(True).values.astype(bool)
    ash = pd.Series(allow_short.values, index=feats.index).reindex(date).fillna(True).values.astype(bool)
    it.ent[(it.ent == 1) & ~al] = 0
    it.ent[(it.ent == -1) & ~ash] = 0
    return it
