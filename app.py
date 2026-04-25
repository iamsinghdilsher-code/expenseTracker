import os
import csv
import hashlib
import io
import re
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from zoneinfo import ZoneInfo
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify, session, g, Response)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

os.environ.setdefault("TZ", "America/Los_Angeles")
PACIFIC = ZoneInfo("America/Los_Angeles")

# Point pytesseract at the Windows default install location if tesseract isn't on PATH
_TESSERACT_WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.name == "nt" and os.path.isfile(_TESSERACT_WIN):
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_WIN
    except ImportError:
        pass

app = Flask(__name__)
app.config["TIMEZONE"] = "America/Los_Angeles"
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    if os.environ.get("FLASK_ENV") == "production":
        raise RuntimeError("SECRET_KEY environment variable must be set in production")
    _secret_key = "dev-secret-change-in-prod"
app.config["SECRET_KEY"] = _secret_key
app.config["UPLOAD_FOLDER"] = os.environ.get(
    "UPLOAD_FOLDER",
    os.path.join(os.path.dirname(__file__), "uploads")
)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

CATEGORIES = ["Bills", "Food", "Health", "Transport", "Entertainment", "Shopping", "Other"]


class DuplicateExpenseError(Exception):
    pass

ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
CARD_TYPES = ["Visa", "Mastercard", "Amex", "Discover", "Other"]

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


# ------------------------------------------------------------------ #
# Auth helpers                                                        #
# ------------------------------------------------------------------ #

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def power_required(f):
    """Requires a logged-in Power User."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login"))
        if not g.user or g.user["role"] != "power":
            flash("Power User access required.", "error")
            return redirect(url_for("expenses"))
        return f(*args, **kwargs)
    return decorated


def umbrella_required(f):
    """Requires both a valid session and an active umbrella context."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login"))
        if not g.active_umbrella_id:
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.before_request
def load_user():
    g.user = None
    g.active_umbrella_id = None
    g.active_umbrella = None
    g.umbrellas = []
    if "user_id" in session:
        from database.db import get_db
        conn = get_db()
        g.user = conn.execute(
            "SELECT id, name, email, role FROM users WHERE id = ?", (session["user_id"],)
        ).fetchone()
        if "active_umbrella_id" not in session:
            row = conn.execute(
                "SELECT umbrella_id FROM umbrella_access WHERE user_id = ? LIMIT 1",
                (session["user_id"],),
            ).fetchone()
            if row:
                session["active_umbrella_id"] = row["umbrella_id"]
        g.active_umbrella_id = session.get("active_umbrella_id")
        g.umbrellas = conn.execute(
            "SELECT u.id, u.name FROM umbrellas u"
            " JOIN umbrella_access ua ON ua.umbrella_id = u.id"
            " WHERE ua.user_id = ? ORDER BY u.name",
            (session["user_id"],),
        ).fetchall()
        if g.active_umbrella_id:
            g.active_umbrella = conn.execute(
                "SELECT id, name FROM umbrellas WHERE id = ?", (g.active_umbrella_id,)
            ).fetchone()
        conn.close()


@app.context_processor
def inject_user():
    return {
        "current_user": g.user,
        "active_umbrella_id": g.active_umbrella_id,
        "active_umbrella": g.active_umbrella,
        "user_umbrellas": g.umbrellas,
    }


# ------------------------------------------------------------------ #
# Parsing helpers                                                     #
# ------------------------------------------------------------------ #

def _allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXT


def _detect_category(description):
    d = description.upper()
    if re.search(r'\b(GAS|FUEL|SHELL|CHEVRON|ARCO|COSTCO\s*GAS|EXXON|BP|MOBIL|TEXACO|SINCLAIR)\b', d):
        return "Transport"
    if re.search(r'\b(RESTAURANT|CAFE|COFFEE|PIZZA|BURGER|MCDONALD|SUBWAY|STARBUCKS|GROCERY|SAFEWAY|WHOLEFOOD|KROGER|TRADER\s*JOE)\b', d):
        return "Food"
    if re.search(r'\b(AMAZON|WALMART|TARGET|COSTCO|BEST\s*BUY|HOME\s*DEPOT|NORDSTROM)\b', d):
        return "Shopping"
    if re.search(r'\b(NETFLIX|HULU|SPOTIFY|DISNEY|APPLE|GOOGLE\s*PLAY)\b', d):
        return "Entertainment"
    if re.search(r'\b(HOSPITAL|PHARMACY|CVS|WALGREEN|DOCTOR|CLINIC)\b', d):
        return "Health"
    if re.search(r'\b(ELECTRIC|WATER|INTERNET|INSURANCE|PG&E|AT&T|VERIZON|COMCAST|T-MOBILE)\b', d):
        return "Bills"
    return "Other"


def _extract_last_four(text):
    """Extract card last-4 digits from text (OCR output or transaction description)."""
    if not text:
        return None
    for pat in [
        r'(?:x{2,4}|[*]{2,4})[-\s]?(\d{4})\b',
        r'ending\s+(?:in\s+)?(\d{4})\b',
        r'\b[xX]{4}(\d{4})\b',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _match_payment_method(last_four, umbrella_id):
    """Return payment_method id if last_four matches a registered card in the umbrella."""
    if not last_four or not umbrella_id:
        return None
    from database.db import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM payment_methods WHERE last_four = ? AND umbrella_id = ?",
        (last_four, umbrella_id),
    ).fetchone()
    conn.close()
    return row["id"] if row else None


def _parse_receipt_text(text):
    result = {}
    amount_match = re.search(
        r'(?:total|amount|subtotal|due|charged)[:\s]+\$?(\d+\.?\d*)', text, re.IGNORECASE
    )
    if not amount_match:
        amount_match = re.search(r'\$(\d+\.\d{2})', text)
    if amount_match:
        result["amount"] = amount_match.group(1)
    date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', text)
    if date_match:
        result["date"] = date_match.group(1)
    # Prefer an explicit "Merchant" field (e.g. Citi alert emails)
    merchant_match = re.search(r'merchant[:\s]*\n?\s*(.+)', text, re.IGNORECASE)
    if merchant_match:
        result["description"] = merchant_match.group(1).strip()[:80]
    else:
        _junk = re.compile(r'(custom\s*alert|\balert\b|©|copyright)', re.IGNORECASE)
        lines = [l.strip() for l in text.split("\n") if l.strip() and not _junk.search(l)]
        if lines:
            result["description"] = lines[0][:80]
    result["category"] = _detect_category(result.get("description", ""))
    result["last_four"] = _extract_last_four(text)
    return result


