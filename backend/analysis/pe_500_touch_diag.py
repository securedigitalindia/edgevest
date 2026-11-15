"""Every 500-multiple touch of NIFTY (5-min spot within BAND pts) -> sell 1 PE at that level (next-month expiry),
buy 3 PE GAP lower (month-after expiry). No exit rule: mark-to-market daily to sell expiry / end of data. Writes JSON for the artifact."""
import sqlite3, datetime as dt, collections, json, sys
SIDE = sys.argv[2] if len(sys.argv) > 2 else "PE"   # PE: buy GAP below; CE: buy GAP above
DB = "data/drishti.db"; BAND = 50; RESET = 100; GAP = 1000; BUY = 3
con = sqlite3.connect(DB)
def ist(ts): return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") + dt.timedelta(hours=5, minutes=30)
snaps = con.execute("select ts, max(spot_ltp) from option_chain_5m where symbol='NIFTY50' and spot_ltp>0 group by ts order by ts").fetchall()
snaps = [(ts, ist(ts), sp) for ts, sp in snaps]
bday = collections.defaultdict(list)
for ts, t, sp in snaps: bday[t.date()].append((ts, t, sp))
M = sorted(r[0] for r in con.execute("select distinct expiry_date from option_chain_5m where symbol='NIFTY50' and expiry_type in ('monthly','quarterly')"))
def mexp(y, m):
    c = [e for e in M if e[:7] == f"{y}-{m:02d}"]; return c[-1] if c else None
def leg(ts, e, k):   # ltp, oi, and how many of the previous 6 snapshots (30 min) quoted the identical ltp
    r = con.execute(f"select ltp, oi from option_chain_5m where symbol='NIFTY50' and ts=? and expiry_date=? and strike=? and opt_type='{SIDE}' and ltp>0", (ts, e, k)).fetchone()
    if not r: return None
    h = [x[0] for x in con.execute(f"select ltp from option_chain_5m where symbol='NIFTY50' and ts<? and expiry_date=? and strike=? and opt_type='{SIDE}' order by ts desc limit 6", (ts, e, k))]
    return dict(ltp=r[0], oi=r[1], same=sum(1 for v in h if v == r[0]), n=len(h))
def px(ts, e, k):
    r = con.execute(f"select ltp from option_chain_5m where symbol='NIFTY50' and ts=? and expiry_date=? and strike=? and opt_type='{SIDE}' and ltp>0", (ts, e, k)).fetchone()
    return r[0] if r else None
idx = {ts: i for i, (ts, _, _) in enumerate(snaps)}
trades, last_ev = [], {}
for i, (ts, t, sp) in enumerate(snaps):
    L = round(sp / 500) * 500; kind = "band"
    if abs(sp - L) > BAND and i > 0:   # gap / fast move: spot jumped across a 500 level between two snapshots
        ps = snaps[i - 1][2]; lv = [k for k in range(int(min(ps, sp) // 500 + 1) * 500, int(max(ps, sp)) + 1, 500) if min(ps, sp) < k <= max(ps, sp)]
        if lv: L = min(lv, key=lambda k: abs(k - sp)); kind = "gap"
    if kind == "band" and abs(sp - L) > BAND: 
        for k in list(last_ev): 
            if abs(sp - k) > RESET: last_ev.pop(k)
        continue
    if L in last_ev: continue
    if not (9 * 60 + 20 <= t.hour * 60 + t.minute <= 15 * 60 + 25): continue
    last_ev[L] = ts
    y, m = t.year, t.month
    sy, sm = (y, m + 1) if m < 12 else (y + 1, 1); by, bm = (sy, sm + 1) if sm < 12 else (sy + 1, 1)
    se, be = mexp(sy, sm), mexp(by, bm); K, KB = L, (L - GAP if SIDE == 'PE' else L + GAP)
    tr = dict(side=SIDE, kind=kind, dist=round(sp - L, 1), ts=t.strftime("%Y-%m-%d %H:%M"), date=t.strftime("%Y-%m-%d"), spot=sp, level=L, K=K, KB=KB, sell_exp=se, buy_exp=be, first2w=t.day <= 14)
    if not se or not be: tr["skip"] = "expiry not in data"; trades.append(tr); continue
    s0 = b0 = None; used = ts
    for j in range(i, min(i + 4, len(snaps))):
        s0, b0 = px(snaps[j][0], se, K), px(snaps[j][0], be, KB)
        if s0 and b0: used = snaps[j][0]; break
    if not (s0 and b0): tr["skip"] = "strike not quoted"; trades.append(tr); continue
    ls, lb = leg(used, se, K), leg(used, be, KB)
    tr.update(oi_s=ls["oi"], oi_b=lb["oi"], same_s=ls["same"], same_b=lb["same"], hist_s=ls["n"], hist_b=lb["n"], s0=s0, b0=b0, debit=round(BUY * b0 - s0, 2), entry_lag_min=(idx[used] - i) * 5, path=[])
    for d in sorted(bday):
        if d <= t.date() or d.isoformat() > se: continue
        x = [q for q in bday[d] if q[1].hour * 60 + q[1].minute <= 15 * 60 + 20]
        if not x: continue
        q = x[-1]; s, b = px(q[0], se, K), px(q[0], be, KB)
        a_, b_ = leg(q[0], se, K), leg(q[0], be, KB)
        stale = bool((a_ and a_['same'] >= 6) or (b_ and b_['same'] >= 6))
        if s is None and d.isoformat() == se: s = max(K - q[2], 0) if SIDE == 'PE' else max(q[2] - K, 0)
        if s is None or b is None: continue
        tr["path"].append([d.isoformat(), round(q[2], 1), round(s, 1), round(b, 1), round(s0 - s + BUY * (b - b0), 1), int(stale)])
    trades.append(tr)
json.dump(dict(band=BAND, gap=GAP, buy_lots=BUY, data_from=snaps[0][1].strftime("%Y-%m-%d"), data_to=snaps[-1][1].strftime("%Y-%m-%d %H:%M"), trades=trades), open(sys.argv[1], "w"))
ok = [x for x in trades if "skip" not in x and x["path"]]
print(len(trades), "touch events;", len(ok), "priced with a path;", sum("skip" in x for x in trades), "skipped")
for x in trades: print(x["ts"], x["kind"], x["dist"], x["level"], round(x["spot"]), x.get("skip") or f"debit {x['debit']} pnl_end {x['path'][-1][4] if x['path'] else None} ({x['path'][-1][0] if x['path'] else '-'})")
