"""Profile display and safe editable account-holder details."""
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import Customer
from app.forms import ProfileForm

bp = Blueprint("profile", __name__)


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def index():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        existing = db.session.execute(db.select(Customer).where(Customer.email == email, Customer.customer_id != current_user.customer_id)).scalar_one_or_none()
        if existing:
            flash("That email address is already registered.", "danger")
        else:
            current_user.full_name = form.full_name.data.strip()
            current_user.email = email
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("That email address is already registered.", "danger")
            else:
                flash("Profile updated.", "success")
                return redirect(url_for("profile.index"))
    return render_template("profile.html", form=form, account=current_user.account)
