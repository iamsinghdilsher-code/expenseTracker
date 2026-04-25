# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server (debug mode, port 5001)
python app.py

# Run tests
pytest

# Run a single test file
pytest tests/test_auth.py -v

# Update knowledge graph after modifying code files
graphify update .
```

Tesseract OCR must be installed separately (Windows default path `C:\Program Files\Tesseract-OCR\tesseract.exe` is auto-detected). Set `ANTHROPIC_API_KEY` to enable LLM-based receipt parsing and batch categorization; the app falls back to regex if the key is absent.

## Current State (as of 2026-04-24, Phase 9 complete)

Flask expense tracker ("Spendly") — Jinja2 templates, SQLite, no ORM. Phases 1–6 are complete. The app is fully multi-tenant with umbrella-scoped data, a Power User admin dashboard, and an LLM-assisted ingestion pipeline.

### What Is Implemented

**Auth & access control**: `/register`, `/login`, `/logout`. Three route guards stack on top of each other: `login_required` → `umbrella_required` → `power_required`. `load_user()` (`@app.before_request`) populates `g.user`, `g.active_umbrella_id`, `g.active_umbrella`, and `g.umbrellas` on every request; `inject_user()` context processor makes these available in every template.

**Multi-tenant umbrella model**: Every expense, category, and payment method belongs to an umbrella. Users can belong to multiple umbrellas; `/switch-umbrella/<id>` updates `session["active_umbrella_id"]`. Normal users are isolated to their own data within permitted umbrellas. Power users (`role = 'power'`) bypass the `user_id` filter and can edit/delete any expense.

**Expense CRUD**: Dashboard (`/expenses`), add, edit, delete, CSV export — all umbrella-aware. Edit/delete allow power users to operate cross-user.

**Ingestion pipeline** — three paths, all funnel into `_save_expense()`:
- Manual form → `add_expense()` POST
- Photo upload → `add_expense_photo()` (JSON) → `_llm_parse_receipt()` → prefills form → manual confirm
- CSV / PDF / pasted text → `add_expense_statement()` (JSON) → `_llm_categorize_batch()` → user reviews table → `add_expense_bulk()` (JSON)

**LLM features** (requires `ANTHROPIC_API_KEY`): `_llm_parse_receipt()` and `_llm_categorize_batch()` call `claude-haiku-4-5-20251001` with an ephemeral-cached system prompt. Both fall back to regex silently if the key is absent.

**Confidence gating & deduplication**: `_save_expense()` auto-downgrades status to `'draft'` when `confidence_score < 0.85`. Deduplication uses a SHA-256 hash of `"user_id:amount:.2f:date:description"` stored in `expenses.dedup_hash` (partial unique index, NULLs excluded for legacy rows).

**Payment method registry**: `/payment-methods` CRUD. `_extract_last_four()` pulls card digits from OCR/CSV text; `_match_payment_method()` looks up the umbrella's registered cards. Unmatched cards set `status = 'draft'`.

**Admin dashboard** (`/admin`, power users only):
- Summary stats, month navigator, spending charts (by umbrella, by category, 6-month trend bar)
- Per-user spending table
- Draft queue with one-click Confirm, Edit, Delete
- Budget overview with inline progress bars

**Budget tracker** (`/admin/budgets`): Power User sets monthly limits per `(umbrella, category, month)`. Upserted via `INSERT … ON CONFLICT DO UPDATE`.

**Seed data**: `seed_db(user_id)` (called at registration) creates a Home umbrella, seeds the 7 default categories, and inserts 17 sample expenses.

**Permission Manager** (`/admin/users`, power users only):
- All-users table with role badges (normal/power), umbrella memberships, per-user grant/revoke
- Role toggle: promote normal → power or demote power → normal (cannot self-demote)
- Invite links: power user generates a single-use token URL (`/invite/<token>`); any logged-in user who visits it is added to the target umbrella and switched to it; token is marked used

### What Is Implemented (Phases 8–9)

- **Phase 8 — Audit Trail**: `audit_log` table, `_log_audit()` helper, `/admin/audit` filterable view (by entity type, action, actor, date range). 20 call sites covering all mutations. Accessible via "Audit Trail" button on admin dashboard.
- **Phase 9 — Email Ingestion**: `POST /webhooks/email/inbound` secured by `WEBHOOK_SECRET` env var. Accepts Postmark inbound JSON — parses PDF/CSV/image attachments and email body text through existing parsers (`_parse_pdf_statement`, `_parse_csv_statement`, `_llm_parse_receipt`, `_parse_text_statement`). Saves as `status='draft'` expenses. Webhook URL shown on admin dashboard when `WEBHOOK_SECRET` is set. New `source='email'` value on expenses.

---

## Architecture

### Single-file routing (`app.py`)

All routes live in `app.py`. Route groups:

| Group | Routes |
|---|---|
| Public | `/`, `/terms`, `/privacy` |
| Auth | `/register`, `/login`, `/logout`, `/switch-umbrella/<id>` |
| Profile | `/profile` |
| Expenses | `/expenses`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete`, `/expenses/export` |
| Ingestion (JSON APIs) | `/expenses/add/photo`, `/expenses/add/statement`, `/expenses/add/bulk` |
| Payment methods | `/payment-methods`, `/payment-methods/add`, `/payment-methods/<id>/edit`, `/payment-methods/<id>/delete` |
| Admin | `/admin`, `/admin/expenses/<id>/confirm`, `/admin/expenses/<id>/delete`, `/admin/budgets`, `/admin/budgets/set`, `/admin/budgets/<id>/delete` |
| Permission Manager | `/admin/users`, `/admin/users/<id>/role`, `/admin/users/<id>/umbrella/grant`, `/admin/users/<user_id>/umbrella/<umbrella_id>/revoke`, `/admin/invites/create`, `/admin/invites/<id>/delete`, `/invite/<token>` |

### Database (`database/db.py`)

SQLite with `row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`. `get_db()` opens a new connection each call — callers must close it. No connection pooling.

**Tables**: `users` · `umbrellas` · `umbrella_access` · `categories` (tree via `parent_id`) · `payment_methods` · `expenses` · `budgets`

Column migrations run inside `init_db()` wrapped in individual try/except blocks so a duplicate-column error on an existing DB doesn't abort the rest.

`get_category_tree(conn, umbrella_id)` returns `[{id, name, children:[{id, name}]}]` — used everywhere a category dropdown or filter needs the tree.

### Frontend

All pages extend `templates/base.html`. `_macros.html` contains the `category_select` macro. Charts use Chart.js 4.4 loaded from CDN (doughnut on dashboard, bar + doughnut + line on admin). CSS design system in `static/css/style.css` — CSS variables, green `#1a472a` / orange `#c17f24` palette, DM Serif Display / DM Sans fonts.

### Key invariants

- `CATEGORIES` list in `app.py` is the canonical 7-item flat list used for category dropdowns, budget forms, and `_detect_category()` regex fallback. The DB stores these as top-level rows in the `categories` table per umbrella.
- Timezone is Pacific (`America/Los_Angeles`) throughout — all `datetime.now()` calls use `PACIFIC`.
- Upload folder is `uploads/` (gitignored); max 16 MB.
- Currency is USD throughout.

---

## graphify

This project has a graphify knowledge graph at `graphify-out/`.

- Before answering architecture or codebase questions, read `graphify-out/GRAPH_REPORT.md` for god nodes and community structure
- If `graphify-out/wiki/index.md` exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
