# Release Checklist

How to cut and ship an EdgeVest release — versioning convention, backend
steps, frontend steps, and the current outstanding items as of the last time
this doc was updated (2026-08-25, `v5.0`).

## Versioning

- Tags are placed directly on `dev` (`v3.0`, `v4.0`, `v5.0`, ...) — this repo
  does not merge to `main` for releases; `main` sits untouched at the initial
  monorepo commit.
- Bump both of these together, in their own commit, before tagging:
  - `frontend/package.json` + `frontend/package-lock.json` (`"version"` field,
    top of the file and the `packages[""]` entry — **do not** blind
    find-and-replace the version string across the whole lockfile, other
    dependencies legitimately share version numbers with the app)
  - `backend/server.py`'s `APP_VERSION` constant (added in `v5.0`; no other
    version tracking exists in the backend)
- Tag only when you're about to actually ship — don't chase a tag for every
  commit. `git describe --tags --always --dirty` (used as the default
  release id by `frontend/deploy/deploy.sh`) will honestly report
  `v5.0-1-gabc1234` for anything committed after the tag; that's correct
  behavior, not a bug to fix.
- A tag that has already been pushed should not be force-moved — cut a new
  tag (`v5.0.1`, `v5.1`, ...) instead.

## Backend release (EC2)

1. **Get the code onto the box** — `git pull` (or checkout the release tag)
   at `/home/ubuntu/edgevest`.
2. **Sync `backend/.env.production`** — this file is gitignored, so the copy
   on a dev laptop and the copy on EC2 are two independent files that never
   auto-sync. Diff and merge by hand; never overwrite the server's copy
   wholesale (it may hold entries — e.g. `CORS_ORIGINS` — that a laptop's
   copy doesn't).
   - Give prod its own `PAYMENTS_CRON_SECRET`, distinct from dev's. Generate
     one with `python3 -c "import secrets; print(secrets.token_hex(24))"`.
3. **Migrate the database** — `python poller.py init`. This is the only
   command in this codebase that touches schema (`db/init_db.py`'s
   `init_db()`, `CREATE TABLE IF NOT EXISTS` everywhere — idempotent, safe to
   rerun, never touches existing data). `python poller.py sync` does **not**
   do this — that command runs `sync/daily_sync.py`'s end-of-day
   candle sync and never calls `init_db()`. Needed at least once for the
   `payment_orders` table, introduced by the Razorpay integration.
4. **Set up the reconciliation cron**, if not already present — nothing in
   this repo schedules `POST /api/payments/reconcile` (confirmed by grepping
   the repo for it — no crontab/systemd-timer file exists anywhere). Add one:
   ```
   */15 * * * * curl -s -X POST -H "X-Cron-Secret: <PAYMENTS_CRON_SECRET>" https://api.edgevest.in/api/payments/reconcile
   ```
   Keep the interval longer than a single run can take — there's no lock
   against two overlapping runs both racing to resolve the same stale order
   (see `docs/architecture.md`'s payments section).
5. **Restart the service** — `sudo systemctl restart edgevest-web`.
6. **Verify** — hit `/api/me` (or similar) and confirm the new code is
   actually serving. Since `RAZORPAY_KEY_ID` is a live key (`rzp_live_...`),
   plan a small real-money checkout smoke test rather than assuming
   test-mode behavior carries over.

## Frontend release (S3 + CloudFront)

Use `frontend/deploy/deploy.sh` — versioned releases, fast rollback. See the
script's own header comment for full mechanics; summary:

```
frontend/deploy/deploy.sh deploy   <prod|staging|dev> [release-id]
frontend/deploy/deploy.sh rollback <prod|staging|dev> <release-id>
frontend/deploy/deploy.sh list     <prod|staging|dev>
frontend/deploy/deploy.sh current  <prod|staging|dev>
```

- Each deploy builds (`npm run build` / `build:staging` / `build:dev`),
  uploads `dist/` to `s3://<bucket>/releases/<release-id>/`, then repoints
  that environment's CloudFront `OriginPath` at the new prefix and
  invalidates `/*`. Nothing previously deployed is touched, so rollback is
  just repointing `OriginPath` at an older release — no rebuild, no
  reupload.
- `release-id` defaults to `git describe --tags --always --dirty`. Pass one
  explicitly (e.g. the tag name) when you want the S3 folder to read cleanly
  as an exact release rather than "N commits past a tag".
- Requires `aws` CLI (profile `default`) and `python3`; does not require
  `jq`.

## Order of operations for a full release

1. Bump versions, commit, tag (see Versioning above).
2. Push `dev` + the tag to origin.
3. Backend steps 1–6 above, on EC2, for prod.
4. `frontend/deploy/deploy.sh deploy prod <tag>`.
5. Smoke test prod end-to-end (login, a real small checkout, positions,
   games).

Dev and staging can go through step 4 independently, any time, without
waiting on the backend/prod steps — they're lower-stakes and don't share
prod's Razorpay keys or DB.

## Status as of 2026-08-25 (`v5.0`)

- ✅ `dev.edgevest.in` and `staging.edgevest.in` — both on the versioned
  deploy pattern, serving `releases/v5.0`, old pre-versioning files cleaned
  out of both buckets.
- ❌ `edgevest.in` (prod frontend) — still on the old flat/root S3 deploy,
  not yet moved onto `frontend/deploy/deploy.sh`.
- ❌ Prod backend — not yet on `v5.0`. `.env.production` on EC2 not yet
  confirmed synced with `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` /
  `PAYMENTS_CRON_SECRET` (added locally, never pushed to the server).
  `PAYMENTS_CRON_SECRET` still needs to be made distinct from dev's before
  going live. `payment_orders` table confirmed absent from prod's DB as of
  the last backup (2026-08-24). No reconciliation cron scheduled anywhere.
- ⚠️ 34 Dependabot vulnerabilities (15 high, 18 moderate, 1 low) flagged on
  every push to `dev` — not triaged yet, worth a look before or shortly
  after this release.
