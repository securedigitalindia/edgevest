"""
Day-view engine (docs/prd/strategy-day-view.md). Pure functions over a sqlite
connection to option_chain_5m — no Flask. For one entry day it finds the entry
(first touch of a multiple of `step`), prices every leg for every compared entry
strike over a window (7 calendar days before .. 30 after the entry day), and
returns a JSON-ready dict. Used by routes (live dashboard) and by
analysis/strategy_viewer/build_data.py (shareable artifact) — one copy of the logic.

Prices are last-traded from option_chain_5m (no bid/ask). The newest snapshot of
"today" is as fresh as the poller's ~5-min chain capture.
"""
import datetime as dt
import time
from .day_strategies import DAY_STRATEGIES

PRE, POST = 7, 30           # calendar days kept before / after the entry day
ENTRY_WAIT_SNAPS = 12       # wait up to 1 hour for a leg's first trade after the touch
_IST = dt.timedelta(hours=5, minutes=30)


def get(sid: str):
    return DAY_STRATEGIES.get(sid)


def _ist(ts: str) -> dt.datetime:
    return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") + _IST


def _utc(d: dt.date, end: bool = False) -> str:
    return (dt.datetime.combine(d, dt.time(0, 0)) - _IST + (dt.timedelta(days=1) if end else dt.timedelta())).strftime("%Y-%m-%dT%H:%M:%SZ")


_EXP_CACHE: dict = {}
_LIST_CACHE: dict = {}


def _monthly_expiries(conn, sym):
    """Monthly/quarterly expiry dates. GROUP BY on the (symbol, expiry_type, expiry_date) index: 0.2 s vs 12 s for DISTINCT; cached 10 min."""
    hit = _EXP_CACHE.get(sym)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    out = sorted({r[0] for typ in ("monthly", "quarterly") for r in conn.execute(
        "SELECT expiry_date FROM option_chain_5m INDEXED BY idx_option_chain_5m_sym_type_expiry WHERE symbol=? AND expiry_type=? GROUP BY expiry_date", (sym, typ))})
    _EXP_CACHE[sym] = (time.time(), out)
    return out


def _session_snaps(conn, symbol, d0: dt.date, d1: dt.date):
    """[(ts, ist_dt, spot)] for IST dates d0..d1 inclusive, inside 09:15-15:30 IST.
    Distinct snapshot times come from the (symbol, ts) index alone, then the spot is MAX(spot_ltp) of that snapshot (the chain stores a few slightly
    different spot values within one capture; max is the convention every published artifact used — keep it so numbers agree)."""
    out = []
    tss = [r[0] for r in conn.execute("SELECT DISTINCT ts FROM option_chain_5m WHERE symbol=? AND ts>=? AND ts<? ORDER BY ts",
                                      (symbol, _utc(d0), _utc(d1, end=True)))]
    for ts in tss:
        t = _ist(ts); m = t.hour * 60 + t.minute
        if not (9 * 60 + 15 <= m <= 15 * 60 + 30):
            continue
        r = conn.execute("SELECT MAX(spot_ltp) FROM option_chain_5m WHERE symbol=? AND ts=? AND spot_ltp>0", (symbol, ts)).fetchone()
        if r and r[0]:
            out.append((ts, t, r[0]))
    return out


