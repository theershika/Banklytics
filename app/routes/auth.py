"""Registration and session authentication."""
from uuid import uuid4
from flask import Blueprint, render_template, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db, limiter
from app.models import Customer, Account
from app.forms import LoginForm, RegisterForm

bp = Blueprint("auth", __name__)
_DUMMY_PASSWORD_HASH = generate_password_hash("unavailable-account-password")


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        email = form.email.data.strip().lower()
        exists = db.session.execute(db.select(Customer).where(or_(Customer.username == username, Customer.email == email))).scalars().first()
        if exists:
            flash("That username or email is already registered.", "danger")
        else:
            customer = Customer(full_name=form.full_name.data.strip(), username=username, email=email,
                                password_hash=generate_password_hash(form.password.data))
            try:
                db.session.add(customer)
                db.session.flush()
                db.session.add(Account(account_number="AP" + uuid4().hex[:16].upper(), customer_id=customer.customer_id, balance=0))
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("That username or email is already registered.", "danger")
            else:
                flash("Your demo account is ready. Sign in to get started.", "success")
                return redirect(url_for("auth.login"))
    return render_template("register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    form = LoginForm()
    if form.validate_on_submit():
        customer = db.session.execute(db.select(Customer).where(Customer.username == form.username.data.strip().lower())).scalar_one_or_none()
        # A valid hash is checked even for unknown users to reduce timing differences.
        candidate_hash = customer.password_hash if customer else _DUMMY_PASSWORD_HASH
        valid = check_password_hash(candidate_hash, form.password.data)
        if customer and valid:
            session.clear()
            login_user(customer, remember=form.remember.data)
            flash("Welcome back to AccountPulse.", "success")
            return redirect(url_for("dashboard.index"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("main.index"))
