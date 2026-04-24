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

# Update knowledge graph after modifying code files
graphify update .
```

## Current State (as of 2026-04-24)

This is a Flask expense tracker application ("Spendly") using Jinja2 templates and SQLite.
It is a single-tenant app being evolved into a multi-tenant family/business financial system.

### What Is Implemented

**Auth**: `/register`, `/login`, `/logout` — full session auth with password hashing (werkzeug).
`login_required` decorator guards all protected routes. `load_user()` runs before every request
and injects `current_user` into all templates via context processor.

**Expense CRUD**: `/expenses` (dashboard), `/expenses/add`, `/expenses/<id>/edit`,
`/expenses/<id>/delete`, `/expenses/export` — all fully implemented.

**Ingestion pipeline** (three methods on the add expense page):
- Manual form entry
- Photo upload → Tesseract OCR → `_parse_receipt_text()` → pre-fills form
- CSV file or pasted text → `_parse_csv_statement()` / `_parse_text_statement()` → bulk import

**Auto-categorization**: `_detect_category(description)` uses regex against ~15 hardcoded
merchant keywords. Returns one of 7 flat categories: Bills, Food, Health, Transport,
Entertainment, Shopping, Other.

**Profile**: `/profile` — name update, password change, basic stats (expense count, total, top category).

**Public pages**: `/` (landing), `/terms`, `/privacy`.

### What Is NOT Yet Implemented (see Roadmap below)

- Multi-tenant umbrella architecture (Home / Business 1 / Business 2)
- Hierarchical categories (parent > child tree)
- Power User role with global cross-umbrella view
- Payment method registry + automated card-owner matching
- PDF statement parser
- LLM-based semantic categorization
- Confidence scoring / draft state for low-confidence expenses
- Deduplication (hash-based duplicate prevention)
- Power User admin dashboard
- Permission manager (grant/revoke umbrella access per user)
- Audit trail log
- Email ingestion webhook

---

## Architecture

### Routing (`app.py`)

All routes live in `app.py`. Key groupings:

| Group | Routes |
|---|---|
| Public | `/`, `/terms`, `/privacy` |
| Auth | `/register`, `/login`, `/logout` |
| Profile | `/profile` |
| Expenses | `/expenses`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete`, `/expenses/export` |
| Ingestion | `/expenses/add/photo` (OCR), `/expenses/add/statement` (CSV/text), `/expenses/add/bulk` (JSON batch save) |

### Templates

All pages extend `templates/base.html` (shared navbar + footer).
`current_user` is available in every template via context processor.

### Database (`database/db.py`)

SQLite with `row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`.
Database file `expense_tracker.db` is gitignored.

**Current tables**: `users`, `expenses`

**Planned tables** (see Roadmap):
`umbrellas`, `umbrella_access`, `categories` (hierarchical), `payment_methods`,
`audit_log` — plus new columns on `expenses`: `umbrella_id`, `category_id`,
`payment_method_id`, `confidence_score`, `status`

### Frontend

CSS design system in `static/css/style.css` — CSS variables, green (`#1a472a`) and
orange (`#c17f24`) palette, DM Serif Display / DM Sans fonts.
`static/js/main.js` is currently minimal.

### Constants

- Currency: US Dollar ($) throughout
- Timezone: Pacific Time (`America/Los_Angeles`)
- Upload folder: `uploads/` (gitignored)
- Max upload size: 16 MB

---

## Development Roadmap

The full plan is a 9-phase build. **Phases 1–3 are blockers for everything else.**

### Phase 1 — Restructure the Database
1. Add `umbrellas` table (Home, Business 1, Business 2 — each with an owner_id)
2. Add `role` column to `users` (`power` or `normal`)
3. Add `umbrella_access` table (maps user ↔ umbrella with role scope)
4. Rebuild `categories` as a tree (`parent_id`, `umbrella_id`) replacing the flat 7-item list
5. Add `payment_methods` table (last_four, bank_name, card_type, user_id, umbrella_id)
6. Add columns to `expenses`: `umbrella_id`, `category_id`, `payment_method_id`,
   `confidence_score` (float), `status` (draft | confirmed)
7. Write migration script to move existing data without loss

### Phase 2 — Auth & Access Control
8. On registration: create/join an umbrella, store `active_umbrella_id` in session
9. Add `umbrella_required` guard alongside `login_required`
10. Power User (`role = power`) bypasses data isolation filters
11. Normal User sees only their own expenses within permitted umbrellas
12. Updated seed script creates default umbrellas + categories

### Phase 3 — Rebuild Expense Flow (Umbrella-Aware)
13. Dashboard filters by `umbrella_id` + hierarchical `category_id`
14. Add/edit/delete attach `umbrella_id` from session
15. Category dropdown shows parent > child tree
16. Pie chart breaks down by sub-category within active umbrella
17. CSV export includes umbrella + full category path

### Phase 4 — Payment Method Registry + Card Mapping
18. `/payment-methods` CRUD (add/edit/delete cards)
19. Matching function: extracted last-4 → lookup `payment_methods` → return owner + umbrella
20. Photo upload: OCR → extract last-4 → auto-assign owner
21. CSV/statement import: extract last-4 per row → auto-assign owner
22. No match → status = `draft`

### Phase 5 — Smarter Ingestion Pipeline
23. LLM call replaces regex `_parse_receipt_text` — extract merchant, amount, date, last-4
24. PDF statement parser (pdfplumber) for credit card PDF statements
25. LLM categorization: merchant + user history → category + umbrella + confidence score
26. Confidence gating: score < 0.85 → status = `draft`, else auto-confirm
27. Deduplication: hash `(user_id, amount, date, description)` before insert

### Phase 6 — Power User Dashboard
28. `/admin` route (Power User only)
29. Consolidated view across all umbrellas and users
30. Draft queue: all `status = draft` expenses, one-click confirm/edit
31. Spending charts: by umbrella, by user, by category, by month
32. Budget tracker: Power User sets monthly budget per umbrella/category

### Phase 7 — Permission Manager
33. `/admin/users` — list users with roles and umbrella access
34. Promote/demote users (normal ↔ power)
35. Grant/revoke umbrella access per user
36. Invite link system: new user joins pre-assigned umbrella + role

### Phase 8 — Audit Trail
37. `audit_log` table: event_type, user_id, target, old_value, new_value, timestamp
38. Log: expense CRUD, AI suggestion vs. human override, permission changes, login/logout
39. `/admin/audit` filterable view for Power User

### Phase 9 — Email Ingestion
40. Inbound email webhook (Postmark or SendGrid)
41. Sender address → match to user
42. Attachment (PDF/image) → route to existing parsers
43. Receipt in email body → LLM extracts merchant + amount
44. Save as `draft` tagged to sender's user + default umbrella

---

## graphify

This project has a graphify knowledge graph at `graphify-out/`.

Rules:
- Before answering architecture or codebase questions, read `graphify-out/GRAPH_REPORT.md`
  for god nodes and community structure
- If `graphify-out/wiki/index.md` exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph
  current (AST-only, no API cost)
