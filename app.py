from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
import csv
import os
import re
from functools import wraps
from calendar import monthrange

from dotenv import load_dotenv
from flask import Flask, Response, abort, flash, redirect, render_template, request, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

load_dotenv()
app = Flask(__name__)
app.config.from_object("config.Config")
if app.config["ENV"] == "production" and not app.config["SECRET_KEY"]:
    raise RuntimeError("SECRET_KEY must be configured in production.")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, storage_uri=app.config["RATELIMIT_STORAGE_URI"], default_limits=[app.config["RATELIMIT_DEFAULT"]])


@app.after_request
def add_csrf_tokens(response):
    """Inject tokens into legacy server-rendered POST forms without changing their layout."""
    if response.mimetype == "text/html":
        token = generate_csrf()
        html = response.get_data(as_text=True)
        html = re.sub(r'(<form\b[^>]*\bmethod=["\']post["\'][^>]*)>', rf'\1><input type="hidden" name="csrf_token" value="{token}">', html, flags=re.I)
        response.set_data(html)
    return response


def utc_now():
    return datetime.now(UTC)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="customer")
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    customer = db.relationship("Customer", foreign_keys=[customer_id], backref=db.backref("user", uselist=False))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Customer(db.Model):
    __tablename__ = "customers"
    id = db.Column(db.Integer, primary_key=True)
    customer_code = db.Column(db.String(16), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(25), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    accounts = db.relationship("Account", backref="customer", lazy=True, cascade="all, delete-orphan")


class Account(db.Model):
    __tablename__ = "accounts"
    id = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(24), unique=True, nullable=False)
    account_type = db.Column(db.String(30), nullable=False, default="Savings")
    opening_balance = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="Active")
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    transactions = db.relationship("Transaction", backref="account", lazy=True, cascade="all, delete-orphan")

    @property
    def balance(self):
        total = self.opening_balance or Decimal("0")
        for tx in self.transactions:
            total += tx.amount if tx.transaction_type == "Deposit" else -tx.amount
        return total


