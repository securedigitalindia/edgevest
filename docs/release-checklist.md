# Release Checklist

How to cut and ship an EdgeVest release — versioning convention, backend
steps, frontend steps, and the current outstanding items as of the last time
this doc was updated (2026-08-26, `v5.4`).

## Branching model

- **Current (solo)**: everything happens directly on `dev`; tags (`v3.0`
  through `v5.1`) were placed there, and `main` was intentionally left
  untouched at the initial monorepo commit.
- **As of `v5.2` (2026-08-26)**: `main` was fast-forwarded to match `dev`
  (`git merge dev --ff-only`, clean — `main` had never diverged) as the first
  step of moving to a real branching model for when more than one person is
  contributing: new work branches off `main`, PRs into `dev`, and once a
  batch of work on `dev` is ready to ship, `dev` merges into `main` (fast-
  forward, same as this one, as long as nothing lands on `main` directly in
  between) — **`main` becomes the source of truth, and release tags move to
  `main` going forward** instead of `dev`.
- Until other contributors are actually opening PRs against `dev`, this is
  functionally the same solo workflow as before, just with the extra step of
  fast-forwarding `main` at release time instead of never touching it.

## Versioning

- Tags are placed on `main` (`v5.2` on) — `dev` is where work lands first;
  `main` is fast-forwarded to `dev` at release time and the tag goes on
  `main`. (Tags before `v5.2` — `v3.0` through `v5.1` — were placed on `dev`,
  back when `main` was never touched; see Branching model above.)
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
2. **Install Python dependencies** — `source venv/bin/activate && pip install
   -r requirements.txt`. `backend/edgevest-web` (the systemd `ExecStart`
   script) only activates the venv and runs gunicorn; nothing installs
   packages automatically. `razorpay>=1.4.0` was added to
   `requirements.txt` alongside the payments module — if prod's venv was set
   up before that, it won't have it yet.
3. **Sync `backend/.env.production`** — this file is gitignored, so the copy
   on a dev laptop and the copy on EC2 are two independent files that never
   auto-sync. Diff and merge by hand; never overwrite the server's copy
   wholesale (it may hold entries — e.g. `CORS_ORIGINS` — that a laptop's
   copy doesn't).
   - Give prod its own `PAYMENTS_CRON_SECRET`, distinct from dev's. Generate
     one with `python3 -c "import secrets; print(secrets.token_hex(24))"`.
4. **Migrate the database** — `python poller.py init`. This is the only
   command in this codebase that touches schema (`db/init_db.py`'s
   `init_db()`, `CREATE TABLE IF NOT EXISTS` everywhere — idempotent, safe to
   rerun, never touches existing data). `python poller.py sync` does **not**
   do this — that command runs `sync/daily_sync.py`'s end-of-day
   candle sync and never calls `init_db()`. Needed at least once for the
   `payment_orders` table, introduced by the Razorpay integration.
5. **Set up the reconciliation cron**, if not already present — nothing in
   this repo schedules `POST /api/payments/reconcile` (confirmed by grepping
   the repo for it — no crontab/systemd-timer file exists anywhere). Add one:
   ```
   */15 * * * * curl -s -X POST -H "X-Cron-Secret: <PAYMENTS_CRON_SECRET>" https://api.edgevest.in/api/payments/reconcile
   ```
   Keep the interval longer than a single run can take — there's no lock
   against two overlapping runs both racing to resolve the same stale order
   (see `docs/architecture.md`'s payments section).
6. **Restart the service** — `sudo systemctl restart edgevest-web`.
7. **Verify** — hit `/api/me` (or similar) and confirm the new code is
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

1. Bump versions, commit on `dev` (see Versioning above).
2. Fast-forward `main` to `dev` (`git checkout main && git merge dev --ff-only`),
   tag `main`, push `main` + `dev` + the tag to origin.
3. Backend steps 1–7 above, on EC2, for prod.
4. `frontend/deploy/deploy.sh deploy prod <tag>`.
5. Smoke test prod end-to-end (login, a real small checkout, positions,
   games).

Dev and staging can go through step 4 independently, any time, without
waiting on the backend/prod steps — they're lower-stakes and don't share
prod's Razorpay keys or DB.

## Status as of 2026-08-26 (`v5.4` — frontend released to prod; backend released through `v5.2`)

- ✅ `edgevest.in`/`www.edgevest.in` — serving `releases/v5.4` (frontend-only
  CSS spacing fix, no backend changes this release).
  `dev.edgevest.in`/`staging.edgevest.in` are still on `v5.1` (last deployed
  there); they'll read as behind until someone runs
  `deploy.sh deploy dev v5.4` / `deploy.sh deploy staging v5.4`.
- ⚠️ Prod backend is still running `v5.2`'s `APP_VERSION` (`5.2.0`). `v5.3`
  and `v5.4` bumped `APP_VERSION` in lockstep with the frontend per
  convention, but neither actually touched backend code, so no EC2 release
  was done for either — `git tag`/`APP_VERSION` and "what's actually
  deployed on EC2" have diverged by two versions. Not urgent (nothing to
  deploy), but worth remembering next time a real backend change ships:
  the EC2 steps need to run for that release specifically, not just
  whichever `APP_VERSION` string is currently in `server.py`.
- ✅ `main` fast-forwarded to `dev` at each release since `v5.2` (`v5.3`,
  `v5.4`) — same branching model, no divergence issues.
- Previous status (`v5.2`, 2026-08-26): frontend + backend both released to
  prod, `main` fast-forwarded to `dev` for the first time.
- ⚠️ 34 Dependabot vulnerabilities (15 high, 18 moderate, 1 low) flagged on
  every push to `dev` — not triaged yet, worth a look now that `v5.0` is out.
