# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

TCM 中藥腫瘤篩選平台 (TCM/oncology screening platform) — a FastAPI backend + vanilla-JS/HTML frontend (no build step, no framework). Backend: `app/`. Frontend: `frontend/` (static files served by FastAPI at `/app/`, and separately deployed to Cloudflare Pages). All UI copy, comments, docs, and commit messages in this repo are Traditional Chinese; match that when editing existing files.

This repo's own house rules live in **`rules.md`** — read it before adding or changing a feature. It documents real bugs that were hit and fixed (with version numbers), and the reasoning is not repeated in code comments. Treat it as the primary spec/architecture-decision doc, more authoritative than this file for anything about conventions. `architecture.html` renders `rules.md` in the running app.

**MANDATORY: before editing any `.py` file under `app/`, read `.claude/rules/backend.md` and follow it in full.** It is not optional guidance — treat violations as build-breaking. Its six sections, each with a real past incident behind it:
- **Dual-database compatibility** — code must work on both SQLite (local) and PostgreSQL (production). Never use Postgres-only types (`ENUM`/`ARRAY`/`JSONB`/`INET`/`GIN`); JSON goes in a `Text` column as a serialized string.
- **Read-only session routing** — query-station/read-only endpoints must use `get_query_db`, not `get_db`, or the read-only-mode local cache silently stops working.
- **Admin bypass / ACL / audit** — role `"管理者"` bypasses all permission checks; new guarded routes use `require_permission(feature_code, ...)`; every mutating action goes through the one shared `write_audit_log(...)`, never a per-feature audit table.
- **`feature_config` overwrite protection** — `seed_default_data()`/`migrate_schema.py` may update `module`/`name`/`nav_label`/`page_url`/`sort_order` on existing feature rows, but must never overwrite `enabled`/`show_frontend`/`show_backend` (admin-editable at runtime; overwriting them silently reverts admin changes on every restart — this happened in v1.32.4).
- **Secret comparison** — externally-triggered endpoints compare secrets with `secrets.compare_digest`, and return 503 (not a silent skip) when the secret env var is unset.
- **Self-authored migration script, no Alembic** — schema changes go into `migrate_schema.py` by hand (no `alembic/`, `env.py`, or `versions/`); DDL must run on both SQLite and Postgres (SQLite can't `DROP COLUMN`/`ALTER COLUMN`), and its feature-row update logic must mirror `seed_default_data()`'s update-vs-overwrite rule above.

## Commands

```bash
# setup + run (from repo root)
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Frontend: http://localhost:8000/app/index.html — API docs (Swagger): http://localhost:8000/docs
- DB: SQLite file `tcm_platform.db`, auto-created on first run (no `DATABASE_URL` set). Test login: `admin` / `0000` (auto-seeded, local only).
- Tests: `tests/test_news_e2e.py` is a hand-rolled end-to-end check script (not pytest-style `test_*` functions — `python -m pytest tests/` collects zero tests and exits 5, that command does not actually verify anything despite `rules.md` §9 listing it as the pre-release check). Run it with `python -m tests.test_news_e2e` from the repo root — it spins up the real app + real JWT login + real DB tables, only faking the external network calls (`collect_all`), and exits non-zero if any of its assertions fail.
- One-off data scripts (idempotent, re-runnable): `python -m app.import_tcmsp_data data_import/tcmsp_data.json`, `python -m app.import_dark_genes`, `python -m app.import_gencc_diseases`, `python -m app.migrate_schema` (backfills schema/feature_config changes onto an existing DB — needed whenever an existing table gets new/changed columns, NOT needed for brand-new tables since `create_all()` handles those), `python -m app.seed_gencc_translations` (fills empty GenCC disease translation fields only, never overwrites existing ones).
- To point any of the above at a remote DB instead of local SQLite: set `DATABASE_URL` first (PowerShell: `$env:DATABASE_URL="postgresql://..."`).
- No linter/formatter is configured in this repo.

## Architecture

### Backend shape
- `app/main.py` — FastAPI app, CORS, router registration, a global read-only-mode middleware (see below), static mount of `frontend/` at `/app`, `Base.metadata.create_all()` + `seed_default_data()` run at startup.
- `app/database.py` — SQLAlchemy engine/session. `DATABASE_URL` env var selects Postgres; unset falls back to local SQLite (`sqlite:///./tcm_platform.db`). Two DB-session dependencies: `get_db` (normal read/write) and `get_query_db` (read-only query stations; transparently switches to a local SQLite cache when read-only mode is active and a cache exists — see `app/local_cache.py`).
- `app/models.py` — all SQLAlchemy models, one file, ~39 tables (plus enum classes). String/UUID primary keys (`gen_id()`), portable column types only (`String`/`DateTime`/`Text`/`Integer`/`Boolean`/`Enum`) — **never Postgres-only types** (`ENUM`/`ARRAY`/`JSONB`/`INET`/`GIN`), because local dev must keep working on SQLite. JSON-shaped data is stored as a `Text` column holding a JSON string.
- `app/routers/` — one router module per feature area, included in `main.py`. Each new feature area gets its own router file.
- `app/deps.py` — shared FastAPI dependencies: `get_current_user` (JWT bearer), `is_admin`/`require_admin` (role name `"管理者"` bypasses all permission checks), `require_permission(feature_code, need_execute=True)` (checks `RolePermission.can_view`/`can_execute` against `feature_config`'s feature codes), `write_audit_log(...)` (writes to the one shared `AuditLog` table — don't create a per-feature audit table).
- `app/feature_config.py` — single source of truth (`FEATURE_CONFIG` list) for every page/widget's code, nav label, page URL, and default frontend/backend visibility. `seed_default_data()` inserts new entries here into the DB **and** updates `module`/`name`/`nav_label`/`page_url`/`sort_order` on existing ones (but deliberately never overwrites `enabled`/`show_frontend`/`show_backend`, since admins edit those live via the permission-matrix UI). `migrate_schema.py` must stay in sync with this same update-vs-overwrite logic — this was a real bug (v1.32.4).
- `app/news/` — the news-aggregation module (collectors, scoring, entity linking, summarization, service layer). See `docs/news_module.md` and rules.md §5-5 for the design (external content is untrusted — escape before writing to any DOM; soft-delete with mandatory notes; audit via the shared `AuditLog` with `news_*` action names; scraper config lives in DB (`news_sources.config`), not hardcoded).
- Scheduled news collection is triggered externally via `.github/workflows/daily-news.yml` (Render free tier has no cron) hitting `POST /news/admin/collect/scheduled` with a bearer secret — compare secrets with `secrets.compare_digest`, never in a query string, and 503 if the secret isn't configured (never silently skip the check).

### Feature-flag / navigation system (core platform mechanism — read rules.md §1-2 before touching any page)
Every backend feature module is one independent `.html` page + matching `.js` file (no bundling unrelated features into one page), registered as a row in `FEATURE_CONFIG`. Three independent layers control visibility, all edited together in one modal on `roles.html` ("權限矩陣"):
1. `enabled` — global kill switch (hides from everyone including admins).
2. `show_frontend`/`show_backend` — which nav area it appears in (irrelevant for widgets with `page_url = None`).
3. Per-role `can_view` in `role_permissions` — admin role always sees everything, bypassing this table.
Nav (`js/nav.js` → `GET /nav/menu`) is the only dynamically-controlled layer; individual API endpoints still need their own `require_admin`/`require_permission()` checks — both must be kept in sync, checking the nav visibility alone is not a security boundary.

### Read-only mode / local cache (rules.md §5-3)
A global middleware in `main.py` (`enforce_read_only_mode`) blocks all POST/PUT/PATCH/DELETE except a small whitelist (`/auth/login`, `/auth/logout`, `PUT /system-settings/read-only-mode`, `POST /system-settings/backup-database`). If you add any new "operation the system must be able to perform even while read-only" (e.g. anything needed to self-recover), it must be added to `_READ_ONLY_EXEMPT_PATHS` in `main.py` — omitting this can permanently lock the system (real incident, v1.31.2). When enabling read-only mode, query-station endpoints using `get_query_db` transparently read from a rebuilt local SQLite cache instead of the remote DB; only read endpoints for query stations use `get_query_db`, admin CRUD endpoints keep `get_db` always.

### i18n (rules.md §5-2)
Four site languages: `tw` (original, untouched), `cn` (OpenCC glyph conversion, covers everything), `en`/`ko` (exact-string dictionary lookup in `frontend/js/i18n-dict.js`, so text mixed with dynamic data won't translate — expected, not a bug). Query-station pages (herb/disease/dark-gene/GenCC) don't load `nav.js` and call `window.applySiteLanguage(lang)` directly instead. Any new page or text change requires checking all four languages before shipping (see rules.md §5-2 for the scan procedure) — coverage gaps between `en` and `ko` have shipped before.

### Frontend conventions
- No bundler/framework. Every page is standalone HTML + a same-named JS file in `frontend/js/`.
- `frontend/js/api.js` holds `API_BASE`, hardcoded to the deployed Render URL (staging/dual-env `resolveApiBase()` logic is currently disabled — see CHANGELOG v1.7.0 if reviving it).
- Query-station pages (left list / right detail layout: TCMSP herb/disease, dark-gene, GenCC) share strict layout rules: anything needing to survive across selections (empty-state elements, progress bars) must be a **sibling** of the container that gets replaced via `innerHTML =`, never nested inside it — nesting inside has caused the same class of bug three times (rules.md §5-1). Chart/graph library instances (e.g. `vis.Network`) must be `.destroy()`ed and nulled before their container's `innerHTML` is overwritten, or you silently redraw into a detached DOM node.
- Graph color legend (`js/graph-legend.js`) is a shared component across all six relationship-graph pages — reuse `graphLegend.getColor('xxx')`, don't hardcode hex colors, and mount it separately for both the inline and fullscreen graph containers.

### Auth/permissions model
JWT bearer auth (`app/security.py`), role-based via `UserRole`/`Role`/`RolePermission`. No password reset flow, no JWT revocation (logout only records the logout timestamp — token remains valid until natural expiry, a known limitation).

## Versioning / release process (rules.md §9 — don't skip steps)
Every shipped version must update all five of these consistently, or the in-app version-info page will disagree with reality:
1. `app/main.py` → `FastAPI(version="x.y.z")`
2. `app/routers/project_info.py` → `APP_VERSION`
3. `README.md` → header "目前版本：vx.y.z"
4. `CHANGELOG.md` → new `## vx.y.z — YYYY-MM-DD (summary)` section at the top
5. `git_push.bat` → `DEFAULT_MSG`

Also update `rules.md` if the change introduces a new convention or a lesson future contributors need. Before pushing: all four i18n languages checked, `python -m pytest tests/ -q` passing, versions in sync, and `git status` confirmed clean of local-only files (`.db`, `.env`, temp files).

**Git operations must be run by the user themselves in PowerShell, not by Claude through a device-bridge/remote tool** — such bridges cannot delete files, and nearly every git write operation needs to create-then-delete `.git/index.lock`; running git through one leaves a stuck lock file blocking all further git commands until manually removed. This project ships two double-clickable batch files for the user's own convenience: `update_local_folder.bat` (mirrors an extracted new-version zip into this folder via `robocopy /MIR`, preserving `.git`) and `git_push.bat` (add/commit/push in one step).
