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
```

## Architecture

This is a Flask expense tracker application using Jinja2 templates and SQLite. It is structured as a tutorial project with intentional stubs labeled "Step X" for incremental implementation.

**Routing**: All routes live in [app.py](app.py). Currently implemented: `/`, `/login`, `/register`, `/terms`, `/privacy`. Stub routes waiting for implementation: `/logout`, `/profile`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete`.

**Templates**: All pages extend [templates/base.html](templates/base.html), which provides the shared navbar and footer. Pages are rendered via `render_template()` in `app.py`.

**Database layer**: [database/db.py](database/db.py) is a stub that students implement. The pattern is SQLite with `row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`. The database file `expense_tracker.db` is gitignored.

**Frontend**: Custom CSS design system in [static/css/style.css](static/css/style.css) uses CSS variables with a green (`#1a472a`) and orange (`#c17f24`) palette, DM Serif Display / DM Sans fonts. [static/js/main.js](static/js/main.js) is currently empty.

**Currency**: The app is designed for Indian Rupee (₹) throughout.

## Development Notes

- Flask runs with `debug=True` on port 5001.
- No authentication is implemented yet — login/register forms exist but have no backend handling.
- `database/db.py` functions (`get_db`, `init_db`, `seed_db`) are placeholder stubs.
