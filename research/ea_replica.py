"""Bar-by-bar replica of EvalPassMomentum.mq5's signal logic (independent of strategies.noise_area).

It walks M1 bars exactly like the EA's OnNewBar(): builds the day model from past bars at the
first check of each New York day, then evaluates exits/entries at scheduled checks. Emitted
intents are executed with the same bt engine so trade lists can be compared 1:1.
"""
import numpy as np
import pandas as pd

from bt import Intents, Market


def replica_intents(mkt: Market, lookback=30, band_mult=1.5, check_every=30, use_vwap=False,
                    stop_mode="sigma", stop_sigma=1.0, min_stop_sigma=0.25, tp_r=2.5,
                    open_min=570, close_min=960, first_check=600, last_entry=930, flat_min=955,
                    exit_mode="band") -> Intents:
    s = mkt.sig
    n = len(s)
    it = Intents(n)
    t = pd.DatetimeIndex(s.time).tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
    ny_day = (t.values.astype("datetime64[D]").astype(np.int64))
    ny_min = (t.hour * 60 + t.minute).values
    close = s.bc.values; high = s.bh.values; low = s.bl.values; vol = s.n.values.astype(float)
    sess_len = close_min - open_min
    in_sess = (ny_min >= open_min) & (ny_min < close_min)
    sess_idx = np.flatnonzero(in_sess)

    day_id = -1; ready = False; day_open = prev_close = 0.0; sigma = None
    pos = 0  # position state as the EA would see it, driven by our own intents (no stops simulated)
    for i in range(n):
        if not in_sess[i]:
            continue
        m = ny_min[i] - open_min
        today = ny_day[i]
        if today != day_id:
            ready = False; day_id = today
        clk = ny_min[i]
        if not (((clk + 1) % check_every == 0) and (clk + 1 >= first_check)):
            continue
        if not ready:
            # --- BuildDay(): past sessions from history up to bar i ---
            lo = np.searchsorted(sess_idx, max(0, i - (lookback + 12) * 1440))
            hi = np.searchsorted(sess_idx, i, side="right")
            idx = sess_idx[lo:hi]
            d = ny_day[idx]
            past = idx[d < today]
            todays = idx[d == today]
            if len(todays) == 0:
                continue
            today_open = close[todays[0]]
            days, starts = np.unique(ny_day[past], return_index=True)
            if len(days) < lookback:
                continue
            grid = np.zeros((len(days), sess_len))
            opens = close[past[starts]]
            row = np.searchsorted(days, ny_day[past])
            grid[row, ny_min[past] - open_min] = close[past]
            for r_ in range(len(days)):
                last = opens[r_]
                for k in range(sess_len):
                    if grid[r_, k] == 0.0:
                        grid[r_, k] = last
                    else:
                        last = grid[r_, k]
            use = slice(len(days) - lookback, len(days))
            sigma = np.mean(np.abs(grid[use] / opens[use, None] - 1.0), axis=0)
            prev_close = grid[-1, -1]
            day_open = today_open
            ready = True
        c = close[i]
        sig = sigma[m] * band_mult
        upper = max(day_open, prev_close) * (1 + sig)
        lower = min(day_open, prev_close) * (1 - sig)
        vwap = 0.0
        if use_vwap:
            j0 = i - m
            seg = slice(max(0, j0 - 5), i + 1)
            sel = (ny_day[seg] == today) & in_sess[seg]
            tp_px = ((high[seg] + low[seg] + close[seg]) / 3)[sel]
            w = vol[seg][sel]
            vwap = (tp_px * w).sum() / w.sum() if w.sum() > 0 else 0.0
        long_stop = max(upper, vwap) if (use_vwap and vwap > 0) else upper
        short_stop = min(lower, vwap) if (use_vwap and vwap > 0) else lower
        # exits (signal form: engine only acts on them if it holds that side)
        xl = (c < long_stop) if exit_mode == "band" else ((c < lower) if exit_mode == "opposite" else False)
        xs = (c > short_stop) if exit_mode == "band" else ((c > upper) if exit_mode == "opposite" else False)
        it.ex[i] = 2 if (xl and xs) else (1 if xl else (-1 if xs else 0))
        if clk + 1 > last_entry:
            continue
        sig_px = sigma[m] * day_open
        if c > upper:
            it.ent[i] = 1
            it.sl[i] = stop_sigma * sig_px if stop_mode == "sigma" else max(c - long_stop, min_stop_sigma * sig_px)
        elif c < lower:
            it.ent[i] = -1
            it.sl[i] = stop_sigma * sig_px if stop_mode == "sigma" else max(short_stop - c, min_stop_sigma * sig_px)
        it.tp[i] = tp_r * it.sl[i] if (tp_r > 0 and it.ent[i] != 0) else 0.0
    clk_all = ny_min
    it.ex[(clk_all >= flat_min) | (clk_all < open_min)] = 2
    return it
