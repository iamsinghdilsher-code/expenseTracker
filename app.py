import os
import csv
import io
import re
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
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

CATEGORIES = ["Bills", "Food", "Health", "Transport", "Entertainment", "Shopping", "Other"]
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}

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
    return result


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
        for row in reader:
            try:
                raw = row.get(amt_col, "0").replace("$", "").replace(",", "").strip() if amt_col else "0"
                amount = abs(float(raw)) if raw else 0
                if amount <= 0:
                    continue
                desc = row.get(desc_col, "").strip()[:80] if desc_col else ""
                expenses.append({
                    "date": row.get(date_col, "").strip() if date_col else "",
                    "description": desc,
                    "amount": f"{amount:.2f}",
                    "category": _detect_category(desc),
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
            "date": m.group(1),
            "description": desc,
            "amount": m.group(3),
            "category": _detect_category(desc),
        })
    return expenses[:50]


def _build_category_tree(umbrella_id):
    from database.db import get_db, get_category_tree
    conn = get_db()
    tree = get_category_tree(conn, umbrella_id)
    conn.close()
    return tree


def _save_expense(user_id, amount, category, description, date, source, umbrella_id=None):
    from database.db import get_db
    conn = get_db()
    category_id = None
    if umbrella_id:
        row = conn.execute(
            "SELECT id FROM categories WHERE name = ? AND umbrella_id = ?",
            (category, umbrella_id),
        ).fetchone()
        if row:
            category_id = row["id"]
    conn.execute(
        "INSERT INTO expenses"
        " (user_id, umbrella_id, category_id, amount, category, description,"
        "  date, source, status, confidence_score, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', 1.0, ?)",
        (user_id, umbrella_id, category_id, amount, category, description,
         date, source, datetime.now(PACIFIC).isoformat()),
    )
    conn.commit()
    conn.close()


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
        try:
            amount = float(raw_amount)
        except ValueError:
            flash("Please enter a valid amount.", "error")
            return redirect(url_for("add_expense"))
        if not date:
            date = datetime.now(PACIFIC).strftime("%Y-%m-%d")
        try:
            _save_expense(session["user_id"], amount, category, description, date, source,
                          umbrella_id=g.active_umbrella_id)
            flash(f"${amount:.2f} expense added.", "success")
        except Exception as e:
            flash(f"Could not save expense: {e}", "error")
        return redirect(url_for("add_expense"))
    today = datetime.now(PACIFIC).strftime("%Y-%m-%d")
    category_tree = _build_category_tree(g.active_umbrella_id) if g.active_umbrella_id else []
    return render_template("add_expense.html", category_tree=category_tree, today=today)


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
        extracted = _parse_receipt_text(text)
    except ImportError:
        extracted = {"ocr_unavailable": True}
    except Exception as e:
        extracted = {"error": str(e)}
    return jsonify(extracted)


@app.route("/expenses/add/statement", methods=["POST"])
@login_required
def add_expense_statement():
    if "csv_file" in request.files and request.files["csv_file"].filename:
        content = request.files["csv_file"].read().decode("utf-8", errors="ignore")
        expenses = _parse_csv_statement(content)
    elif request.form.get("paste_text", "").strip():
        expenses = _parse_text_statement(request.form["paste_text"])
    else:
        return jsonify({"error": "No file or text provided"}), 400
    return jsonify({"expenses": expenses})


@app.route("/expenses/add/bulk", methods=["POST"])
@umbrella_required
def add_expense_bulk():
    data = request.get_json(silent=True) or {}
    expenses = data.get("expenses", [])
    if not expenses:
        return jsonify({"error": "No expenses provided"}), 400
    saved = 0
    try:
        for exp in expenses:
            _save_expense(
                session["user_id"],
                float(exp["amount"]),
                exp.get("category", "Other"),
                exp.get("description", ""),
                exp.get("date", datetime.now(PACIFIC).strftime("%Y-%m-%d")),
                "statement",
                umbrella_id=g.active_umbrella_id,
            )
            saved += 1
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"saved": saved})


# ------------------------------------------------------------------ #
# Edit / Delete                                                       #
# ------------------------------------------------------------------ #

@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
@umbrella_required
def edit_expense(id):
    from database.db import get_db
    conn = get_db()
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
        conn.execute(
            "UPDATE expenses SET amount=?, category=?, category_id=?, description=?, date=?"
            " WHERE id=? AND user_id=?",
            (amount, category, category_id, description, date, id, session["user_id"]),
        )
        conn.commit()
        conn.close()
        flash("Expense updated.", "success")
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
    conn.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?", (id, session["user_id"])
    )
    conn.commit()
    conn.close()
    flash("Expense deleted.", "success")
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


if __name__ == "__main__":
    from database.db import init_db
    init_db()
    app.run(debug=True, port=5001)
