"""Sell 1x PE (next-month expiry) / buy 3x PE 1000 lower (month-after expiry), entered in the first 14 days of a month
when spot is within TOL points of a 500 multiple. No exit rule: mark-to-market to sell-leg expiry. Local option_chain_5m only."""
import sqlite3, datetime as dt, collections
DB = "data/drishti.db"; TOL = 100; GAP = 1000; BUY_LOTS = 3
con = sqlite3.connect(DB)
def ist(ts): return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") + dt.timedelta(hours=5, minutes=30)
rows = con.execute("select ts,spot_ltp from option_chain_5m where symbol='NIFTY50' and opt_type='PE' group by ts").fetchall()
snaps = collections.defaultdict(list)   # IST date -> [(ts, hhmm, spot)]
for ts, spot in rows:
    t = ist(ts); snaps[t.date()].append((ts, t.hour * 100 + t.minute, spot))
days = sorted(snaps)
def snap(day, hhmm, after=True):
    c = [s for s in snaps[day] if (s[1] >= hhmm if after else s[1] <= hhmm)]
    return (min(c, key=lambda s: s[1]) if after else max(c, key=lambda s: s[1])) if c else None
def px(ts, expiry, strike):
    r = con.execute("select ltp from option_chain_5m where symbol='NIFTY50' and ts=? and expiry_date=? and strike=? and opt_type='PE' and ltp>0", (ts, expiry, strike)).fetchone()
    return r[0] if r else None
def monthlies():  # expiry dates that are monthly/quarterly (month-end style)
    return sorted(r[0] for r in con.execute("select distinct expiry_date from option_chain_5m where symbol='NIFTY50' and expiry_type in ('monthly','quarterly')"))
M = monthlies()
def month_expiry(y, m):
    c = [e for e in M if e[:7] == f"{y}-{m:02d}"]; return c[-1] if c else None
out = []
for d in days:
    if d.day > 14: continue
    e = snap(d, 930)
    if not e: continue
    ts, _, spot = e
    k500 = round(spot / 500) * 500
    if abs(spot - k500) > TOL: continue
    y, m = d.year, d.month
    sy, sm = (y, m + 1) if m < 12 else (y + 1, 1); by, bm = (sy, sm + 1) if sm < 12 else (sy + 1, 1)
    se, be = month_expiry(sy, sm), month_expiry(by, bm)
    K = round(spot / 50) * 50; KB = K - GAP
    row = dict(date=d, spot=spot, K=K, KB=KB, sell_exp=se, buy_exp=be)
    if not se or not be: row["note"] = f"no data for {'sell' if not se else 'buy'} expiry"; out.append(row); continue
    s0, b0 = px(ts, se, K), px(ts, be, KB)
    if s0 is None or b0 is None: row["note"] = "strike not quoted at entry"; out.append(row); continue
    row.update(s0=s0, b0=b0, credit=s0 - BUY_LOTS * b0)
    path = []
    for dd in days:
        if dd <= d or dd.isoformat() > se: continue
        x = snap(dd, 1520, after=False)
        if not x: continue
        s, b = px(x[0], se, K), px(x[0], be, KB)
        if s is None and dd.isoformat() == se: s = max(K - x[2], 0)   # sell leg expired: intrinsic
        if s is None or b is None: continue
        path.append((dd, x[2], s0 - s + BUY_LOTS * (b - b0)))
    row["path"] = path; out.append(row)
print(f"{'entry':10} {'spot':>8} {'sellK':>6} {'buyK':>6} {'sell':>7} {'buy':>7} {'net debit(pts)':>14} | {'MTM@end':>9} {'min':>8} {'max':>8} {'last day':>10} {'spot@end':>9}")
for r in out:
    if "note" in r: print(r["date"], f"{r['spot']:.0f}", r["K"], r["KB"], "SKIP:", r["note"]); continue
    p = r["path"]
    if not p: print(r["date"], "no forward data"); continue
    v = [x[2] for x in p]
    print(f"{r['date']} {r['spot']:8.0f} {r['K']:6.0f} {r['KB']:6.0f} {r['s0']:7.1f} {r['b0']:7.1f} {-r['credit']:14.1f} | {v[-1]:9.1f} {min(v):8.1f} {max(v):8.1f} {str(p[-1][0]):>10} {p[-1][1]:9.0f}  (sell exp {r['sell_exp']}, buy exp {r['buy_exp']})")