class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer, primary_key=True)
    transaction_code = db.Column(db.String(20), unique=True, nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    transaction_type = db.Column(db.String(12), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    transaction_date = db.Column(db.Date, nullable=False, default=date.today)
    description = db.Column(db.String(200), nullable=True)
    is_unusual = db.Column(db.Boolean, default=False, nullable=False)
    unusual_reason = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)


def next_code(prefix, model, field):
    last = db.session.query(func.max(field)).scalar()
    try:
        n = int(last.split("-")[-1]) + 1 if last else 1
    except (ValueError, AttributeError):
        n = 1
    return f"{prefix}-{n:05d}"


def money(value):
    return f"₹{Decimal(value or 0):,.2f}"


@app.template_filter("money")
def money_filter(value):
    return money(value)


@app.context_processor
def template_dates():
    return {"today": date.today().isoformat()}


def transaction_flag(tx_type, amount, account):
    limit = Decimal(str(app.config["UNUSUAL_TRANSACTION_LIMIT"]))
    reasons = []
    if amount >= limit:
        reasons.append(f"High-value transaction (≥ {money(limit)})")
    historical = [t.amount for t in account.transactions]
    if len(historical) >= 3:
        average = sum(historical, Decimal("0")) / len(historical)
        if average and amount >= average * 3:
            reasons.append("Amount is at least three times the account's prior average")
    if tx_type == "Withdrawal":
        recent_withdrawals = [t for t in account.transactions if t.transaction_type == "Withdrawal" and (date.today() - t.transaction_date).days <= 1]
        if len(recent_withdrawals) >= 3:
            reasons.append("Frequent withdrawal pattern (three or more in 24 hours)")
    return bool(reasons), "; ".join(reasons) or None


def transaction_frame(account_ids=None):
    """Return a Pandas data set used by the dashboard, reports, and chart export."""
    query = Transaction.query if account_ids is None else Transaction.query.filter(Transaction.account_id.in_(account_ids))
    records = [{"date": tx.transaction_date, "type": tx.transaction_type, "amount": float(tx.amount), "unusual": tx.is_unusual}
               for tx in query.all()]
    frame = pd.DataFrame(records, columns=["date", "type", "amount", "unusual"])
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"])
        frame["month"] = frame["date"].dt.to_period("M").astype(str)
    return frame


def monthly_summary(account_ids=None):
    frame = transaction_frame(account_ids)
    if frame.empty:
        return [], [], [], []
    grouped = frame.groupby(["month", "type"], as_index=False).agg(total=("amount", "sum"), count=("amount", "size"))
    pivot = grouped.pivot(index="month", columns="type", values="total").fillna(0).sort_index()
    # NumPy normalizes numeric chart input and calculates the cash-flow total consistently.
    deposits = np.asarray(pivot.get("Deposit", pd.Series(0, index=pivot.index)), dtype=float)
    withdrawals = np.asarray(pivot.get("Withdrawal", pd.Series(0, index=pivot.index)), dtype=float)
    rows = grouped.sort_values(["month", "type"], ascending=[False, True]).to_dict("records")
    return rows, pivot.index.tolist(), deposits.tolist(), withdrawals.tolist()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to access Banklytics.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = db.session.get(User, session.get("user_id"))
        if not user or user.role != "admin":
            flash("Administrator access is required.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


def current_user():
    return db.session.get(User, session.get("user_id")) if session.get("user_id") else None


def accessible_accounts():
    user = current_user()
    if not user:
        return Account.query.filter(text("1=0"))
    return Account.query if user.role == "admin" else Account.query.filter_by(customer_id=user.customer_id)


def require_account_access(account):
    user = current_user()
    if not user or (user.role != "admin" and account.customer_id != user.customer_id):
        abort(403)


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not name or not email or not password:
            flash("Name, email, and password are required.", "danger")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        elif User.query.filter_by(email=email).first() or Customer.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
        else:
            user = User(full_name=name, email=email)
            user.set_password(password)
            customer = Customer(customer_code=next_code("CUS", Customer, Customer.customer_code), full_name=name, email=email, phone="Demo user")
            db.session.add_all([user, customer]); db.session.flush()
            user.customer_id = customer.id
            db.session.add(Account(account_number=next_code("ACC", Account, Account.account_number), account_type="Savings", opening_balance=Decimal("0"), customer=customer))
            db.session.commit()
            session.permanent = True
            session["user_id"] = user.id
            flash("Registration complete. Welcome to Banklytics!", "success")
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if not user or not user.check_password(request.form.get("password", "")):
            flash("Invalid email or password.", "danger")
        else:
            session["user_id"] = user.id
            flash(f"Welcome back, {user.full_name}!", "success")
            return redirect(request.args.get("next") or url_for("dashboard"))
    return render_template("auth.html", mode="login")


@app.post("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    accounts = accessible_accounts().all()
    account_ids = [account.id for account in accounts]
    transactions_query = Transaction.query.filter(Transaction.account_id.in_(account_ids)) if account_ids else Transaction.query.filter(text("1=0"))
    deposits = transactions_query.filter_by(transaction_type="Deposit").with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar()
    withdrawals = transactions_query.filter_by(transaction_type="Withdrawal").with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar()
    recent = transactions_query.order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).limit(7).all()
    unusual = transactions_query.filter_by(is_unusual=True).order_by(Transaction.transaction_date.desc()).limit(5).all()
    _, labels, chart_deposits, chart_withdrawals = monthly_summary()
    return render_template("dashboard.html", customers=len({a.customer_id for a in accounts}), accounts=len(accounts), balance=sum((a.balance for a in accounts), Decimal("0")), deposits=deposits, withdrawals=withdrawals, recent=recent, unusual=unusual, chart_labels=labels, chart_deposits=chart_deposits, chart_withdrawals=chart_withdrawals)


@app.route("/customers", methods=["GET", "POST"])
@login_required
def customers():
    if current_user().role != "admin": abort(403)
    if request.method == "POST":
        name, email, phone = (request.form.get(k, "").strip() for k in ("full_name", "email", "phone"))
        if not all((name, email, phone)):
            flash("Name, email, and phone are required.", "danger")
        elif Customer.query.filter_by(email=email).first():
            flash("That email is already registered.", "danger")
        else:
            customer = Customer(customer_code=next_code("CUS", Customer, Customer.customer_code), full_name=name, email=email, phone=phone)
            db.session.add(customer); db.session.commit(); flash("Customer added successfully.", "success")
            return redirect(url_for("customers"))
    return render_template("customers.html", customers=Customer.query.order_by(Customer.created_at.desc()).all())


@app.route("/accounts", methods=["GET", "POST"])
@login_required
def accounts():
    if current_user().role != "admin": abort(403)
    if request.method == "POST":
        customer_id = request.form.get("customer_id")
        try: opening = Decimal(request.form.get("opening_balance", "0"))
        except InvalidOperation: opening = Decimal("-1")
        if not customer_id or not Customer.query.get(customer_id) or opening < 0:
            flash("Select a customer and enter a valid non-negative opening balance.", "danger")
        else:
            account = Account(account_number=next_code("ACC", Account, Account.account_number), account_type=request.form.get("account_type", "Savings"), opening_balance=opening, customer_id=customer_id)
            db.session.add(account); db.session.commit(); flash("Account opened successfully.", "success")
            return redirect(url_for("accounts"))
    return render_template("accounts.html", accounts=Account.query.order_by(Account.created_at.desc()).all(), customers=Customer.query.order_by(Customer.full_name).all())


@app.route("/transactions", methods=["GET", "POST"])
@login_required
def transactions():
    if request.method == "POST":
        account = db.session.get(Account, request.form.get("account_id", type=int))
        typ = request.form.get("transaction_type")
        try: amount = Decimal(request.form.get("amount", "0"))
        except InvalidOperation: amount = Decimal("0")
        try: tx_date = datetime.strptime(request.form.get("transaction_date"), "%Y-%m-%d").date()
        except (TypeError, ValueError): tx_date = None
        if account: require_account_access(account)
        if not account or typ not in ("Deposit", "Withdrawal") or amount <= 0 or not tx_date:
            flash("Choose an account, valid transaction type/date, and a positive amount.", "danger")
        elif typ == "Withdrawal" and amount > account.balance:
            flash("Withdrawal cannot exceed available balance.", "danger")
        else:
            flagged, reason = transaction_flag(typ, amount, account)
            tx = Transaction(transaction_code=next_code("TXN", Transaction, Transaction.transaction_code), account=account, transaction_type=typ, amount=amount, transaction_date=tx_date, description=request.form.get("description", "").strip(), is_unusual=flagged, unusual_reason=reason)
            db.session.add(tx); db.session.commit()
            flash("Transaction recorded" + (" and flagged for review." if flagged else "."), "warning" if flagged else "success")
            return redirect(url_for("transactions"))
    q = Transaction.query.join(Account).join(Customer)
    user = current_user()
    if user.role != "admin": q = q.filter(Account.customer_id == user.customer_id)
    tx_type, flag = request.args.get("type"), request.args.get("flag")
    search = request.args.get("search", "").strip()
    if tx_type in ("Deposit", "Withdrawal"): q = q.filter(Transaction.transaction_type == tx_type)
    if flag == "unusual": q = q.filter(Transaction.is_unusual.is_(True))
    if search:
        q = q.filter((Transaction.transaction_code.ilike(f"%{search}%")) | (Transaction.description.ilike(f"%{search}%")))
    for argument, operator in (("date_from", lambda value: Transaction.transaction_date >= value), ("date_to", lambda value: Transaction.transaction_date <= value), ("min_amount", lambda value: Transaction.amount >= value), ("max_amount", lambda value: Transaction.amount <= value)):
        value = request.args.get(argument)
        if value:
            try: q = q.filter(operator(date.fromisoformat(value) if argument.startswith("date") else Decimal(value)))
            except (ValueError, InvalidOperation): flash(f"Ignored invalid {argument.replace('_', ' ')}.", "warning")
    ordering = {"oldest": Transaction.transaction_date.asc(), "amount_high": Transaction.amount.desc(), "amount_low": Transaction.amount.asc()}.get(request.args.get("sort"), Transaction.transaction_date.desc())
    page = q.order_by(ordering, Transaction.id.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=20, error_out=False)
    return render_template("transactions.html", transactions=page.items, page=page, accounts=accessible_accounts().filter_by(status="Active").order_by(Account.account_number).all())


@app.route("/reports")
@login_required
def reports():
    accounts = accessible_accounts().order_by(Account.account_number).all()
    account_ids = [account.id for account in accounts]
    monthly, _, _, _ = monthly_summary(account_ids)
    unusual = Transaction.query.filter(Transaction.account_id.in_(account_ids), Transaction.is_unusual.is_(True)).order_by(Transaction.transaction_date.desc()).all() if account_ids else []
    return render_template("reports.html", accounts=accounts, monthly=monthly, unusual=unusual)


@app.route("/reports/monthly-chart.png")
@login_required
def monthly_chart():
    _, labels, deposits, withdrawals = monthly_summary([account.id for account in accessible_accounts().all()])
    figure, axis = plt.subplots(figsize=(8, 3.6), tight_layout=True)
    positions = np.arange(len(labels))
    axis.bar(positions - 0.2, deposits, width=0.4, label="Deposits", color="#20c997")
    axis.bar(positions + 0.2, withdrawals, width=0.4, label="Withdrawals", color="#ff6b6b")
    axis.set_xticks(positions, labels if labels else ["No data"])
    axis.set_ylabel("Amount (INR)")
    axis.set_title("Monthly cash-flow analysis")
    axis.legend(frameon=False)
    axis.spines[["top", "right"]].set_visible(False)
    buffer = StringIO()
    # savefig requires bytes; use a separate in-memory binary buffer.
    from io import BytesIO
    image = BytesIO(); figure.savefig(image, format="png", dpi=140); plt.close(figure); image.seek(0)
    return send_file(image, mimetype="image/png", max_age=0)


def build_pdf(title, customer_name, account_number, period, opening, deposits, withdrawals, closing, transactions):
    """Create an in-memory educational-simulation receipt or statement."""
    from io import BytesIO
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=18*mm)
    styles = getSampleStyleSheet(); story = []
    story += [Paragraph("<b>BANKLYTICS</b>", styles["Title"]), Paragraph("Smart Banking. Smarter Insights.", styles["Normal"]), Spacer(1, 8)]
    story += [Paragraph(f"<b>{title}</b>", styles["Heading2"]), Paragraph("EDUCATIONAL SIMULATION - NOT A REAL BANK STATEMENT", styles["Normal"]), Spacer(1, 8)]
    story += [Paragraph(f"Customer: {customer_name}<br/>Demo account: {account_number}<br/>Period: {period}<br/>Generated: {datetime.now().strftime('%d %b %Y %H:%M')}", styles["Normal"]), Spacer(1, 10)]
    summary = [["Opening balance", money(opening)], ["Total deposits", money(deposits)], ["Total withdrawals", money(withdrawals)], ["Closing balance", money(closing)]]
    table = Table(summary, colWidths=[80*mm, 75*mm]); table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#eef4fb")), ("GRID", (0,0), (-1,-1), .3, colors.HexColor("#b9cbe0")), ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"), ("ALIGN", (1,0), (1,-1), "RIGHT"), ("PADDING", (0,0), (-1,-1), 7)])); story += [table, Spacer(1, 12)]
    rows = [["Reference", "Date", "Type", "Description", "Amount"]] + [[t.transaction_code, str(t.transaction_date), t.transaction_type, t.description or "-", money(t.amount)] for t in transactions]
    details = Table(rows, repeatRows=1, colWidths=[28*mm, 24*mm, 24*mm, 62*mm, 28*mm]); details.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#102a43")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .25, colors.HexColor("#d6e0ec")), ("FONTSIZE", (0,0), (-1,-1), 7), ("VALIGN", (0,0), (-1,-1), "TOP"), ("PADDING", (0,0), (-1,-1), 5), ("ALIGN", (-1,1), (-1,-1), "RIGHT")])); story.append(details)
    doc.build(story); buffer.seek(0); return buffer


@app.route("/transactions/<int:transaction_id>/receipt.pdf")
@login_required
def transaction_receipt(transaction_id):
    tx = db.get_or_404(Transaction, transaction_id); account = tx.account
    require_account_access(account)
    before = account.opening_balance
    for item in sorted(account.transactions, key=lambda t: (t.transaction_date, t.id)):
        if item.id == tx.id: break
        before += item.amount if item.transaction_type == "Deposit" else -item.amount
    after = before + (tx.amount if tx.transaction_type == "Deposit" else -tx.amount)
    pdf = build_pdf("Transaction Receipt", account.customer.full_name, account.account_number, str(tx.transaction_date), before, tx.amount if tx.transaction_type == "Deposit" else 0, tx.amount if tx.transaction_type == "Withdrawal" else 0, after, [tx])
    return send_file(pdf, mimetype="application/pdf", as_attachment=True, download_name=f"{tx.transaction_code}-receipt.pdf")


@app.route("/accounts/<int:account_id>/statement.pdf")
@login_required
def account_statement(account_id):
    account = db.get_or_404(Account, account_id); month = request.args.get("month")
    require_account_access(account)
    transactions = sorted(account.transactions, key=lambda t: (t.transaction_date, t.id))
    if month:
        transactions = [t for t in transactions if t.transaction_date.strftime("%Y-%m") == month]
    opening = account.opening_balance
    if month:
        opening += sum((t.amount if t.transaction_type == "Deposit" else -t.amount) for t in account.transactions if t.transaction_date.strftime("%Y-%m") < month)
    deposits = sum((t.amount for t in transactions if t.transaction_type == "Deposit"), Decimal("0")); withdrawals = sum((t.amount for t in transactions if t.transaction_type == "Withdrawal"), Decimal("0"))
    pdf = build_pdf("Monthly Account Statement", account.customer.full_name, account.account_number, month or "All activity", opening, deposits, withdrawals, opening + deposits - withdrawals, transactions)
    return send_file(pdf, mimetype="application/pdf", as_attachment=True, download_name=f"{account.account_number}-statement.pdf")


@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    deposits = db.session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter_by(transaction_type="Deposit").scalar()
    withdrawals = db.session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter_by(transaction_type="Withdrawal").scalar()
    return render_template("admin.html", customers=Customer.query.count(), accounts=Account.query.count(), transactions=Transaction.query.count(), deposits=deposits, withdrawals=withdrawals, unusual=Transaction.query.filter_by(is_unusual=True).order_by(Transaction.transaction_date.desc()).all())


@app.route("/export/transactions.csv")
@login_required
def export_transactions():
    output = StringIO(); writer = csv.writer(output)
    writer.writerow(["Transaction ID", "Date", "Account", "Customer", "Type", "Amount", "Description", "Unusual", "Reason"])
    query = Transaction.query.join(Account)
    if current_user().role != "admin": query = query.filter(Account.customer_id == current_user().customer_id)
    for tx in query.order_by(Transaction.transaction_date.desc()).all():
        writer.writerow([tx.transaction_code, tx.transaction_date, tx.account.account_number, tx.account.customer.full_name, tx.transaction_type, tx.amount, tx.description or "", "Yes" if tx.is_unusual else "No", tx.unusual_reason or ""])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=banklytics_transactions.csv"})


@app.get("/health")
@csrf.exempt
def health():
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return {"status": "unhealthy"}, 503
    return {"status": "ok"}, 200


def seed_data():
    if Customer.query.first(): return
    people = [("Aarav Sharma", "aarav@example.test", "9876543210"), ("Diya Patel", "diya@example.test", "9876543211"), ("Kabir Singh", "kabir@example.test", "9876543212")]
    for i, (name, email, phone) in enumerate(people, 1):
        db.session.add(Customer(customer_code=f"CUS-{i:05d}", full_name=name, email=email, phone=phone))
    db.session.flush()
    for i, customer in enumerate(Customer.query.all(), 1):
        db.session.add(Account(account_number=f"ACC-{i:05d}", account_type="Savings" if i < 3 else "Current", opening_balance=Decimal(str(i * 10000)), customer=customer))
    db.session.flush()
    sample = [(1,"Deposit",25000,"2026-08-05","Salary credit"),(1,"Withdrawal",4500,"2026-08-10","ATM withdrawal"),(2,"Deposit",18000,"2026-09-02","Freelance payment"),(2,"Withdrawal",3200,"2026-09-11","Utility bills"),(3,"Deposit",75000,"2026-10-15","Business receipt")]
    for i, (aid, typ, amount, dt, desc) in enumerate(sample, 1):
        value = Decimal(str(amount)); flagged = value >= app.config["UNUSUAL_TRANSACTION_LIMIT"]
        db.session.add(Transaction(transaction_code=f"TXN-{i:05d}", account_id=aid, transaction_type=typ, amount=value, transaction_date=datetime.strptime(dt, "%Y-%m-%d").date(), description=desc, is_unusual=flagged, unusual_reason=f"High-value transaction (≥ {money(app.config['UNUSUAL_TRANSACTION_LIMIT'])})" if flagged else None))
    db.session.commit()


with app.app_context():
    db.create_all()
    # Lightweight additive migration for existing SQLite/MySQL demo databases.
    user_columns = {column["name"] for column in inspect(db.engine).get_columns("users")}
    if "role" not in user_columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'customer'"))
    if "customer_id" not in user_columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN customer_id INTEGER NULL"))
        db.session.commit()
    if app.config["AUTO_SEED_DEMO_DATA"]:
        seed_data()

if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"])
