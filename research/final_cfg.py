"""The selected configuration (mirrored by the EA defaults)."""
STRAT = dict(lookback=30, vol_mult=2.0, check_every=30, sl_mode="sig", sl_sigma=1.0, use_vwap=False,
             tp_r=2.5, exit_mode="none")
MGMT = dict(be_trig=1.5, be_off=0.1, max_per_day=3)
