"""Account-scoped simulated transactions and educational reviews."""
from uuid import uuid4, UUID
from flask import Blueprint, render_template, redirect, url_for, flash, session, request, abort
from flask_login import current_user, login_required
from app.extensions import db
from app.forms import BankingForm
from app.models import TransactionFlag, Transaction
from app.services.banking_service import post_transaction

bp = Blueprint("banking", __name__)


def transaction_page(kind):
    form = BankingForm()
    token_key = "transaction_tokens"
    tokens = session.get(token_key, [])
    if request.method == "GET":
        key = str(uuid4())
        tokens = (tokens + [key])[-30:]
        session[token_key] = tokens
        form.submission_key.data = key
    if form.validate_on_submit():
        key = form.submission_key.data
        try:
            UUID(key)
        except (ValueError, TypeError):
            abort(400)
        if key not in tokens:
            flash("This transaction form has expired. Please start a new transaction.", "warning")
            return redirect(url_for("banking." + ("deposit" if kind == "deposit" else "withdraw")))
        try:
            tx, created = post_transaction(current_user.account.account_id, kind, form.amount.data,
                                           (form.description.data or "").strip(), key)
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")
        else:
            flash("Transaction recorded successfully." if created else "This transaction was already recorded; no additional money was moved.", "success" if created else "info")
            return redirect(url_for("transactions.index"))
    return render_template("deposit.html" if kind == "deposit" else "withdraw.html", form=form, account=current_user.account)


@bp.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    return transaction_page("deposit")


@bp.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    return transaction_page("withdrawal")


@bp.get("/reviews")
@login_required
def flags():
    query = db.select(TransactionFlag).join(Transaction).where(Transaction.account_id == current_user.account.account_id)
    status = request.args.get("status", "all")
    if status in ("pending", "reviewed"):
        query = query.where(TransactionFlag.review_status == status)
    flags = db.session.execute(query.order_by(TransactionFlag.created_at.desc(), TransactionFlag.flag_id.desc())).scalars().all()
    return render_template("flags.html", flags=flags, status=status)


@bp.post("/reviews/<int:flag_id>")
@login_required
def review_flag(flag_id):
    flag = db.session.execute(db.select(TransactionFlag).join(Transaction).where(
        TransactionFlag.flag_id == flag_id, Transaction.account_id == current_user.account.account_id)).scalar_one_or_none()
    if flag is None:
        abort(404)
    flag.review_status = "reviewed"
    db.session.commit()
    flash("Review marked complete. Flags are educational prompts, not fraud findings.", "success")
    return redirect(url_for("banking.flags"))
