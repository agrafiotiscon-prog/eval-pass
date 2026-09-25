"""Per-instrument strategy library + walk-forward selection.

Every config in the library is backtested once over the whole history (M1 bid/ask execution,
conservative same-bar handling). Then, for each 6-month test window, the config(s) with the best
score on the preceding 3 years are selected and ONLY their trades inside the test window are kept.
The stitched test-window trades are an honest out-of-sample record of "what the selector would
have traded".

Usage: python wf.py SYMBOL [start] [end]
"""
import itertools
import multiprocessing as mp
import os
import sys
import time

import numpy as np
import pandas as pd

from bt import Market, run
from strategies import (breakout, mean_reversion, noise_area, orb, swing_breakout)

OUT = "/tmp/data/wf"

NY = ("ny_min", 570, 960)
SESS = {
    "USATECHIDXUSD": dict(noise=[NY], orb=[("ny_min", 570)], bo=[("ny_min", 570, 720), ("ny_min", 720, 960), ("ny_min", 570, 960)],
                          mr=[("ny_min", 600, 900), ("ny_min", 1080, 1380)]),
    "XAUUSD": dict(noise=[NY, ("ny_min", 500, 810), ("ldn_min", 480, 990)], orb=[("ldn_min", 480), ("ny_min", 500), ("ny_min", 570)],
                   bo=[("ldn_min", 420, 660), ("ny_min", 500, 720), ("ldn_min", 420, 1020)], mr=[("utc_min", 0, 360), ("ny_min", 720, 960), ("utc_min", 1140, 1260)]),
    "EURUSD": dict(noise=[("ldn_min", 480, 990), ("ny_min", 480, 1020)], orb=[("ldn_min", 480), ("ny_min", 500)],
                   bo=[("ldn_min", 420, 660), ("ny_min", 540, 720), ("ldn_min", 420, 1020)], mr=[("utc_min", 0, 360), ("utc_min", 1140, 1260), ("ldn_min", 480, 720)]),
    "GBPUSD": dict(noise=[("ldn_min", 480, 990), ("ny_min", 480, 1020)], orb=[("ldn_min", 480), ("ny_min", 500)],
                   bo=[("ldn_min", 420, 660), ("ny_min", 540, 720), ("ldn_min", 420, 1020)], mr=[("utc_min", 0, 360), ("utc_min", 1140, 1260), ("ldn_min", 480, 720)]),
    "USDJPY": dict(noise=[("utc_min", 0, 360), ("ldn_min", 480, 990), ("ny_min", 480, 1020)], orb=[("utc_min", 0), ("ldn_min", 480), ("ny_min", 500)],
                   bo=[("utc_min", 0, 360), ("ldn_min", 420, 660), ("ldn_min", 420, 1020)], mr=[("utc_min", 0, 360), ("utc_min", 1140, 1260), ("ny_min", 720, 960)]),
}


def configs(sym):
    s = SESS[sym]
    out = []
    for (clk, o, c), lb, vm, ce, sl, tp, part in itertools.product(s["noise"], (20, 30), (1.5, 2.0), (30, 60), (0.75, 1.0), (2.0, 3.0), (0.0, 1.0)):
        sess = dict(clock=clk, open_min=o, close_min=c, first_check=o + 30, last_entry=c - 30, flat_min=c - 5)
        out.append(("noise", "1min", dict(fn="noise", lookback=lb, vol_mult=vm, check_every=ce, sl_mode="sig", sl_sigma=sl,
                                          use_vwap=False, tp_r=tp, exit_mode="none", **sess),
                    dict(be_trig=1.5, be_off=0.1, part_r=part, part_frac=0.5 if part else 0.0, max_per_day=3)))
    for (clk, o), orl, slf, tp, fb, until in itertools.product(s["orb"], (15, 30, 60), (0.5, 1.0), (0.0, 1.5, 2.5), (False, True), (60, 180)):
        out.append(("orb", "1min", dict(fn="orb", tz_col=clk, open_min=o, or_len=orl, sl_frac=slf, tp_r=tp, first_bar_dir=fb,
                                        entry_until=until, flat_min=min(o + 480, 1435)), dict(max_per_day=1)))
    for (clk, a, b), n, sl, trail, tnd in itertools.product(s["bo"], (12, 24, 48), (1.0, 2.0), ((0, 0), (2.0, 1.5)), (0, 100)):
        out.append(("bo", "15min", dict(fn="bo", n=n, sl_atr=sl, clock=clk, start=a, end=b, trend_n=tnd, tp_r=0 if trail[0] else 2.0, flat_after=b + 120),
                    dict(tr_trig=trail[0], tr_dist=trail[1], max_per_day=3)))
    for (clk, a, b), n, k, sl, conf in itertools.product(s["mr"], (12, 24), (2.0, 2.5, 3.0), (1.5, 3.0), (False, True)):
        out.append(("mr", "5min", dict(fn="mr", n=n, k_entry=k, sl_atr=sl, confirm=conf, clock=clk, start=a, end=b),
                    dict(max_hold_min=n * 5 * 2, max_per_day=6)))
    for n, sl, trail, tnd, lo in itertools.product((24, 72, 120, 240), (2.0, 3.0), ((0, 0), (1.0, 1.5), (2.0, 2.0)), (0, 200), (False, True)):
        out.append(("swing", "60min", dict(fn="swing", n=n, atr_n=24, sl_atr=sl, trend_n=tnd, long_only=lo, tp_r=0 if trail[0] else 3.0),
                    dict(tr_trig=trail[0], tr_dist=trail[1], max_per_day=1)))
    return out