def _find_entry(sp: list, step: int, near: int):
    """First touch of a multiple of `step`: within `near` pts, or a jump through one since the previous snapshot."""
    for i, s in enumerate(sp):
        c = round(s / step) * step
        if abs(s - c) <= near:
            return i, c, "near"
        if i > 0:
            lo, hi = min(sp[i - 1], s), max(sp[i - 1], s)
            lv = [k for k in range(int(lo // step + 1) * step, int(hi) + 1, step) if lo < k <= hi]
            if lv:
                return i, min(lv, key=lambda k: abs(k - s)), "cross"
    return None, None, None


def list_days(conn, sid: str) -> dict:
    """Every captured trading day with its first-touch entry (if it has happened yet). Cached 30 s (a full-history scan)."""
    hit = _LIST_CACHE.get(sid)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    res = _list_days(conn, sid)
    _LIST_CACHE[sid] = (time.time(), res)
    return res


def _list_days(conn, sid: str) -> dict:
    S = DAY_STRATEGIES[sid]; step, near = S["entry"]["step"], S["entry"]["near"]
    by = {}
    for ts, t, sp in _session_snaps(conn, S["symbol"], dt.date(2000, 1, 1), dt.date(2100, 1, 1)):
        by.setdefault(t.date(), []).append((t, sp))
    days = sorted(by)
    latest = days[-1] if days else None
    out = []
    for d in days:
        snaps = by[d]
        if len(snaps) < 40 and d != latest:      # partial historical day = capture outage, skip; today may legitimately be partial
            continue
        ti, L, kind = _find_entry([x[1] for x in snaps], step, near)
        e = dict(date=d.isoformat(), snaps=len(snaps), live=(d == latest))
        if ti is not None and ti <= 72:
            e.update(level=L, time=snaps[ti][0].strftime("%H:%M"), kind=kind)
        out.append(e)
    return dict(days=out, as_of=(max(t for t, _ in by[latest]).strftime("%Y-%m-%d %H:%M IST") if latest else None))


def compute_day(conn, sid: str, date_str: str, variants=None) -> dict | None:
    """Day payload for one entry day. Returns None if the day has no captured snapshots."""
    S = DAY_STRATEGIES[sid]; sym = S["symbol"]; step, near = S["entry"]["step"], S["entry"]["near"]
    variants = variants or S["variants"]
    d = dt.date.fromisoformat(date_str)
    snaps = _session_snaps(conn, sym, d - dt.timedelta(days=PRE + 6), d + dt.timedelta(days=POST))
    by = {}
    for x in snaps: by.setdefault(x[1].date(), []).append(x)
    latest = max(by) if by else None
    if d not in by:
        return None
    days = sorted(k for k in by if len(by[k]) >= 40 or k == d)
    di = days.index(d)
    sn = by[d]; sp = [x[2] for x in sn]; tl = [x[0] for x in sn]

    M = _monthly_expiries(conn, sym)
    def mexp(y, m):
        c = [e for e in M if e[:7] == f"{y}-{m:02d}"]; return c[-1] if c else None
    def expiry(ref):
        k = int(ref.split("+")[1]); y, m = d.year, d.month + k
        return mexp(y + (m - 1) // 12, (m - 1) % 12 + 1)

    def thin(lst, k):    # entry day 5-min, +-2 trading days 15-min, the rest hourly (keeps payloads small)
        return [x for x in lst if (x[1].minute % 15 == 0 if abs(k) <= 2 else x[1].minute == 15)]
    pv = [x for k in range(di) if (d - days[k]).days <= PRE for x in thin(by[days[k]], k - di)]
    nx = [x for k in range(di + 1, len(days)) if (days[k] - d).days <= POST for x in thin(by[days[k]], k - di)]
    seq = pv + sn + nx; off = len(pv); stl = [x[0] for x in seq]

    ti, L, kind = _find_entry(sp, step, near)
    rec = dict(date=date_str, d=[x[1].strftime("%Y-%m-%d") for x in seq], t=[x[1].strftime("%H:%M") for x in seq],
               spot=[round(x[2], 1) for x in seq], day0=off, day1=off + len(sn), touch=None, exps=None,
               live=(d == latest), as_of=max(x[1] for x in snaps).strftime("%Y-%m-%d %H:%M IST"),
               V={v: {} for v in variants})
    if ti is None or ti > 72:
        s = sp[-1]    # waiting for a touch: tell the UI where the nearest levels are
        up = (int(s // step) + 1) * step; dn = int(s // step) * step
        rec["watch"] = dict(spot=round(s, 1), up=up, down=dn, up_dist=round(up - s, 1), down_dist=round(s - dn, 1))
        return rec
    rec["touch"] = dict(i=off + ti, level=L, kind=kind, spot=round(sp[ti], 1), time=sn[ti][1].strftime("%H:%M"))
    exps = [expiry(l["expiry"]) for l in S["legs"]]; rec["exps"] = exps
    if not all(exps):
        return rec

    # One range query per (expiry, option type) over every strike the comparison needs — 4 queries instead of ~42.
    want = {}
    for v in variants:
        for o in S["offs"]:
            for l, e in zip(S["legs"], exps):
                opt = v if l["opt"] == "{opt}" else l["opt"]
                so = l["strike"][v] if isinstance(l["strike"], dict) else l["strike"]
                want.setdefault((e, opt), set()).add(L + o * step + so)
    cache = {}
    for (e, opt), ks in want.items():
        ph = ",".join("?" * len(ks)); per = {k: {} for k in ks}
        for ts, k, l, oi in conn.execute(
                f"SELECT ts, strike, ltp, oi FROM option_chain_5m INDEXED BY idx_option_chain_5m_strike_expiry WHERE symbol=? AND expiry_date=? AND opt_type=? AND strike IN ({ph}) AND ts>=? AND ltp>0",
                (sym, e, opt, *ks, stl[0])):
            per[k][ts] = (l, oi)
        for k, ser_ in per.items():
            cache[(e, k, opt)] = ser_
    def series(e, k, opt):
        return cache.get((e, k, opt), {})
    def why(ts, e, k, opt):
        if not conn.execute("SELECT 1 FROM option_chain_5m WHERE symbol=? AND ts=? AND expiry_date=? LIMIT 1", (sym, ts, e)).fetchone():
            return f"expiry {e} is not in the stored chain"
        r = conn.execute("SELECT ltp FROM option_chain_5m WHERE symbol=? AND ts=? AND expiry_date=? AND strike=? AND opt_type=?", (sym, ts, e, k, opt)).fetchone()
        return f"strike {int(k)} is outside the stored strike range" if r is None else f"strike {int(k)} has no trade yet (price 0)"
    def stale(ser, i):   # same price as each of the previous 6 snapshots
        v = ser.get(tl[i])
        return int(bool(v) and i >= 6 and all(ser.get(tl[j], (None,))[0] == v[0] for j in range(i - 6, i)))

    for v in variants:
        for o in S["offs"]:
            A = L + o * step; legs = []
            for l, e in zip(S["legs"], exps):
                opt = v if l["opt"] == "{opt}" else l["opt"]
                so = l["strike"][v] if isinstance(l["strike"], dict) else l["strike"]
                legs.append(dict(role=l["role"], qty=l["qty"], opt=opt, strike=A + so, exp=e, ser=series(e, A + so, opt)))
            j0 = next((j for j in range(ti, min(ti + ENTRY_WAIT_SNAPS, len(sn))) if all(tl[j] in g["ser"] for g in legs)), None)
            if j0 is None:
                bad = [f"{g['role'].lower()} leg: " + why(tl[ti], g["exp"], g["strike"], g["opt"]) for g in legs if tl[ti] not in g["ser"]]
                waiting = d == latest and ti + ENTRY_WAIT_SNAPS > len(sn)   # today: may still get its first trade
                rec["V"][v][str(o)] = dict(A=A, skip="; ".join(bad) or "no price within 1 hour of the touch", pending=bool(waiting))
                continue
            rec["V"][v][str(o)] = dict(A=A, j=off + j0, lag=(j0 - ti) * 5, legs=[dict(
                role=g["role"], qty=g["qty"], opt=g["opt"], strike=g["strike"], exp=g["exp"], px0=g["ser"][tl[j0]][0], oi=g["ser"][tl[j0]][1],
                st=stale(g["ser"], j0), px=[(g["ser"].get(t) or (None,))[0] for t in stl]) for g in legs])
    return rec


def is_settled(rec: dict, latest_date: str | None) -> bool:
    """A past day is final once the data runs POST days past it (nothing later can change its window)."""
    if rec.get("live") or not latest_date:
        return False
    return (dt.date.fromisoformat(latest_date) - dt.date.fromisoformat(rec["date"])).days >= POST