def _normalize_date(raw):
    """Convert common date formats to YYYY-MM-DD for SQLite strftime compatibility."""
    if not raw:
        return datetime.now(PACIFIC).strftime("%Y-%m-%d")
    raw = raw.strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', raw):
        return raw
    m = re.match(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$', raw)
    if m:
        mo, day, yr = m.group(1), m.group(2), m.group(3)
        yr = "20" + yr if len(yr) == 2 else yr
        return f"{yr}-{mo.zfill(2)}-{day.zfill(2)}"
    m = re.match(r'^(\d{1,2})[/-](\d{1,2})$', raw)
    if m:
        yr = datetime.now(PACIFIC).strftime("%Y")
        return f"{yr}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
    return datetime.now(PACIFIC).strftime("%Y-%m-%d")


def _parse_csv_statement(content):
    expenses = []
    try:
        reader = csv.DictReader(io.StringIO(content))
        fieldnames = reader.fieldnames or []
        date_col = next((h for h in fieldnames if "date" in h.lower()), None)
        desc_col = next(
            (h for h in fieldnames if any(k in h.lower() for k in ["desc", "merchant", "name", "detail", "memo"])),
            None,
        )
        amt_col = next(
            (h for h in fieldnames if any(k in h.lower() for k in ["amount", "debit", "charge"])),
            None,
        )
        card_col = next(
            (h for h in fieldnames if any(k in h.lower() for k in ["card", "last four", "last 4", "last4", "account"])),
            None,
        )
        for row in reader:
            try:
                raw = row.get(amt_col, "0").replace("$", "").replace(",", "").strip() if amt_col else "0"
                amount = abs(float(raw)) if raw else 0
                if amount <= 0:
                    continue
                desc = row.get(desc_col, "").strip()[:80] if desc_col else ""
                raw_card = row.get(card_col, "").strip() if card_col else ""
                expenses.append({
                    "date": _normalize_date(row.get(date_col, "") if date_col else ""),
                    "description": desc,
                    "amount": f"{amount:.2f}",
                    "category": _detect_category(desc),
                    "last_four": _extract_last_four(raw_card) or _extract_last_four(desc),
                })
            except (ValueError, TypeError):
                continue
    except Exception:
        pass
    return expenses[:50]


def _parse_text_statement(text):
    expenses = []
    pattern = re.compile(
        r'(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s+(.+?)\s+\$?(\d+\.\d{2})',
        re.MULTILINE,
    )
    for m in pattern.finditer(text):
        desc = m.group(2).strip()[:80]
        expenses.append({
            "date": _normalize_date(m.group(1)),
            "description": desc,
            "amount": m.group(3),
            "category": _detect_category(desc),
            "last_four": _extract_last_four(desc),
        })
    return expenses[:50]


def _llm_parse_receipt(text):
    """LLM-based receipt parser. Falls back to regex when ANTHROPIC_API_KEY is unset."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        result = _parse_receipt_text(text)
        result.setdefault("confidence_score", 0.7)
        return result
    try:
        import anthropic, json as _json
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=[{
                "type": "text",
                "text": (
                    "Extract expense data from receipt or transaction text. "
                    "Return ONLY a JSON object with: merchant (string), "
                    "amount (number or null), date (YYYY-MM-DD or null), "
                    "last_four (4-digit string or null), "
                    "category (Bills|Food|Health|Transport|Entertainment|Shopping|Other), "
                    "confidence (float 0-1)."
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": text[:2000]}],
        )
        data = _json.loads(msg.content[0].text)
        return {
            "description": (data.get("merchant") or "").strip()[:80],
            "amount": f"{data['amount']:.2f}" if data.get("amount") else None,
            "date": data.get("date") or "",
            "last_four": data.get("last_four"),
            "category": data.get("category", "Other"),
            "confidence_score": float(data.get("confidence", 0.8)),
        }
    except Exception:
        result = _parse_receipt_text(text)
        result.setdefault("confidence_score", 0.7)
        return result


def _llm_categorize_batch(items):
    """LLM categorization for a list of expense dicts. Adds/updates category + confidence_score."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not items:
        for item in items:
            item.setdefault("confidence_score", 0.7)
        return items
    try:
        import anthropic, json as _json
        client = anthropic.Anthropic(api_key=api_key)
        lines = "\n".join(
            f"{i+1}. {item.get('description', '')} ${item.get('amount', '0')}"
            for i, item in enumerate(items)
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=[{
                "type": "text",
                "text": (
                    "Categorize bank transactions into one of: "
                    "Bills, Food, Health, Transport, Entertainment, Shopping, Other. "
                    "Return ONLY a JSON array, one element per transaction in order, "
                    "each with 'category' (string) and 'confidence' (float 0-1)."
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": lines}],
        )
        results = _json.loads(msg.content[0].text)
        for i, item in enumerate(items):
            if i < len(results):
                item["category"] = results[i].get("category", item.get("category", "Other"))
                item["confidence_score"] = float(results[i].get("confidence", 0.8))
            else:
                item.setdefault("confidence_score", 0.8)
    except Exception:
        for item in items:
            item.setdefault("confidence_score", 0.7)
    return items


def _parse_pdf_statement(file_bytes):
    """Extract expenses from a PDF bank statement using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        return []
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                for row in (table or []):
                    if row:
                        text_parts.append("  ".join(str(c or "").strip() for c in row))
            raw = page.extract_text()
            if raw:
                text_parts.append(raw)
    return _parse_text_statement("\n".join(text_parts))


def _build_category_tree(umbrella_id):
    from database.db import get_db, get_category_tree
    conn = get_db()
    tree = get_category_tree(conn, umbrella_id)
    conn.close()
    return tree


def _save_expense(user_id, amount, category, description, date, source, umbrella_id=None,
                  payment_method_id=None, status='confirmed', confidence_score=1.0):
    from database.db import get_db
    if confidence_score < 0.85 and status == 'confirmed':
        status = 'draft'
    dedup_hash = hashlib.sha256(
        f"{user_id}:{amount:.2f}:{date}:{description.lower().strip()}".encode()
    ).hexdigest()
    conn = get_db()
    category_id = None
    if umbrella_id:
        row = conn.execute(
            "SELECT id FROM categories WHERE name = ? AND umbrella_id = ?",
            (category, umbrella_id),
        ).fetchone()
        if row:
            category_id = row["id"]
    try:
        cur = conn.execute(
            "INSERT INTO expenses"
            " (user_id, umbrella_id, category_id, payment_method_id, amount, category, description,"
            "  date, source, status, confidence_score, dedup_hash, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, umbrella_id, category_id, payment_method_id, amount, category, description,
             date, source, status, confidence_score, dedup_hash, datetime.now(PACIFIC).isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        raise DuplicateExpenseError(f"{description} ${amount:.2f} on {date}")
    finally:
        conn.close()


def _log_audit(action, entity_type, entity_id, description, umbrella_id=None,
               actor_id=None, actor_name=None):
    """Append one row to audit_log. actor_id/actor_name default to the current session user."""
    from database.db import get_db
    try:
        if actor_id is None:
            actor_id = session.get("user_id")
        if actor_name is None:
            actor_name = (g.user["name"] if g.user else "") or ""
        conn = get_db()
        conn.execute(
            "INSERT INTO audit_log"
            " (timestamp, actor_id, actor_name, action, entity_type, entity_id, umbrella_id, description)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now(PACIFIC).isoformat(), actor_id, actor_name,
             action, entity_type, entity_id, umbrella_id, description),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _parse_email_sender(from_field):
    """Return bare lowercase email address from 'Name <email>' or plain 'email' string."""
    m = re.search(r'<([^>]+)>', from_field or '')
    return (m.group(1) if m else (from_field or '')).strip().lower()


def _strip_html(html):
    """Strip HTML tags and collapse whitespace for plain-text fallback."""
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html or '')).strip()


# ------------------------------------------------------------------ #
# Public routes                                                       #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Auth routes                                                         #
# ------------------------------------------------------------------ #

@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("expenses"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or not password:
            return render_template("register.html", error="All fields are required.")
        if len(password) < 8:
            return render_template("register.html", error="Password must be at least 8 characters.")
        from database.db import get_db, init_db, seed_db
        init_db()
        conn = get_db()
        if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            conn.close()
            return render_template("register.html", error="An account with that email already exists.")
        conn.execute(
            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(password), datetime.now(PACIFIC).isoformat()),
        )
        conn.commit()
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        session["user_id"] = user["id"]
        seed_db(user["id"])
        # Activate the Home umbrella created by seed_db
        conn2 = get_db()
        umb = conn2.execute(
            "SELECT id FROM umbrellas WHERE owner_id = ? LIMIT 1", (user["id"],)
        ).fetchone()
        conn2.close()
        if umb:
            session["active_umbrella_id"] = umb["id"]
        flash(f"Welcome to Spendly, {name}!", "success")
        return redirect(url_for("expenses"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("expenses"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        from database.db import get_db, init_db
        init_db()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            conn.close()
            return render_template("login.html", error="Incorrect email or password.")
        umb = conn.execute(
            "SELECT umbrella_id FROM umbrella_access WHERE user_id = ? LIMIT 1",
            (user["id"],),
        ).fetchone()
        conn.close()
        session["user_id"] = user["id"]
        if umb:
            session["active_umbrella_id"] = umb["umbrella_id"]
        return redirect(url_for("expenses"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/switch-umbrella/<int:umbrella_id>")
@login_required
def switch_umbrella(umbrella_id):
    from database.db import get_db
    conn = get_db()
    access = conn.execute(
        "SELECT id FROM umbrella_access WHERE user_id = ? AND umbrella_id = ?",
        (session["user_id"], umbrella_id),
    ).fetchone()
    conn.close()
    if access:
        session["active_umbrella_id"] = umbrella_id
    else:
        flash("You don't have access to that umbrella.", "error")
    return redirect(request.referrer or url_for("expenses"))


# ------------------------------------------------------------------ #
# Profile                                                             #
# ------------------------------------------------------------------ #

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    from database.db import get_db
    conn = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if name and name != user["name"]:
            conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, session["user_id"]))
            conn.commit()
            flash("Name updated.", "success")
            _log_audit("update", "profile", session["user_id"], "Updated display name")
        if current_pw or new_pw:
            if not check_password_hash(user["password_hash"], current_pw):
                conn.close()
                return render_template("profile.html", error="Current password is incorrect.")
            if len(new_pw) < 8:
                conn.close()
                return render_template("profile.html", error="New password must be at least 8 characters.")
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new_pw), session["user_id"]),
            )
            conn.commit()
            flash("Password updated.", "success")
            _log_audit("update", "profile", session["user_id"], "Changed password")
        conn.close()
        return redirect(url_for("profile"))

    stats = conn.execute("""
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total,
               strftime('%Y-%m', date) as month
        FROM expenses WHERE user_id = ?
        GROUP BY month ORDER BY month DESC LIMIT 1
    """, (session["user_id"],)).fetchone()
    top_cat = conn.execute("""
        SELECT category, SUM(amount) as total FROM expenses
        WHERE user_id = ? GROUP BY category ORDER BY total DESC LIMIT 1
    """, (session["user_id"],)).fetchone()
    all_time = conn.execute(
        "SELECT COUNT(*) as count, COALESCE(SUM(amount),0) as total FROM expenses WHERE user_id = ?",
        (session["user_id"],),
    ).fetchone()
    conn.close()
    return render_template("profile.html", stats=stats, top_cat=top_cat, all_time=all_time)


# ------------------------------------------------------------------ #
# Expenses dashboard                                                  #
# ------------------------------------------------------------------ #

@app.route("/expenses")
@umbrella_required
def expenses():
    from database.db import get_db
    now = datetime.now(PACIFIC)
    month = request.args.get("month", now.strftime("%Y-%m"))
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        month = now.strftime("%Y-%m")

    search = request.args.get("search", "").strip()
    cat_filter = request.args.get("category", "").strip()

    conn = get_db()
    is_power = g.user["role"] == "power"

    if is_power:
        query = "SELECT * FROM expenses WHERE strftime('%Y-%m', date) = ?"
        params = [month]
    else:
        query = "SELECT * FROM expenses WHERE user_id = ? AND umbrella_id = ? AND strftime('%Y-%m', date) = ?"
        params = [session["user_id"], g.active_umbrella_id, month]

    if search:
        query += " AND description LIKE ?"
        params.append(f"%{search}%")
    if cat_filter:
        query += " AND category = ?"
        params.append(cat_filter)
    query += " ORDER BY date DESC"
    rows = conn.execute(query, params).fetchall()

    # Category totals for the pie chart (always full month, no search/cat filter)
    if is_power:
        cat_rows = conn.execute(
            "SELECT category, SUM(amount) as total FROM expenses"
            " WHERE strftime('%Y-%m', date) = ? GROUP BY category",
            (month,),
        ).fetchall()
    else:
        cat_rows = conn.execute(
            "SELECT category, SUM(amount) as total FROM expenses"
            " WHERE user_id = ? AND umbrella_id = ? AND strftime('%Y-%m', date) = ?"
            " GROUP BY category",
            (session["user_id"], g.active_umbrella_id, month),
        ).fetchall()

    conn.close()

    total = sum(r["amount"] for r in rows)
    chart_labels = [r["category"] for r in cat_rows]
    chart_values = [round(r["total"], 2) for r in cat_rows]

    y, m = int(month[:4]), int(month[5:])
    prev_m = f"{y-1}-12" if m == 1 else f"{y}-{m-1:02d}"
    next_m = f"{y+1}-01" if m == 12 else f"{y}-{m+1:02d}"
    month_label = datetime.strptime(month, "%Y-%m").strftime("%B %Y")

    category_tree = _build_category_tree(g.active_umbrella_id) if g.active_umbrella_id else []

    return render_template(
        "expenses.html",
        expenses=rows,
        total=total,
        month=month,
        month_label=month_label,
        prev_month=prev_m,
        next_month=next_m,
        chart_labels=chart_labels,
        chart_values=chart_values,
        search=search,
        cat_filter=cat_filter,
        category_tree=category_tree,
    )


# ------------------------------------------------------------------ #
# Expense input — three methods                                       #
# ------------------------------------------------------------------ #

@app.route("/expenses/add", methods=["GET", "POST"])
@umbrella_required
def add_expense():
    if request.method == "POST":
        raw_amount = request.form.get("amount", "").strip()
        category = request.form.get("category", "Other")
        description = request.form.get("description", "").strip()
        date = request.form.get("date", "").strip()
        source = request.form.get("source", "manual")
        raw_pm = request.form.get("payment_method_id", "").strip()
        last_four_detected = request.form.get("last_four_detected", "").strip()
        try:
            amount = float(raw_amount)
        except ValueError:
            flash("Please enter a valid amount.", "error")
            return redirect(url_for("add_expense"))
        if not date:
            date = datetime.now(PACIFIC).strftime("%Y-%m-%d")
        payment_method_id = int(raw_pm) if raw_pm.isdigit() else None
        status = 'draft' if source == 'photo' and last_four_detected and not payment_method_id else 'confirmed'
        try:
            expense_id = _save_expense(session["user_id"], amount, category, description, date, source,
                          umbrella_id=g.active_umbrella_id,
                          payment_method_id=payment_method_id,
                          status=status)
            flash(f"${amount:.2f} expense added.", "success")
            _log_audit("create", "expense", expense_id,
                       f"${amount:.2f} {category} — {description}",
                       umbrella_id=g.active_umbrella_id)
        except DuplicateExpenseError:
            flash("Duplicate — this expense already exists and was not added.", "warning")
        except Exception as e:
            flash(f"Could not save expense: {e}", "error")
        return redirect(url_for("add_expense"))
    from database.db import get_db
    today = datetime.now(PACIFIC).strftime("%Y-%m-%d")
    category_tree = _build_category_tree(g.active_umbrella_id) if g.active_umbrella_id else []
    conn = get_db()
    pms = conn.execute(
        "SELECT id, last_four, bank_name, card_type FROM payment_methods"
        " WHERE umbrella_id = ? ORDER BY bank_name, last_four",
        (g.active_umbrella_id,),
    ).fetchall() if g.active_umbrella_id else []
    conn.close()
    return render_template("add_expense.html", category_tree=category_tree, today=today,
                           payment_methods=pms)


@app.route("/expenses/add/photo", methods=["POST"])
@login_required
def add_expense_photo():
    if "photo" not in request.files or not request.files["photo"].filename:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["photo"]
    if not _allowed_image(file.filename):
        return jsonify({"error": "Unsupported file type"}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)
    extracted = {}
    try:
        import pytesseract
        from PIL import Image
        text = pytesseract.image_to_string(Image.open(filepath))
        extracted = _llm_parse_receipt(text)
        last_four = extracted.get("last_four")
        if last_four:
            pm_id = _match_payment_method(last_four, g.active_umbrella_id)
            extracted["payment_method_id"] = pm_id
            extracted["is_draft"] = pm_id is None
        else:
            extracted["payment_method_id"] = None
            extracted["is_draft"] = False
    except ImportError:
        extracted = {"ocr_unavailable": True}
    except Exception as e:
        extracted = {"error": str(e)}
    return jsonify(extracted)


@app.route("/expenses/add/statement", methods=["POST"])
@login_required
def add_expense_statement():
    if "csv_file" in request.files and request.files["csv_file"].filename:
        f = request.files["csv_file"]
        if f.filename.lower().endswith(".pdf"):
            expenses = _parse_pdf_statement(f.read())
        else:
            expenses = _parse_csv_statement(f.read().decode("utf-8", errors="ignore"))
    elif request.form.get("paste_text", "").strip():
        expenses = _parse_text_statement(request.form["paste_text"])
    else:
        return jsonify({"error": "No file or text provided"}), 400
    if expenses:
        expenses = _llm_categorize_batch(expenses)
    return jsonify({"expenses": expenses})


@app.route("/expenses/add/bulk", methods=["POST"])
@umbrella_required
def add_expense_bulk():
    data = request.get_json(silent=True) or {}
    expenses = data.get("expenses", [])
    if not expenses:
        return jsonify({"error": "No expenses provided"}), 400
    saved = 0
    skipped = 0
    try:
        for exp in expenses:
            last_four = exp.get("last_four") or None
            pm_id = _match_payment_method(last_four, g.active_umbrella_id) if last_four else None
            status = 'draft' if last_four and pm_id is None else 'confirmed'
            try:
                _save_expense(
                    session["user_id"],
                    float(exp["amount"]),
                    exp.get("category", "Other"),
                    exp.get("description", ""),
                    exp.get("date", datetime.now(PACIFIC).strftime("%Y-%m-%d")),
                    "statement",
                    umbrella_id=g.active_umbrella_id,
                    payment_method_id=pm_id,
                    status=status,
                )
                saved += 1
            except DuplicateExpenseError:
                skipped += 1
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    if saved > 0:
        _log_audit("create", "expense", None,
                   f"Bulk import: {saved} saved, {skipped} duplicates skipped",
                   umbrella_id=g.active_umbrella_id)
    return jsonify({"saved": saved, "skipped": skipped})


# ------------------------------------------------------------------ #
# Edit / Delete                                                       #
# ------------------------------------------------------------------ #

@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
@umbrella_required
def edit_expense(id):
    from database.db import get_db
    conn = get_db()
    is_power = g.user and g.user["role"] == "power"
    if is_power:
        expense = conn.execute("SELECT * FROM expenses WHERE id = ?", (id,)).fetchone()
    else:
        expense = conn.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?", (id, session["user_id"])
        ).fetchone()
    if not expense:
        conn.close()
        flash("Expense not found.", "error")
        return redirect(url_for("expenses"))
    if request.method == "POST":
        raw_amount = request.form.get("amount", "").strip()
        category = request.form.get("category", expense["category"])
        description = request.form.get("description", "").strip()
        date = request.form.get("date", expense["date"]).strip()
        try:
            amount = float(raw_amount)
        except ValueError:
            umb_id = expense["umbrella_id"] or g.active_umbrella_id
            tree = _build_category_tree(umb_id) if umb_id else []
            conn.close()
            return render_template("edit_expense.html", expense=expense, category_tree=tree,
                                   error="Please enter a valid amount.")
        cat_row = conn.execute(
            "SELECT id FROM categories WHERE name = ? AND umbrella_id = ?",
            (category, expense["umbrella_id"]),
        ).fetchone()
        category_id = cat_row["id"] if cat_row else expense["category_id"]
        if is_power:
            conn.execute(
                "UPDATE expenses SET amount=?, category=?, category_id=?, description=?, date=?"
                " WHERE id=?",
                (amount, category, category_id, description, date, id),
            )
        else:
            conn.execute(
                "UPDATE expenses SET amount=?, category=?, category_id=?, description=?, date=?"
                " WHERE id=? AND user_id=?",
                (amount, category, category_id, description, date, id, session["user_id"]),
            )
        conn.commit()
        conn.close()
        flash("Expense updated.", "success")
        _log_audit("update", "expense", id,
                   f"Updated: {description} ${amount:.2f} ({category})",
                   umbrella_id=expense["umbrella_id"])
        return redirect(url_for("expenses"))
    umb_id = expense["umbrella_id"] or g.active_umbrella_id
    category_tree = _build_category_tree(umb_id) if umb_id else []
    conn.close()
    return render_template("edit_expense.html", expense=expense, category_tree=category_tree)


@app.route("/expenses/<int:id>/delete", methods=["POST"])
@umbrella_required
def delete_expense(id):
    from database.db import get_db
    conn = get_db()
    is_power = g.user and g.user["role"] == "power"
    expense = conn.execute("SELECT * FROM expenses WHERE id = ?", (id,)).fetchone()
    if is_power:
        conn.execute("DELETE FROM expenses WHERE id = ?", (id,))
    else:
        conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?", (id, session["user_id"])
        )
    conn.commit()
    conn.close()
    flash("Expense deleted.", "success")
    if expense:
        _log_audit("delete", "expense", id,
                   f"Deleted: {expense['description']} ${expense['amount']:.2f}",
                   umbrella_id=expense["umbrella_id"])
    return redirect(url_for("expenses"))


@app.route("/expenses/export")
@umbrella_required
def export_expenses():
    from database.db import get_db
    month = request.args.get("month", "").strip()
    if month:
        try:
            datetime.strptime(month, "%Y-%m")
        except ValueError:
            month = ""

    conn = get_db()
    is_power = g.user["role"] == "power"

    _select = (
        "SELECT e.date, e.description, e.category, e.amount, e.source,"
        " u.name AS umbrella_name,"
        " c.name AS cat_name, pc.name AS parent_cat_name"
        " FROM expenses e"
        " LEFT JOIN umbrellas u ON u.id = e.umbrella_id"
        " LEFT JOIN categories c ON c.id = e.category_id"
        " LEFT JOIN categories pc ON pc.id = c.parent_id"
    )

    if is_power:
        if month:
            rows = conn.execute(
                _select + " WHERE strftime('%Y-%m', e.date) = ? ORDER BY e.date DESC",
                (month,),
            ).fetchall()
        else:
            rows = conn.execute(_select + " ORDER BY e.date DESC").fetchall()
    else:
        if month:
            rows = conn.execute(
                _select + " WHERE e.user_id = ? AND e.umbrella_id = ?"
                " AND strftime('%Y-%m', e.date) = ? ORDER BY e.date DESC",
                (session["user_id"], g.active_umbrella_id, month),
            ).fetchall()
        else:
            rows = conn.execute(
                _select + " WHERE e.user_id = ? AND e.umbrella_id = ? ORDER BY e.date DESC",
                (session["user_id"], g.active_umbrella_id),
            ).fetchall()
    conn.close()

    filename = f"expenses_{month}.csv" if month else "expenses_all.csv"
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Date", "Description", "Category", "Amount", "Source", "Umbrella"])
    for r in rows:
        if r["parent_cat_name"] and r["cat_name"]:
            cat_path = f"{r['parent_cat_name']} > {r['cat_name']}"
        else:
            cat_path = r["cat_name"] or r["category"]
        writer.writerow([r["date"], r["description"], cat_path,
                         f"{r['amount']:.2f}", r["source"], r["umbrella_name"] or ""])

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ------------------------------------------------------------------ #
# Payment methods                                                     #
# ------------------------------------------------------------------ #

@app.route("/payment-methods")
@umbrella_required
def payment_methods():
    from database.db import get_db
    conn = get_db()
    pms = conn.execute(
        "SELECT pm.id, pm.last_four, pm.bank_name, pm.card_type, u.name AS owner_name"
        " FROM payment_methods pm"
        " JOIN users u ON u.id = pm.user_id"
        " WHERE pm.umbrella_id = ?"
        " ORDER BY pm.bank_name, pm.last_four",
        (g.active_umbrella_id,),
    ).fetchall()
    conn.close()
    return render_template("payment_methods.html", payment_methods=pms, card_types=CARD_TYPES)


@app.route("/payment-methods/add", methods=["POST"])
@umbrella_required
def add_payment_method():
    last_four = request.form.get("last_four", "").strip()
    bank_name = request.form.get("bank_name", "").strip()
    card_type = request.form.get("card_type", "Other").strip()
    if not last_four or not last_four.isdigit() or len(last_four) != 4:
        flash("Last four digits must be exactly 4 numbers.", "error")
        return redirect(url_for("payment_methods"))
    from database.db import get_db
    conn = get_db()
    if conn.execute(
        "SELECT id FROM payment_methods WHERE last_four = ? AND umbrella_id = ?",
        (last_four, g.active_umbrella_id),
    ).fetchone():
        conn.close()
        flash(f"A card ending in {last_four} is already registered.", "error")
        return redirect(url_for("payment_methods"))
    conn.execute(
        "INSERT INTO payment_methods (last_four, bank_name, card_type, user_id, umbrella_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (last_four, bank_name, card_type, session["user_id"], g.active_umbrella_id,
         datetime.now(PACIFIC).isoformat()),
    )
    conn.commit()
    conn.close()
    flash(f"Card ending in {last_four} added.", "success")
    _log_audit("create", "payment_method", None,
               f"Added card ****{last_four} ({bank_name} {card_type})",
               umbrella_id=g.active_umbrella_id)
    return redirect(url_for("payment_methods"))


@app.route("/payment-methods/<int:id>/edit", methods=["GET", "POST"])
@umbrella_required
def edit_payment_method(id):
    from database.db import get_db
    conn = get_db()
    pm = conn.execute(
        "SELECT * FROM payment_methods WHERE id = ? AND umbrella_id = ?",
        (id, g.active_umbrella_id),
    ).fetchone()
    if not pm:
        conn.close()
        flash("Payment method not found.", "error")
        return redirect(url_for("payment_methods"))
    if request.method == "POST":
        last_four = request.form.get("last_four", "").strip()
        bank_name = request.form.get("bank_name", "").strip()
        card_type = request.form.get("card_type", "Other").strip()
        if not last_four or not last_four.isdigit() or len(last_four) != 4:
            conn.close()
            return render_template("edit_payment_method.html", pm=pm, card_types=CARD_TYPES,
                                   error="Last four digits must be exactly 4 numbers.")
        conn.execute(
            "UPDATE payment_methods SET last_four=?, bank_name=?, card_type=?"
            " WHERE id=? AND umbrella_id=?",
            (last_four, bank_name, card_type, id, g.active_umbrella_id),
        )
        conn.commit()
        conn.close()
        flash("Card updated.", "success")
        _log_audit("update", "payment_method", id,
                   f"Updated card ****{last_four} ({bank_name} {card_type})",
                   umbrella_id=g.active_umbrella_id)
        return redirect(url_for("payment_methods"))
    conn.close()
    return render_template("edit_payment_method.html", pm=pm, card_types=CARD_TYPES)


@app.route("/payment-methods/<int:id>/delete", methods=["POST"])
@umbrella_required
def delete_payment_method(id):
    from database.db import get_db
    conn = get_db()
    pm = conn.execute(
        "SELECT * FROM payment_methods WHERE id = ? AND umbrella_id = ?",
        (id, g.active_umbrella_id),
    ).fetchone()
    conn.execute(
        "DELETE FROM payment_methods WHERE id = ? AND umbrella_id = ?",
        (id, g.active_umbrella_id),
    )
    conn.commit()
    conn.close()
    flash("Card removed.", "success")
    if pm:
        _log_audit("delete", "payment_method", id,
                   f"Removed card ****{pm['last_four']} ({pm['bank_name']} {pm['card_type']})",
                   umbrella_id=g.active_umbrella_id)
    return redirect(url_for("payment_methods"))


# ------------------------------------------------------------------ #
# Admin — Power User Dashboard                                        #
# ------------------------------------------------------------------ #

@app.route("/admin")
@power_required
def admin_dashboard():
    from database.db import get_db
    now = datetime.now(PACIFIC)
    month = request.args.get("month", now.strftime("%Y-%m"))
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        month = now.strftime("%Y-%m")

    conn = get_db()

    total_month = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as t FROM expenses"
        " WHERE strftime('%Y-%m', date) = ?", (month,)
    ).fetchone()["t"]
    draft_count = conn.execute(
        "SELECT COUNT(*) as c FROM expenses WHERE status = 'draft'"
    ).fetchone()["c"]
    user_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    umbrella_count = conn.execute("SELECT COUNT(*) as c FROM umbrellas").fetchone()["c"]

    umb_rows = conn.execute(
        "SELECT u.name, COALESCE(SUM(e.amount), 0) as total"
        " FROM umbrellas u"
        " LEFT JOIN expenses e ON e.umbrella_id = u.id"
        "   AND strftime('%Y-%m', e.date) = ?"
        " GROUP BY u.id, u.name ORDER BY total DESC",
        (month,),
    ).fetchall()

    cat_rows = conn.execute(
        "SELECT category, COALESCE(SUM(amount), 0) as total"
        " FROM expenses WHERE strftime('%Y-%m', date) = ?"
        " GROUP BY category ORDER BY total DESC",
        (month,),
    ).fetchall()

    user_rows = conn.execute(
        "SELECT u.name, COALESCE(SUM(e.amount), 0) as total"
        " FROM users u"
        " LEFT JOIN expenses e ON e.user_id = u.id"
        "   AND strftime('%Y-%m', e.date) = ?"
        " GROUP BY u.id, u.name ORDER BY total DESC LIMIT 10",
        (month,),
    ).fetchall()

    trend_rows = conn.execute(
        "SELECT strftime('%Y-%m', date) as m, SUM(amount) as total"
        " FROM expenses GROUP BY m ORDER BY m DESC LIMIT 6"
    ).fetchall()
    trend_rows = list(reversed(trend_rows))

    drafts = conn.execute(
        "SELECT e.*, u.name as user_name, umb.name as umbrella_name"
        " FROM expenses e"
        " JOIN users u ON u.id = e.user_id"
        " LEFT JOIN umbrellas umb ON umb.id = e.umbrella_id"
        " WHERE e.status = 'draft'"
        " ORDER BY e.created_at DESC"
    ).fetchall()

    budget_rows = conn.execute(
        "SELECT b.*, umb.name as umbrella_name,"
        " COALESCE((SELECT SUM(e.amount) FROM expenses e"
        "           WHERE e.umbrella_id = b.umbrella_id"
        "           AND e.category = b.category"
        "           AND strftime('%Y-%m', e.date) = b.month), 0) as actual"
        " FROM budgets b"
        " JOIN umbrellas umb ON umb.id = b.umbrella_id"
        " WHERE b.month = ?"
        " ORDER BY umb.name, b.category",
        (month,),
    ).fetchall()

    conn.close()

    y, m_int = int(month[:4]), int(month[5:])
    prev_m = f"{y-1}-12" if m_int == 1 else f"{y}-{m_int-1:02d}"
    next_m = f"{y+1}-01" if m_int == 12 else f"{y}-{m_int+1:02d}"
    month_label = datetime.strptime(month, "%Y-%m").strftime("%B %Y")

    webhook_secret = os.environ.get("WEBHOOK_SECRET", "")
    webhook_url = (
        url_for("email_inbound_webhook", token=webhook_secret, _external=True)
        if webhook_secret else None
    )

    return render_template(
        "admin.html",
        month=month,
        month_label=month_label,
        prev_month=prev_m,
        next_month=next_m,
        total_month=total_month,
        draft_count=draft_count,
        user_count=user_count,
        umbrella_count=umbrella_count,
        umbrella_labels=[r["name"] for r in umb_rows],
        umbrella_values=[round(r["total"], 2) for r in umb_rows],
        cat_labels=[r["category"] for r in cat_rows],
        cat_values=[round(r["total"], 2) for r in cat_rows],
        user_rows=user_rows,
        trend_labels=[r["m"] for r in trend_rows],
        trend_values=[round(r["total"], 2) for r in trend_rows],
        drafts=drafts,
        budget_rows=budget_rows,
        webhook_url=webhook_url,
        webhook_configured=bool(webhook_secret),
    )


@app.route("/admin/expenses/<int:id>/confirm", methods=["POST"])
@power_required
def admin_confirm_expense(id):
    from database.db import get_db
    month = request.form.get("month", datetime.now(PACIFIC).strftime("%Y-%m"))
    conn = get_db()
    expense = conn.execute("SELECT * FROM expenses WHERE id = ?", (id,)).fetchone()
    conn.execute("UPDATE expenses SET status = 'confirmed' WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Expense confirmed.", "success")
    if expense:
        _log_audit("confirm", "expense", id,
                   f"Confirmed draft: {expense['description']} ${expense['amount']:.2f}",
                   umbrella_id=expense["umbrella_id"])
    return redirect(url_for("admin_dashboard", month=month))


@app.route("/admin/expenses/<int:id>/delete", methods=["POST"])
@power_required
def admin_delete_expense(id):
    from database.db import get_db
    month = request.form.get("month", datetime.now(PACIFIC).strftime("%Y-%m"))
    conn = get_db()
    expense = conn.execute("SELECT * FROM expenses WHERE id = ?", (id,)).fetchone()
    conn.execute("DELETE FROM expenses WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Expense deleted.", "success")
    if expense:
        _log_audit("delete", "expense", id,
                   f"Admin deleted: {expense['description']} ${expense['amount']:.2f}",
                   umbrella_id=expense["umbrella_id"])
    return redirect(url_for("admin_dashboard", month=month))


@app.route("/admin/budgets")
@power_required
def admin_budgets():
    from database.db import get_db
    now = datetime.now(PACIFIC)
    month = request.args.get("month", now.strftime("%Y-%m"))
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        month = now.strftime("%Y-%m")

    conn = get_db()
    budget_rows = conn.execute(
        "SELECT b.*, umb.name as umbrella_name,"
        " COALESCE((SELECT SUM(e.amount) FROM expenses e"
        "           WHERE e.umbrella_id = b.umbrella_id"
        "           AND e.category = b.category"
        "           AND strftime('%Y-%m', e.date) = b.month), 0) as actual"
        " FROM budgets b"
        " JOIN umbrellas umb ON umb.id = b.umbrella_id"
        " WHERE b.month = ?"
        " ORDER BY umb.name, b.category",
        (month,),
    ).fetchall()
    umbrellas = conn.execute("SELECT id, name FROM umbrellas ORDER BY name").fetchall()
    conn.close()

    y, m_int = int(month[:4]), int(month[5:])
    prev_m = f"{y-1}-12" if m_int == 1 else f"{y}-{m_int-1:02d}"
    next_m = f"{y+1}-01" if m_int == 12 else f"{y}-{m_int+1:02d}"
    month_label = datetime.strptime(month, "%Y-%m").strftime("%B %Y")

    return render_template(
        "admin_budgets.html",
        month=month,
        month_label=month_label,
        prev_month=prev_m,
        next_month=next_m,
        budget_rows=budget_rows,
        umbrellas=umbrellas,
        categories=CATEGORIES,
    )


@app.route("/admin/budgets/set", methods=["POST"])
@power_required
def admin_set_budget():
    from database.db import get_db
    umbrella_id = request.form.get("umbrella_id", "").strip()
    category = request.form.get("category", "").strip()
    amount_raw = request.form.get("amount", "").strip()
    month = request.form.get("month", datetime.now(PACIFIC).strftime("%Y-%m")).strip()

    if not umbrella_id.isdigit() or not category or not amount_raw:
        flash("All fields are required.", "error")
        return redirect(url_for("admin_budgets", month=month))
    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        flash("Amount must be a positive number.", "error")
        return redirect(url_for("admin_budgets", month=month))

    conn = get_db()
    conn.execute(
        "INSERT INTO budgets (umbrella_id, category, month, amount, created_at)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(umbrella_id, category, month)"
        " DO UPDATE SET amount = excluded.amount",
        (int(umbrella_id), category, month, amount, datetime.now(PACIFIC).isoformat()),
    )
    conn.commit()
    conn.close()
    flash(f"Budget set: {category} for {month}.", "success")
    _log_audit("create", "budget", None,
               f"Set budget: {category} ${amount:.2f} for {month}",
               umbrella_id=int(umbrella_id))
    return redirect(url_for("admin_budgets", month=month))


@app.route("/admin/budgets/<int:id>/delete", methods=["POST"])
@power_required
def admin_delete_budget(id):
    from database.db import get_db
    conn = get_db()
    row = conn.execute("SELECT * FROM budgets WHERE id = ?", (id,)).fetchone()
    month = row["month"] if row else datetime.now(PACIFIC).strftime("%Y-%m")
    conn.execute("DELETE FROM budgets WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Budget removed.", "success")
    if row:
        _log_audit("delete", "budget", id,
                   f"Deleted budget: {row['category']} ${row['amount']:.2f} for {row['month']}",
                   umbrella_id=row["umbrella_id"])
    return redirect(url_for("admin_budgets", month=month))


# ------------------------------------------------------------------ #
# Admin — Permission Manager (Phase 7)                               #
# ------------------------------------------------------------------ #

@app.route("/admin/users")
@power_required
def admin_users():
    from database.db import get_db
    conn = get_db()

    users = conn.execute(
        "SELECT id, name, email, role, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()

    user_list = []
    for user in users:
        memberships = conn.execute(
            "SELECT ua.umbrella_id, ua.role as access_role, umb.name as umbrella_name"
            " FROM umbrella_access ua"
            " JOIN umbrellas umb ON umb.id = ua.umbrella_id"
            " WHERE ua.user_id = ? ORDER BY umb.name",
            (user["id"],),
        ).fetchall()
        user_list.append({"user": user, "memberships": memberships})

    all_umbrellas = conn.execute("SELECT id, name FROM umbrellas ORDER BY name").fetchall()

    invite_links = conn.execute(
        "SELECT il.id, il.token, il.created_at, il.used_at,"
        " umb.name as umbrella_name,"
        " creator.name as creator_name,"
        " claimer.name as claimer_name"
        " FROM invite_links il"
        " JOIN umbrellas umb ON umb.id = il.umbrella_id"
        " JOIN users creator ON creator.id = il.created_by"
        " LEFT JOIN users claimer ON claimer.id = il.used_by"
        " ORDER BY il.created_at DESC LIMIT 30"
    ).fetchall()

    conn.close()
    return render_template(
        "admin_users.html",
        user_list=user_list,
        all_umbrellas=all_umbrellas,
        invite_links=invite_links,
    )


@app.route("/admin/users/<int:id>/role", methods=["POST"])
@power_required
def admin_set_user_role(id):
    from database.db import get_db
    if id == session["user_id"]:
        flash("You cannot change your own role.", "error")
        return redirect(url_for("admin_users"))
    conn = get_db()
    user = conn.execute("SELECT id, role FROM users WHERE id = ?", (id,)).fetchone()
    if not user:
        conn.close()
        flash("User not found.", "error")
        return redirect(url_for("admin_users"))
    new_role = "power" if user["role"] == "normal" else "normal"
    old_role = user["role"]
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, id))
    conn.commit()
    conn.close()
    flash(f"Role updated to '{new_role}'.", "success")
    _log_audit("role_change", "user", id, f"Role changed: {old_role} → {new_role}")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:id>/umbrella/grant", methods=["POST"])
@power_required
def admin_grant_umbrella(id):
    from database.db import get_db
    umbrella_id = request.form.get("umbrella_id", "").strip()
    if not umbrella_id.isdigit():
        flash("Invalid umbrella.", "error")
        return redirect(url_for("admin_users"))
    conn = get_db()
    user = conn.execute("SELECT id, email FROM users WHERE id = ?", (id,)).fetchone()
    umbrella = conn.execute("SELECT id, name FROM umbrellas WHERE id = ?", (int(umbrella_id),)).fetchone()
    if not user or not umbrella:
        conn.close()
        flash("User or umbrella not found.", "error")
        return redirect(url_for("admin_users"))
    try:
        conn.execute(
            "INSERT INTO umbrella_access (user_id, umbrella_id, role, created_at)"
            " VALUES (?, ?, 'member', ?)",
            (id, int(umbrella_id), datetime.now(PACIFIC).isoformat()),
        )
        conn.commit()
        flash("Umbrella access granted.", "success")
        _log_audit("grant", "umbrella_access", None,
                   f"Granted '{umbrella['name']}' access to {user['email']}",
                   umbrella_id=int(umbrella_id))
    except sqlite3.IntegrityError:
        flash("User already has access to this umbrella.", "warning")
    conn.close()
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/umbrella/<int:umbrella_id>/revoke", methods=["POST"])
@power_required
def admin_revoke_umbrella(user_id, umbrella_id):
    from database.db import get_db
    conn = get_db()
    user = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
    umbrella = conn.execute("SELECT name FROM umbrellas WHERE id = ?", (umbrella_id,)).fetchone()
    conn.execute(
        "DELETE FROM umbrella_access WHERE user_id = ? AND umbrella_id = ?",
        (user_id, umbrella_id),
    )
    conn.commit()
    conn.close()
    flash("Umbrella access revoked.", "success")
    _log_audit("revoke", "umbrella_access", None,
               f"Revoked '{umbrella['name'] if umbrella else umbrella_id}' access from {user['email'] if user else user_id}",
               umbrella_id=umbrella_id)
    return redirect(url_for("admin_users"))


@app.route("/admin/invites/create", methods=["POST"])
@power_required
def admin_create_invite():
    from database.db import get_db
    umbrella_id = request.form.get("umbrella_id", "").strip()
    if not umbrella_id.isdigit():
        flash("Please select an umbrella.", "error")
        return redirect(url_for("admin_users"))
    token = secrets.token_urlsafe(16)
    conn = get_db()
    umbrella = conn.execute("SELECT id, name FROM umbrellas WHERE id = ?", (int(umbrella_id),)).fetchone()
    if not umbrella:
        conn.close()
        flash("Umbrella not found.", "error")
        return redirect(url_for("admin_users"))
    conn.execute(
        "INSERT INTO invite_links (token, umbrella_id, created_by, created_at)"
        " VALUES (?, ?, ?, ?)",
        (token, int(umbrella_id), session["user_id"], datetime.now(PACIFIC).isoformat()),
    )
    conn.commit()
    conn.close()
    flash("Invite link created.", "success")
    _log_audit("create", "invite", None,
               f"Created invite link for '{umbrella['name']}'",
               umbrella_id=int(umbrella_id))
    return redirect(url_for("admin_users"))


@app.route("/admin/invites/<int:id>/delete", methods=["POST"])
@power_required
def admin_delete_invite(id):
    from database.db import get_db
    conn = get_db()
    invite = conn.execute(
        "SELECT il.id, umb.name as umbrella_name FROM invite_links il"
        " JOIN umbrellas umb ON umb.id = il.umbrella_id WHERE il.id = ?", (id,)
    ).fetchone()
    conn.execute("DELETE FROM invite_links WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Invite link deleted.", "success")
    _log_audit("delete", "invite", id,
               f"Deleted invite for '{invite['umbrella_name'] if invite else '?'}'")
    return redirect(url_for("admin_users"))


@app.route("/invite/<token>")
@login_required
def use_invite(token):
    from database.db import get_db
    conn = get_db()
    link = conn.execute(
        "SELECT * FROM invite_links WHERE token = ? AND used_by IS NULL", (token,)
    ).fetchone()
    if not link:
        conn.close()
        flash("This invite link is invalid or has already been used.", "error")
        return redirect(url_for("expenses"))
    try:
        conn.execute(
            "INSERT INTO umbrella_access (user_id, umbrella_id, role, created_at)"
            " VALUES (?, ?, 'member', ?)",
            (session["user_id"], link["umbrella_id"], datetime.now(PACIFIC).isoformat()),
        )
    except sqlite3.IntegrityError:
        pass  # already a member — still mark invite used
    conn.execute(
        "UPDATE invite_links SET used_by = ?, used_at = ? WHERE id = ?",
        (session["user_id"], datetime.now(PACIFIC).isoformat(), link["id"]),
    )
    conn.commit()
    umbrella = conn.execute(
        "SELECT name FROM umbrellas WHERE id = ?", (link["umbrella_id"],)
    ).fetchone()
    conn.close()
    session["active_umbrella_id"] = link["umbrella_id"]
    flash(f"You've joined '{umbrella['name']}'!", "success")
    _log_audit("invite_use", "invite", link["id"],
               f"Used invite to join '{umbrella['name']}'",
               umbrella_id=link["umbrella_id"])
    return redirect(url_for("expenses"))


# ------------------------------------------------------------------ #
# Email Ingestion Webhook (Phase 9)                                   #
# ------------------------------------------------------------------ #

@app.route("/webhooks/email/inbound", methods=["POST"])
def email_inbound_webhook():
    """Postmark inbound webhook — parses forwarded receipts/statements into draft expenses."""
    import base64

    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret or request.args.get("token") != secret:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}

    sender_email = _parse_email_sender(data.get("From", ""))
    if not sender_email:
        return jsonify({"status": "ignored", "reason": "no sender"}), 200

    from database.db import get_db
    conn = get_db()
    user = conn.execute(
        "SELECT id, name, email FROM users WHERE LOWER(email) = ?", (sender_email,)
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({"status": "ignored", "reason": "sender not registered"}), 200

    umbrella_row = conn.execute(
        "SELECT umbrella_id FROM umbrella_access WHERE user_id = ? LIMIT 1",
        (user["id"],),
    ).fetchone()
    conn.close()
    if not umbrella_row:
        return jsonify({"status": "ignored", "reason": "no umbrella"}), 200

    umbrella_id = umbrella_row["umbrella_id"]
    subject = data.get("Subject", "") or ""

    # ---- collect parsed expense rows from attachments ----
    batch_expenses = []
    single_receipt = None

    for att in data.get("Attachments", []):
        raw = att.get("Content", "")
        if not raw:
            continue
        try:
            content = base64.b64decode(raw)
        except Exception:
            continue
        name = (att.get("Name") or "").lower()
        ctype = (att.get("ContentType") or "").lower()

        if "pdf" in ctype or name.endswith(".pdf"):
            batch_expenses.extend(_parse_pdf_statement(content))

        elif "csv" in ctype or name.endswith(".csv"):
            batch_expenses.extend(
                _parse_csv_statement(content.decode("utf-8", errors="ignore"))
            )

        elif any(name.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
            fpath = os.path.join(app.config["UPLOAD_FOLDER"],
                                 f"email_{secure_filename(att.get('Name', 'img'))}")
            try:
                with open(fpath, "wb") as fh:
                    fh.write(content)
                import pytesseract
                from PIL import Image
                text = pytesseract.image_to_string(Image.open(fpath))
                parsed = _llm_parse_receipt(text)
                if parsed.get("amount"):
                    single_receipt = parsed
            except Exception:
                pass

    # ---- fallback: parse email body if no attachment results ----
    if not batch_expenses and not single_receipt:
        body = data.get("TextBody") or _strip_html(data.get("HtmlBody", ""))
        if body:
            pattern_count = len(re.findall(
                r'\d{1,2}[/-]\d{1,2}.*?\$?\d+\.\d{2}', body, re.MULTILINE
            ))
            if pattern_count >= 3:
                batch_expenses = _parse_text_statement(body)
            else:
                parsed = _llm_parse_receipt(body)
                if parsed.get("amount"):
                    single_receipt = parsed

    if batch_expenses:
        batch_expenses = _llm_categorize_batch(batch_expenses)

    # ---- persist as draft expenses ----
    saved = 0
    skipped = 0
    today = datetime.now(PACIFIC).strftime("%Y-%m-%d")

    def _ingest_one(amount_raw, category, description, date, confidence, last_four):
        nonlocal saved, skipped
        try:
            pm_id = _match_payment_method(last_four, umbrella_id) if last_four else None
            _save_expense(
                user["id"], float(amount_raw), category,
                description[:80], date or today,
                "email", umbrella_id=umbrella_id,
                payment_method_id=pm_id,
                status="draft",
                confidence_score=float(confidence),
            )
            saved += 1
        except DuplicateExpenseError:
            skipped += 1
        except Exception:
            skipped += 1

    if single_receipt and single_receipt.get("amount"):
        _ingest_one(
            single_receipt["amount"],
            single_receipt.get("category", "Other"),
            single_receipt.get("description") or subject or "Email receipt",
            single_receipt.get("date", ""),
            single_receipt.get("confidence_score", 0.8),
            single_receipt.get("last_four"),
        )

    for exp in batch_expenses:
        if exp.get("amount"):
            _ingest_one(
                exp["amount"],
                exp.get("category", "Other"),
                exp.get("description", "") or subject,
                exp.get("date", ""),
                exp.get("confidence_score", 0.8),
                exp.get("last_four"),
            )

    if saved > 0 or skipped > 0:
        _log_audit(
            "email_ingest", "expense", None,
            f"Email from {sender_email}: {saved} saved, {skipped} skipped -- \"{subject}\"",
            umbrella_id=umbrella_id,
            actor_id=user["id"],
            actor_name=user["name"] or user["email"],
        )

    return jsonify({"status": "ok", "saved": saved, "skipped": skipped})


# ------------------------------------------------------------------ #
# Admin — Audit Trail (Phase 8)                                       #
# ------------------------------------------------------------------ #

AUDIT_ENTITY_TYPES = ["expense", "payment_method", "budget", "user", "umbrella_access", "invite", "profile"]
AUDIT_ACTIONS = ["create", "update", "delete", "confirm", "role_change", "grant", "revoke", "invite_use", "email_ingest"]


@app.route("/admin/audit")
@power_required
def admin_audit():
    from database.db import get_db
    conn = get_db()

    entity_type = request.args.get("entity_type", "").strip()
    actor_id = request.args.get("actor_id", "").strip()
    action = request.args.get("action", "").strip()
    from_date = request.args.get("from_date", "").strip()
    to_date = request.args.get("to_date", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 50

    where = "WHERE 1=1"
    params = []
    if entity_type:
        where += " AND entity_type = ?"
        params.append(entity_type)
    if actor_id and actor_id.isdigit():
        where += " AND actor_id = ?"
        params.append(int(actor_id))
    if action:
        where += " AND action = ?"
        params.append(action)
    if from_date:
        where += " AND date(timestamp) >= ?"
        params.append(from_date)
    if to_date:
        where += " AND date(timestamp) <= ?"
        params.append(to_date)

    total_count = conn.execute(
        f"SELECT COUNT(*) as c FROM audit_log {where}", params
    ).fetchone()["c"]

    logs = conn.execute(
        f"SELECT * FROM audit_log {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        params + [per_page, (page - 1) * per_page],
    ).fetchall()

    all_users = conn.execute("SELECT id, name, email FROM users ORDER BY name").fetchall()
    conn.close()

    total_pages = max(1, (total_count + per_page - 1) // per_page)

    return render_template(
        "admin_audit.html",
        logs=logs,
        all_users=all_users,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        entity_type=entity_type,
        actor_id=actor_id,
        action=action,
        from_date=from_date,
        to_date=to_date,
        entity_types=AUDIT_ENTITY_TYPES,
        actions=AUDIT_ACTIONS,
    )


from database.db import init_db
init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_ENV") != "production", port=5001)
