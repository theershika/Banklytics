"""Searchable, paginated ledger and CSV export."""
from datetime import datetime
from flask import Blueprint, render_template, request, flash, Response
from flask_login import login_required, current_user
from sqlalchemy import or_, cast, String
from app.extensions import db
from app.models import Transaction
from app.services.reporting_service import transaction_csv

bp = Blueprint("transactions", __name__)


def filtered_query():
    query = db.select(Transaction).where(Transaction.account_id == current_user.account.account_id)
    filters = {name: request.args.get(name, "").strip() for name in ("q", "type", "start_date", "end_date", "sort")}
    filters["q"] = filters["q"][:200]
    if filters["q"]:
        term = filters["q"][:200]
        query = query.where(or_(Transaction.description.icontains(term, autoescape=True),
                               cast(Transaction.transaction_id, String).icontains(term, autoescape=True)))
    if filters["type"] in ("deposit", "withdrawal"):
        query = query.where(Transaction.transaction_type == filters["type"])
    for name in ("start_date", "end_date"):
        if filters[name]:
            try:
                date = datetime.strptime(filters[name], "%Y-%m-%d")
                if name == "start_date":
                    query = query.where(Transaction.transaction_date >= date)
                else:
                    query = query.where(Transaction.transaction_date <= date.replace(hour=23, minute=59, second=59, microsecond=999999))
            except ValueError:
                flash("Use a valid YYYY-MM-DD date for transaction filters.", "warning")
                filters[name] = ""
    if filters["sort"] == "oldest":
        query = query.order_by(Transaction.transaction_date.asc(), Transaction.transaction_id.asc())
    else:
        filters["sort"] = "newest"
        query = query.order_by(Transaction.transaction_date.desc(), Transaction.transaction_id.desc())
    return query, filters


@bp.get("/transactions")
@login_required
def index():
    query, filters = filtered_query()
    pagination = db.paginate(query, page=request.args.get("page", 1, type=int), per_page=15, error_out=False)
    return render_template("transactions.html", transactions=pagination.items, pagination=pagination, filters=filters)


@bp.get("/transactions/export.csv")
@login_required
def export_csv():
    query, _ = filtered_query()
    rows = db.session.execute(query).scalars().all()
    return Response(transaction_csv(rows), content_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="accountpulse-transactions.csv"'})
