# Manual Strategy CLI (draft/publish)

> **Scope note, 2026-09-06**: this doc's title/original scope was CLI-only, but the addenda below extended the same draft/publish model to the Dashboard's own "New Recommendation" form, added a Draft Strategies admin panel to the frontend, and redesigned the Telegram alerts + added a Share button for the whole `recommended_trades` lifecycle (entry/adjustment/exit). Read every addendum, not just the top locked-decisions section, for the current full picture — this is the single doc of record for all of it, not just the terminal tool.

## Problem

Today the only way to hand-author a `recommended_trades` row is `backend/live/manual_trade.py`'s `add_manual_trade()` — either called from a Python shell/one-off script, or via `POST /api/recommendations/create` (`server.py:662-679`, admin-only). Both paths do the same thing: every leg's price is a required number the admin types in, the row is inserted `status='open'` immediately, and a client-facing Telegram alert (`_send_manual_alert()`) fires in the same call. There is no way to:

- Stage a multi-leg strategy over several steps (e.g. build up legs one at a time, come back later) before it's visible to anyone.
- Auto-fetch a leg's current live price instead of typing it in, the way `live/triggers.py`'s `Nifty500MultipleTrigger` already does for automated entries (`_fetch_prices()` → `live.upstox_client.get_ltp()`).
- Apply the existing `trade_adjustments` machinery (add/replace legs, partial exit, full exit) to a hand-authored trade from the terminal — today that's only reachable via the HTTP `/api/recommendations/<id>/adjust` route.
- Review/discard a hand-authored trade before it goes live, since `add_manual_trade()` alerts immediately at creation.

This PRD specs a new terminal CLI, admin-only, that separates **drafting** a strategy from **publishing** it, and exposes adjustment/exit as CLI commands reusing the same DB machinery the HTTP admin UI already uses.

## Goal

An admin, from a terminal on a machine with backend DB access, can:

1. Build a multi-leg strategy (`create` + repeated `add-leg`) with each leg's price either typed in directly (**limit** mode) or auto-fetched as the live LTP at the moment that leg is recorded (**market** mode, reusing the same live-price primitive `triggers.py` uses for automated entries) — all while the strategy sits in a new **`draft`** status, invisible to every client-facing read path and silent (no Telegram alert).
2. Run `publish <trade_id>` when ready: flips `draft` → `open` (the existing live status), stamps the real entry time/margin at that moment, and fires the one and only Telegram alert for that trade's entry.
3. `discard <trade_id>` a draft that's abandoned before publish — a clean hard delete, no trace left behind.
4. Once published, use `adjust`/`exit` CLI commands against the same `trade_adjustments` table and alert functions the HTTP admin `/adjust` and `/exit` routes already use — so a strategy built via this CLI behaves identically to one built via the existing admin web flow from that point on.

"Done" = an admin can go from "nothing exists yet" to "a fully-legged, correctly alerted, correctly margined `recommended_trades` row" without ever touching a live trade before they're ready to publish it, and without the frontend/HTTP admin UI needing any changes.

## Non-goals