MK = {}


def build_intents(m, p):
    p = dict(p)
    fn = p.pop("fn")
    if fn == "noise":
        return noise_area(m, **p)
    if fn == "orb":
        return orb(m, **p)
    if fn == "bo":
        fa = p.pop("flat_after")
        it = breakout(m, **p)
        c = m.sig[p["clock"]].values
        a, b = p["start"], p["end"]
        inside = ((c >= a) & (c < fa)) if a <= b else ((c >= a) | (c < fa))
        it.ex[~inside] = 2
        return it
    if fn == "mr":
        return mean_reversion(m, **p)
    if fn == "swing":
        return swing_breakout(m, **p)
    raise ValueError(fn)


def _work(i_cfg):
    i, (fam, tf, p, mg) = i_cfg
    m = MK[tf]
    try:
        it = build_intents(m, p)
        tr = run(m, it, entry_same_bar_check=True, **mg)
    except Exception as e:  # keep the grid running
        print("ERR", fam, p, e, flush=True)
        return i, None
    return i, tr[["t_in", "t_out", "dir", "R", "mae"]].assign(cfg=i)


def run_grid(sym, start="2012-01-01", end="2026-09-01"):
    global MK
    os.makedirs(OUT, exist_ok=True)
    cfgs = configs(sym)
    t0 = time.time()
    for tf in sorted({c[1] for c in cfgs}):
        MK[tf] = Market(sym, tf, start=start, end=end, exec_res="m1")
    print(f"{sym}: {len(cfgs)} configs, markets loaded in {time.time() - t0:.0f}s", flush=True)
    ctx = mp.get_context("fork")
    with ctx.Pool(int(os.environ.get("WF_WORKERS", "2")), maxtasksperchild=25) as pool:
        res = pool.map(_work, list(enumerate(cfgs)), chunksize=4)
    trades = pd.concat([r for _, r in res if r is not None], ignore_index=True)
    meta = pd.DataFrame([dict(cfg=i, fam=c[0], tf=c[1], params=repr(c[2]), mgmt=repr(c[3])) for i, c in enumerate(cfgs)])
    trades.to_parquet(f"{OUT}/{sym}_trades.parquet")
    meta.to_parquet(f"{OUT}/{sym}_meta.parquet")
    print(f"{sym}: grid done in {time.time() - t0:.0f}s, {len(trades):,} trades", flush=True)
    return trades, meta


def score(tr: pd.DataFrame, min_n=40) -> float:
    if len(tr) < min_n:
        return -np.inf
    r = tr.R.values
    sd = r.std()
    return r.mean() / sd * np.sqrt(len(r)) if sd > 0 else -np.inf


def walk_forward(trades: pd.DataFrame, first_test="2015-01-01", last="2026-09-01", train_years=3, step_months=6,
                 top_k=1, families=None, min_n=40):
    tr = trades if families is None else trades[trades.fam.isin(families)]
    starts = pd.date_range(first_test, last, freq=f"{step_months}MS")
    picks, oos = [], []
    for ts in starts:
        te = ts + pd.DateOffset(months=step_months)
        tr0 = ts - pd.DateOffset(years=train_years)
        train = tr[(tr.t_in >= tr0) & (tr.t_in < ts)]
        sc = train.groupby("cfg").apply(lambda g: score(g, min_n)).sort_values(ascending=False)
        sc = sc[np.isfinite(sc) & (sc > 0)]
        chosen = list(sc.index[:top_k])
        picks.append(dict(test_start=ts, chosen=chosen, scores=list(sc.values[:top_k].round(2))))
        if not chosen:
            continue
        t = tr[tr.cfg.isin(chosen) & (tr.t_in >= ts) & (tr.t_in < te)].copy()
        t["w"] = 1.0 / len(chosen)
        oos.append(t)
    oos = pd.concat(oos, ignore_index=True) if oos else pd.DataFrame(columns=list(tr.columns) + ["w"])
    return oos, pd.DataFrame(picks)


if __name__ == "__main__":
    sym = sys.argv[1]
    a = sys.argv[2] if len(sys.argv) > 2 else "2012-01-01"
    b = sys.argv[3] if len(sys.argv) > 3 else "2026-09-01"
    run_grid(sym, a, b)
