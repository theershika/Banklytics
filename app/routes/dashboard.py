"""Public homepage and live account overview."""
from flask import Blueprint, render_template
from flask_login import current_user, login_required
from app.extensions import db
from app.models import Transaction
from app.services.analytics_service import get_analytics

main_bp = Blueprint("main", __name__)
bp = Blueprint("dashboard", __name__)


@main_bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/dashboard", endpoint="index")
@login_required
def dashboard_index():
    account = current_user.account
    stats = get_analytics(account.account_id)
    recent = db.session.execute(db.select(Transaction).where(Transaction.account_id == account.account_id).order_by(
        Transaction.transaction_date.desc(), Transaction.transaction_id.desc()).limit(5)).scalars().all()
    return render_template("dashboard.html", account=account, stats=stats, recent_transactions=recent, chart_data=stats["chart_data"])