- **No new HTTP endpoint, no frontend/admin-UI changes.** This is a `backend/`-only terminal tool. A future HTTP+admin-UI version of draft/publish (e.g. a "Draft Strategies" screen mirroring the existing Recommendations admin UI) is plausible follow-up work but explicitly out of scope here — flagging it so it isn't assumed to already exist.
- ~~Not replacing `add_manual_trade()` / `POST /api/recommendations/create`~~ — **superseded, 2026-09-06**: at the founder's request, the Dashboard's own "New Recommendation" form was switched to default to `status="draft"` too (`add_manual_trade()` gained an optional `status` param, mirroring `open_recommended_trade()`'s; margin calc and the Telegram alert are now skipped there exactly as they are for a CLI-created draft, deferred to `publish_manual_trade()`). Both creation paths now default to draft — `trigger_name` still tells them apart (`"MANUAL"` vs `"MANUAL_CLI"`, see below). The Dashboard's "New Recommendation" button/copy was updated accordingly (was "Create & Send Alert", now saves silently as a draft) and its `Draft Strategies` panel (added the same day, admin-only, Publish/Discard buttons) is the way an admin now completes either kind of draft.
- **No fill-waiting / pending-order / limit-order-polling mechanism.** "Limit" price mode means the admin types a price and it's recorded as-is — there is no broker order placed, no polling for a fill. This mirrors the existing `manual_trade.py` behavior exactly (it has always just recorded whatever price the admin gave it).
- **No CLI support for `auto_roll`-type adjustments.** That's `Nifty500MultipleTrigger`'s own automated expiry-roll mechanism (`triggers.py`'s `_do_auto_roll()` + `roll_recommended_trade()`), tied to that specific trigger's re-strike/re-expiry selection logic — not a generic manual capability. A CLI-authored strategy that needs "roll to next expiry" gets there via `exit` (close the old leg) + a fresh `create`/`publish`, same as any other manual roll would today.
- **No TTL/auto-cleanup job for abandoned drafts.** See Open Questions.
- **No changes to `account_trades`/`push_to_account()` push mechanics.** Out of scope; a published trade is push-able to client accounts exactly as any other `open` recommendation is today, no new behavior needed there.

## Mechanics / behavior

### Price modes (per leg)

| Mode | Behavior |
|---|---|
| `market` | Leg price is fetched live at the moment the leg is recorded (`create`/`add-leg`/`adjust`), via **the same primitive `triggers.py`'s `Nifty500MultipleTrigger._fetch_prices()` uses**: `live.upstox_client.get_ltp([instrument_key]) -> {instrument_key: price}` — a direct Upstox API call, not the `price_cache` table (`get_cached_prices()`) that `manual_trade.py` uses for its *spot* snapshot. Direct-API is deliberate: this CLI is a standalone script an admin may run when the live poller isn't running, so it can't depend on `price_cache` being freshly populated by that process. If the API call fails or returns no price for that instrument key, the command aborts for that leg with an error — never silently records a `None`/zero price. |
| `limit` | Admin supplies `--price` directly; recorded exactly as given, no validation against any live price. |

Leg identity/resolution (instrument_key, lot_size, expiry parsing) reuses `live/fo_instruments.py`'s `fo_ikey()` / `fo_lot_size()` / `resolve_expiry()` — the exact same resolution sequence `manual_trade.py`'s `add_manual_trade()`/`_resolve_legs()` already run. No new instrument-resolution logic.

Spot (`entry_ltp`, index-level display field, distinct from any leg's own price) continues to use the existing `get_cached_prices()` + `SPOT_IKEYS` mechanism unchanged, both at draft-`create` time (informational snapshot) and refreshed again at `publish` time (see below) — this field has always been informational/display-only, never leg-execution-critical, so there's no reason to switch it off the existing cache-based mechanism just because leg prices use the direct-API one.

### Draft vs. open — status enum

**Locked decision:** `recommended_trades.status` gains one new value, `'draft'`, alongside the existing `'open'` / `'exited'` (`docs/schema.md`). No schema/enum migration is needed — `status` has always been a plain `TEXT NOT NULL DEFAULT 'open'` column with no `CHECK` constraint (`db/init_db.py:362`, `:887`); a new string value is a pure application-level change.

**Locked decision — no new index.** `idx_recommended_trades_sym_level_status` (`symbol, entry_level, status`) backs the `(symbol, entry_level, status='open')` dedup lookup used only by `get_open_recommended_trade()` (the automated 500-multi trigger's own entry-collision check) — CLI-created drafts always use `entry_level=0` (see below) and never participate in that lookup. A `list-drafts` scan (`WHERE status='draft'`) is a full-table scan, acceptable at this table's expected row volume (hundreds, not millions); add a dedicated `idx_recommended_trades_status` later only if that stops being true.

### What a draft looks like at the DB level

`open_recommended_trade()` (`db/queries.py:381-408`) gains a new optional `status: str = "open"` kwarg (backward-compatible — every existing caller is unaffected), so `create` calls it with `status="draft"`. Column values used for a CLI-created draft, mirroring `add_manual_trade()`'s existing `MANUAL`-trigger convention:

| Column | Draft-creation value | Changes at publish? |
|---|---|---|
| `entry_level` | `0` (not level-based, same as existing `MANUAL` trigger rows) | No |
| `exit_level` | `0` | No |
| `entry_ltp` | Spot snapshot at `create` time (`get_cached_prices()`) | **Yes** — refreshed to spot-at-publish-time |
| `entry_time` | `create` timestamp (placeholder — see below) | **Yes** — overwritten to the actual publish moment |
| `margin_required` / `margin_final` / `margin_at_entry` | `NULL` — **not computed at draft time** | **Yes** — computed for the first time at publish |
| `status` | `'draft'` | flips to `'open'` |
| `trigger_name` | `"MANUAL_CLI"` (new, distinct — see below) | No |

### Locked decision: margin and `entry_time` are deferred to publish, not computed at draft-creation

This is the one decision that keeps the monthly report (`docs/prd/monthly-recommendation-report.md`) from being corrupted by draft rows, and it was worked out directly from that report's actual SQL:

- `get_monthly_report()`'s "positions entered" count (`db/queries.py:640-643`) is `SELECT COUNT(*) FROM recommended_trades WHERE entry_time >= ? AND entry_time < ?` — **no `status` filter at all.** If a draft's `entry_time` were stamped at `create` time and the draft were never published (or published a different month), it would silently inflate that month's "positions entered" figure forever. By only stamping the *real* `entry_time` at `publish`, a draft that's abandoned never contributes to any month's count, and a draft published in a different month than it was drafted in correctly attributes to the *publish* month — which is the month it actually "entered" the book, exactly matching what every other trade's `entry_time` means today (the moment it went live).
- The margin day-by-day query (`db/queries.py:648-652`, `WHERE entry_time < ? AND (status = 'open' OR exit_time >= ?)`) is naturally safe either way — a `'draft'` row never matches `status = 'open'` and never has `exit_time` set — but computing margin at draft time would still be wasted work (SPAN margin for legs that might change before publish) and would populate `margin_at_entry` before the row has really "entered" anything, which is semantically wrong given what that column means everywhere else in the schema (`docs/schema.md`: "Immutable snapshot of `margin_final` captured once at entry").
- `recalculate_recommendation_margin()` (`live/manual_trade.py:402-449`) is **reused as-is, unmodified**, called for the first time at `publish` — its existing `margin_at_entry=COALESCE(margin_at_entry, ?)` write behavior means this first call on a fresh (`NULL`-margin) draft populates `margin_at_entry` exactly like a brand-new `open_recommended_trade()` insert would, with zero code change needed to that function.

**New function needed** (`db/queries.py`): `publish_recommended_trade(trade_id, entry_time, entry_ltp) -> None`, roughly:
```sql
UPDATE recommended_trades
SET status='open', entry_time=?, entry_ltp=?
WHERE id=? AND status='draft'
```
The `AND status='draft'` guard makes `publish` idempotent-safe against double-invocation (a second `publish` on an already-open trade is a no-op at the SQL level; the CLI additionally checks status up front and errors with a clear message rather than silently doing nothing).

`publish` then calls the existing `recalculate_recommendation_margin(trade_id)` to populate margin/`margin_at_entry` from the draft's current legs (`get_current_legs()` — already netted, so any `add-leg` calls made while still a draft are correctly reflected), and finally sends the Telegram alert (see below).

### Locked decision: draft alert is silent, publish alert fires once

`create`/`add-leg` never call anything in `live/alert.py` or `live/trade_suggestions.py` — no signal dict is built, `send_telegram()`/`send_alert()` are never invoked while `status='draft'`.

`publish` reuses the existing alert-building logic `add_manual_trade()` already has today (`manual_trade.py`'s `_send_manual_alert()`, called at `manual_trade.py:174-177`) — same "Manual Trade · SYMBOL · id=N" formatted message, built from the draft's now-finalized legs/margin/spot. The only change in *when* it fires: today it fires inside `add_manual_trade()` at creation; for the CLI flow it fires inside `publish`, after the status flip and margin recalculation succeed. (`_send_manual_alert()` is a private-by-convention function in the same package — reused directly, not duplicated; renaming it to a public helper as part of implementation is an implementation detail, not a PRD requirement.)

### Locked decision: draft-time leg additions are NOT `trade_adjustments`

`add-leg` on a still-`draft` trade calls `add_trade_legs()` (`db/queries.py:411-448`) directly — the exact same function `create`'s initial legs use — inserting plain `action='entry'`, `adjustment_id=NULL` rows. It does **not** go through `add_trade_adjustment()`/`trade_adjustments`.

This matters because `trade_adjustments` (`docs/schema.md`) models a change to an **already-live** position — it exists to be shown to clients as a distinct event on an open trade (`get_trade_adjustments()`, surfaced in `GET /api/recommendations`'s `adjustments` field), and `add_trade_adjustment()`'s docstring is explicit that it's for adjusting a position that's already on the book. A draft was never on the book — its legs are still being assembled, not "adjusted." `add-leg` is therefore only valid while `status='draft'`; once published, changing legs goes through `adjust` (below), which *does* use the `trade_adjustments` machinery, matching what `/api/recommendations/<id>/adjust` already does for every other open trade.

### Locked decision: `adjust`/`exit` on a published trade reuse existing machinery exactly

Both commands require `status='open'` (checked up front — a draft has to be published first; an exited trade can't be adjusted or exited again), and both are thin CLI wrappers around the exact functions the HTTP admin routes already call:

- **`adjust <trade_id> --type <add_legs|replace_legs|partial_exit> --leg ... [--note ...]`** → `add_trade_adjustment(trade_id, adj_type, note, ts, legs)` (`db/queries.py:1824-1865`, unchanged) + `recalculate_recommendation_margin(trade_id)` (unchanged) + `live.alert.send_adjustment_alert()` (unchanged — already exists, already used by `server.py`'s `/adjust` route). **One behavioral improvement over the existing HTTP route**, worth calling out: `server.py:643` always writes the generic literal `adj_type="adjustment"` regardless of what kind of change it is, even though `live/alert.py:216-219` already has display labels wired up for `add_legs`/`replace_legs`/`partial_exit`/`auto_roll` that the HTTP route never actually populates. The CLI's `--type` flag writes the real, specific `adj_type` the admin selects — a pure superset of existing behavior (same table, same column, no schema change), giving cleaner Telegram messages and audit/report readability for CLI-created adjustments. The actual position math is unaffected either way — it's always fully determined by `get_current_legs()`'s BUY/SELL netting per `instrument_key`, never by the `adj_type` label.
- **`exit <trade_id> [--note ...] [--leg ...]`** → CLI fetches `get_current_legs(trade_id)` (netted — reflects every prior `add_legs`/`replace_legs`/`partial_exit`). **Locked decision (resolved with the founder):** exit legs are specified the same self-identifying way as `create`/`add-leg` legs — `--leg "strike=57000,type=PE,price_mode=limit,price=1600"` or `--leg "strike=57000,type=PE,price_mode=market"` — matched against `get_current_legs()` by `(instrument_type, strike, expiry_str)` (or `instrument_key` for `EQ`), not by position. `price_mode=market` auto-fetches the live LTP via the same direct-API primitive entry legs use (`live.upstox_client.get_ltp()`); `price_mode=limit` requires `--price`. Every current leg must be matched exactly once or the command errors before writing anything (no partial exit via this command — that's `adjust --type partial_exit`). Builds opposite-side exit legs from the resolved prices, then `close_recommended_trade()` (`db/queries.py:2020-2048`, unchanged) + `live.alert.send_rec_exit_alert()` (unchanged) + `live.manual_trade.auto_exit_linked_account_trades()` (unchanged). **Deliberately does *not* reuse `close_manual_trade()`** (`manual_trade.py:254-341`) — that function sources its leg list from `get_trade_legs(trade_id)` filtered to `action='entry'` (every entry-tagged row ever inserted, original + adjustment-added, **not netted**), which is a known-narrower/legacy pattern; `server.py`'s own `/api/recommendations/<id>/exit` route deliberately uses the netted `get_current_legs()` instead (see its inline comment at `server.py:594-597`) specifically so it doesn't ask for more prices than there are actually-still-open legs after adjustments. The CLI's `exit` follows the HTTP route's (correct) pattern, not `manual_trade.py`'s, and additionally improves on the HTTP route's positional price list by matching legs by identity instead of order.
- **`discard <trade_id>`** → `delete_recommendation()` (`db/queries.py:2268-2281`), only valid while `status='draft'`. **Requires one change**: its current `DELETE FROM recommended_trades WHERE id = ? AND status = 'open'` (`:2279`) widens to `WHERE id = ? AND status IN ('open', 'draft')`. This is safe for the existing HTTP `/api/recommendations/<id>/delete` route — that route already gates on `rec["status"] != "open"` *before* calling `delete_recommendation()` (`server.py:895-905`), so widening the underlying query function's own WHERE clause doesn't change what that route will actually delete; it only newly permits the CLI's `discard` to delete a `draft` row directly against the same function.

### Locked decision: `trigger_name` — `"MANUAL_CLI"`, distinct from the existing `"MANUAL"`

Every strategy created by this CLI is stamped `trigger_name="MANUAL_CLI"`. The existing `add_manual_trade()`/`POST /api/recommendations/create` path keeps stamping `"MANUAL"`, unchanged. This is a one-line change (a literal passed to `open_recommended_trade()`), and gives the monthly report / any future per-trigger breakdown a way to tell "instant HTTP admin add" apart from "CLI draft/publish workflow" without any other schema change — `trigger_name` is already a free-text column with no enum constraint, same as `status`.

### Client-facing read paths that must exclude `'draft'`

This was worked out by tracing every read of `recommended_trades` (`server.py`, `db/queries.py`), not assumed:

| Read path | Current behavior | Change needed |
|---|---|---|
| `GET /api/recommendations` → `get_all_recommendations()` (`db/queries.py:523-539`) | **No `status` filter at all** — returns every row. Route is `@require_login` (`server.py:527-528`), i.e. **every logged-in client**, not admin-gated. | **Required.** Add `WHERE rt.status != 'draft'` to `get_all_recommendations()`'s query. Without this, every draft strategy — legs, prices, everything — is visible to every client the moment it's created, defeating the entire point of a draft state. This is the single most important code change this feature depends on. |
| `POST /api/recommendations/<id>/exit` (`server.py:581-620`) | Checks `trade["status"] != "open"` → 400 | None — already rejects a draft by construction. |
| `POST /api/recommendations/<id>/adjust` (`server.py:623-656`) | Checks `trade["status"] != "open"` → 400 | None — already rejects a draft. |
| `POST /api/recommendations/<id>/delete` (`server.py:895-905`) | Checks `rec["status"] != "open"` → 400 ("Only open recommendations can be deleted") | None for the HTTP route itself (still can't delete anything via HTTP unless `open`) — see `delete_recommendation()` widening above, needed only for the CLI's own `discard`. |
| `get_all_open_recommended_trades()` / `get_open_recommended_trade()` / `get_all_open_trades()` (briefing, `Nifty500MultipleTrigger`) | Already `WHERE status = 'open'` | None — a draft never matches `status='open'`, safe by construction. |
| `get_monthly_report()` — positions-entered count | No `status` filter, but keyed on `entry_time` | None — safe *because* `entry_time` is only stamped at publish (see decision above), not because of a status filter. |
| `get_monthly_report()` — margin day-by-day query | `WHERE ... (status='open' OR exit_time >= ?)` | None — a draft never matches either branch. |
| `get_monthly_report()` — exited-trades query | `WHERE status = 'exited'` | None. |
| `POST /api/account-trades/create` (`server.py:785-812`) | Accepts an arbitrary `recommended_trade_id` from the client as a display tag only — never validates its status, never reads its legs. | **Required (resolved with the founder):** reject the request (400) when the supplied `recommended_trade_id` resolves to a `status='draft'` row. Cheap defensive check even with no current discovery path for a draft ID. |

## Architecture impact

New file, `backend/strategy_cli.py` (top-level, alongside `poller.py`) — a standalone argparse-based dispatcher, same shape as `poller.py`'s own `bootstrap`/`sync`/`live`/etc. subcommand style (`poller.py:19-60`), invoked as `python strategy_cli.py <command> [flags]`. Never imported by `server.py`/the Flask app; purely a terminal tool run directly against the same SQLite file (`backend/data/drishti.db`) the Flask API and poller share.

**`db/queries.py` changes:**
- `open_recommended_trade()` — add optional `status: str = "open"` kwarg (backward-compatible).
- New `publish_recommended_trade(trade_id, entry_time, entry_ltp) -> None`.
- `delete_recommendation()` — widen `DELETE ... WHERE id = ? AND status = 'open'` to `... AND status IN ('open', 'draft')`.
- `get_all_recommendations()` — add `WHERE rt.status != 'draft'` (or equivalent).
- New `list_recommendations_by_status(status: str) -> list[dict]` (or an optional `status` filter param on an existing lister) — backs the CLI's `list-drafts`.

**No changes needed** to: `add_trade_legs()`, `add_trade_adjustment()`, `close_recommended_trade()`, `get_current_legs()`, `get_trade_legs()`, `get_trade_adjustments()`, `recalculate_recommendation_margin()`, `live/alert.py`'s `send_adjustment_alert()`/`send_rec_exit_alert()`/`send_telegram()`, `live/fo_instruments.py`, `live/upstox_client.py`. All reused as-is.

**`live/manual_trade.py`**: no required changes — `_send_manual_alert()` is reused (imported) by the CLI's `publish` command, not modified. `add_manual_trade()`/`close_manual_trade()`/`push_to_account()` are all left exactly as they are; this feature is fully additive alongside them.

**`server.py`**: one required change — `get_all_recommendations()`'s new filter is called from the existing `/api/recommendations` route with no route-level code change needed (the filter lives inside the query function).

## CLI command surface

Leg flags are repeatable `--leg` arguments, each a comma-separated `key=value` list mirroring `manual_trade.py`'s existing leg-dict shape (`side`/`type`/`strike`/`expiry`/`lots`/`price`) plus the new `price_mode`:

```
--leg "side=SELL,type=PE,strike=57000,expiry=May 2026,lots=2,price_mode=limit,price=1548.17"
--leg "side=BUY,type=PE,strike=54500,expiry=May 2026,lots=6,price_mode=market"
```
`price` is required when `price_mode=limit`, rejected (error) when `price_mode=market`. `strike`/`expiry` required for `PE`/`CE`/`FUT` legs, omitted for `EQ` (which instead needs `instrument_key`, matching `manual_trade.py`'s existing `EQ` handling).

| Command | Arguments | Reuses |
|---|---|---|
| `create` | `--symbol`, `--note`, `--risk-level`, one or more `--leg` | `open_recommended_trade(status="draft")`, `add_trade_legs()` |
| `add-leg <trade_id>` | one or more `--leg` | `add_trade_legs()` — draft only |
| `show <trade_id>` | — | `get_recommendation()`, `get_current_legs()`, `get_trade_adjustments()` — read-only, any status |
| `list-drafts` | `[--symbol]` | new `list_recommendations_by_status("draft")` |
| `publish <trade_id>` | — | `publish_recommended_trade()`, `recalculate_recommendation_margin()`, `_send_manual_alert()` — draft only |
| `discard <trade_id>` | — | `delete_recommendation()` — draft only |
| `adjust <trade_id>` | `--type {add_legs,replace_legs,partial_exit}`, `--note`, one or more `--leg` | `add_trade_adjustment()`, `recalculate_recommendation_margin()`, `send_adjustment_alert()` — open only |
| `exit <trade_id>` | `--note`, one `--leg` per current leg, self-identifying (`strike`/`type`/`expiry` or `instrument_key`) + `price_mode`/`price` | `close_recommended_trade()`, `send_rec_exit_alert()`, `auto_exit_linked_account_trades()` — open only |

## Data / storage

No new tables, no new columns, no schema migration. One new `status` value (`'draft'`) on the existing free-text `recommended_trades.status` column — no `CHECK` constraint exists to update. `trigger_name="MANUAL_CLI"` is likewise a new free-text value on an existing unconstrained column. No retention/cleanup job is added (see Open Questions on abandoned drafts).

## Success criteria

- `create` with a mix of `market`/`limit` legs produces a `status='draft'` row with `margin_required`/`margin_final`/`margin_at_entry` all `NULL`, and **no** Telegram message sent (verify against the bot/chat directly, not just absence of an exception).
- That same draft does **not** appear in `GET /api/recommendations`'s response for a `client`-role session, nor for an `admin`-role session — confirms the filter is unconditional, not role-gated.
- `publish <trade_id>` on that draft: row flips to `status='open'`, `entry_time` becomes the publish-moment timestamp (not the original `create`-moment one), `margin_at_entry` is populated and equals the freshly computed `margin_final`, and exactly one Telegram message fires.
- Running `get_monthly_report()` for the month the draft was *created* in (if different from the month it was *published* in) shows **no** contribution from that trade to `positions_entered` or the margin series for the creation month — it only shows up in the publish month's figures.
- `discard <trade_id>` on a still-draft trade removes the row and its legs entirely (`SELECT * FROM recommended_trades WHERE id=?` returns nothing); attempting `discard` on an already-`open`/`exited` trade errors without deleting anything.
- `adjust`/`exit` on a published (formerly-CLI-drafted) trade produce identical DB/Telegram effects to the same operations performed via the existing `/api/recommendations/<id>/adjust`/`/exit` HTTP routes on a trigger-created trade — spot-check by comparing a CLI-adjusted trade's `trade_adjustments`/`trade_legs` rows against a HTTP-adjusted one.
- `trigger_name='MANUAL_CLI'` rows are queryable/distinguishable from `trigger_name='MANUAL'` rows in the monthly report's `margin_positions`/`pnl_events`.

## Open questions (resolved)

- **Abandoned drafts — TTL or cleanup?** Resolved: **no** cleanup/nag. `list-drafts` is sufficient visibility; matches how nothing else in this codebase gets a staleness nag.
- **`POST /api/account-trades/create`'s unvalidated `recommended_trade_id`** — resolved: **add the guard** (see table above — reject with 400 when it resolves to a `draft` row).
- **`exit`'s leg-price collection UX** — resolved: self-identifying (`strike`/`type`/`expiry` or `instrument_key`), not positional, and each leg additionally gets its own `price_mode` (`market`/`limit`) exactly like entry legs, not a single price prompt (see `exit` command spec above).

## Open questions (still open)

- ~~**Future HTTP+admin-UI version**~~ — **resolved, 2026-09-06**: built. `frontend/src/screens/Trades.jsx` gained a "Draft Strategies" panel (admin-only, additive alongside the existing open/exited list) with Publish/Discard buttons per draft, backed by the `GET /api/recommendations/drafts`, `POST /api/recommendations/<id>/publish`, and `POST /api/recommendations/<id>/discard` routes documented in `docs/apis.md`.

## Addendum, 2026-09-06: live margin/P&L preview on the Draft Strategies panel

Once the panel existed, the founder asked for it to show margin, unrealised P&L, and live-tracked prices "similar to open positions" — not just a static leg list. Two changes, both **read-only, non-persisting** (the core "margin deferred to publish" decision above is untouched — nothing here writes `margin_required`/`margin_final`/`margin_at_entry` early):

- **Margin preview**: `live.manual_trade._compute_margin(legs)` extracted as a shared helper (was duplicated inline in `add_manual_trade()` and `recalculate_recommendation_margin()`); new `preview_margin_for_trade(rec_id)` calls it against `get_current_legs()` with no DB write. `GET /api/recommendations/drafts` calls this per draft on every request and returns `margin_required`/`margin_final` as a live estimate — same field names as the persisted columns elsewhere in the API, but explicitly documented as non-persisted for this route.
- **Live price tracking**: `get_open_trade_ikeys()` (`db/queries.py`) — the query the live poller (`live/poller.py`) uses to decide which instrument keys to fetch LTPs for and write to `price_cache` every 5s — widened from `WHERE rt.status = 'open'` to `WHERE rt.status IN ('open', 'draft')`. Without this, a draft's legs would never appear in `price_cache`, `GET /api/prices` could never return anything for them, and the frontend's `unrealizedPnl()` util would permanently show `—` for a draft no matter what the UI did. Frontend: `DraftsPanel` collects `instrument_key`s across all drafts and calls the same shared `useRecPrices`/`useTrackedPrices` poller `RecsPanel` already uses for open positions (one deduped `/api/prices` request across every mounted consumer); `utils/pnl.js`'s `unrealizedPnl()` guard widened from `rec.status !== 'open'` to also accept `'draft'` (the math — entry price vs current LTP — doesn't care about status, it was only ever gated to exclude `'exited'`/legless rows).
- Requires the live poller (`python poller.py live`) actually running for any of this to populate — same pre-existing requirement open positions already have. With the poller off, drafts (like open positions) show `—` for P&L; margin preview is unaffected since it calls Upstox's margin API directly, not `price_cache`.

## Addendum, 2026-09-06: Draft card is a real `RecItem`, not a lookalike

The Draft Strategies panel's first cut used a bespoke `DraftItem` component that duplicated `RecItem`'s markup — this drifted immediately (no collapse/expand, no live-price wiring at the leg level) and the founder correctly called it out as "not exactly similar." Fixed properly rather than patched: `DraftItem` was deleted, and `DraftsPanel` now renders drafts through **the actual `RecItem` component** the open/exited list uses, with `RecItem` extended with a third `isDraft` branch alongside `isOpen`/exited (status dot, price passthrough to `RecLegs`, the margin/P&L stats strip, and a Publish/Discard action-bar branch in place of Adjust/Exit/Delete). This is guaranteed structural parity going forward — a future change to `RecItem` automatically applies to drafts too, instead of needing to be ported by hand to a second component. Backend enabler: `server.py`'s per-row builder was extracted into a shared `_shape_recommendation_row()`, called by both `GET /api/recommendations` and `GET /api/recommendations/drafts` with only `margin_required`/`margin_final` differing by source (persisted vs. `preview_margin_for_trade()`) — this is *why* the same frontend component can consume either response with zero special-casing (see `docs/apis.md`'s `/api/recommendations/drafts` entry for the exact shared shape).

## Addendum, 2026-09-06: Share button (open positions) + EdgeVest-branded, linked Telegram alerts

Two related asks, same underlying idea — every notification about a position (in-app or Telegram) should be a short, branded prompt that links back to the site, not a data dump:

- **Share button**: `RecItem`'s open-position action bar (both admin and client variants, including the "adjusted — contact your advisor" notice state) gained a `ShareIcon` button (`components/common/Icons.jsx`) calling `navigator.share()` with a fallback to `copyToClipboard()` (new `utils/clipboard.js`, extracted from `screens/profile/Referrals.jsx`'s already-tested fallback chain — that screen itself untouched). Message: `EdgeVest · <title>`, `#<display_code> · <status>`, and a link to `/trades?rec=<id>` — reusing `RecsPanel`'s existing `?rec=` deep-link effect (switches Open/Exited tab, scrolls to, highlights the card) so the recipient actually lands on the right position, not just the Trades screen.
- **Telegram alerts redesigned to match**: `live/manual_trade.py`'s old `_send_manual_alert()` (routed manual entries through the generic multi-message `send_alert()`/`_format_signal()`/`_format_trade()` pipeline shared with algo-trigger alerts, and exposed internal naming like "Manual Trade · SYMBOL · id=N") was deleted. Three new dedicated, lean functions in `live/alert.py` — `send_new_trade_alert()`, `send_adjustment_alert()` (signature changed: now takes `trade_id`/`display_code`), `send_rec_exit_alert()` (signature changed: `trade_id`/`display_code` added, `spot` param dropped) — share one format: EdgeVest-branded header, one summary line (`display_code` + what happened + leg count, no leg-by-leg dump, no spot price), and a "View & track on EdgeVest" link via new `_frontend_url()` helper (reads `FRONTEND_URL` from `backend/.env.<FLASK_ENV>`, same var `server.py` uses for post-auth redirects). All call sites updated (`server.py`'s `/adjust`/`/exit` routes, `strategy_cli.py`'s `adjust`/`exit` commands). The generic `send_alert()`/`_format_signal()`/`_format_trade()` pipeline itself is untouched and still used unmodified by every algo-trigger alert (Supertrend/EMA/RSI/500-multi, `live/poller.py`/`live/triggers.py`) — the `is_manual`/`"MANUAL ENTRY"` special-casing that briefly existed in that shared pipeline during this change was reverted once the dedicated functions made it dead code.
- **New dependency**: `strategy_cli.py` didn't previously load `backend/.env.<FLASK_ENV>` at all (only `server.py` did) — added the same `load_dotenv()` call there, otherwise `FRONTEND_URL` (and the link line) would be silently blank whenever a Telegram alert fires from the terminal CLI rather than the HTTP API. `FLASK_ENV` must still be set explicitly when running the CLI for this to resolve (e.g. `FLASK_ENV=dev python strategy_cli.py publish <id>`) — matches the existing "no smart default, defaults to production if unset" rule from the root `CLAUDE.md`.

## Addendum, 2026-09-06: API design — one route per auth boundary, not a `?status=` param

Raised by the founder: why `GET /api/recommendations` and `GET /api/recommendations/drafts` as two routes, given they now share `_shape_recommendation_row()` and differ only in status/margin-source? Considered and rejected merging them behind a `?status=draft` query param on the single existing route. **Locked reasoning**: `GET /api/recommendations` is `@require_login` (any client); drafts must never reach a client. Splitting the auth boundary at the route/decorator level (`@require_login` vs `@require_role(admin)`) makes "clients can't see drafts" visible at a glance and immune to a future conditional-logic mistake; a shared route would need that same guarantee enforced *inside* the handler as an if-branch, which is exactly the shape of bug this PRD already found and fixed once (`GET /api/recommendations` originally had no status filter *and* wasn't admin-gated — see the drafts-route table entry above). The remaining duplication (two decorators, two DB query calls feeding one shared shaper) is an accepted, deliberate cost for that guarantee — not something to refactor away.

## Addendum, 2026-09-06: hardening pass before commit

Lead-dev-style review of the full diff before release, alongside `/code-review`:

- Two unnecessary `f''` string prefixes in `live/alert.py` (no interpolation inside) — cosmetic, fixed.
- **Real fix**: `publish_manual_trade()` and `add_manual_trade()`'s `status="open"` branch both called `send_new_trade_alert()` unguarded, *after* the DB write (status flip / margin) had already committed. A formatting bug in the alert path would have made the operation report failure (or 500) even though the trade was already live — misleading to whoever's watching the response. Wrapped both in `try/except`, matching the guarding pattern `server.py`'s `/adjust`/`/exit` routes already use around their own alert calls (`send_telegram()` itself already never raises — this guards the message-*building* code above it, which theoretically could).
- `pyflakes` run across every changed file; every other finding (a shadowed loop var and two unused imports elsewhere in `server.py`/`manual_trade.py`) traced against `git show HEAD` and confirmed pre-existing/unrelated — left alone rather than scope-creeping into an unrelated cleanup.
- Verified live end-to-end after each fix (scratch draft → publish → real Telegram send → confirmed message content → deleted the scratch row), not just re-compiled.
