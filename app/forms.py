"""Validated, CSRF-protected HTML forms."""
import re
from decimal import Decimal, InvalidOperation
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, TextAreaField, HiddenField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Optional


def strip_text(value):
    return value.strip() if isinstance(value, str) else value


def email_address(form, field):
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", field.data or ""):
        raise ValidationError("Enter a valid email address.")


def username_format(form, field):
    if not re.fullmatch(r"[A-Za-z0-9_]{3,40}", field.data or ""):
        raise ValidationError("Use 3–40 letters, numbers, or underscores.")


def strong_password(form, field):
    value = field.data or ""
    if len(value) < 10 or not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
        raise ValidationError("Use at least 10 characters, including a letter and a number.")


def valid_money(form, field):
    value = (field.data or "").strip()
    if not re.fullmatch(r"[0-9]{1,13}(?:\.[0-9]{1,2})?", value):
        raise ValidationError("Enter an amount with at most two decimal places, such as 1500.50.")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise ValidationError("Enter a valid amount.") from None
    if not amount.is_finite() or amount <= 0:
        raise ValidationError("Amount must be greater than zero.")
    if amount > Decimal("9999999999999.99"):
        raise ValidationError("Amount exceeds the supported maximum.")


class LoginForm(FlaskForm):
    username = StringField("Username", filters=[strip_text], validators=[DataRequired(), Length(max=40)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")


class RegisterForm(FlaskForm):
    full_name = StringField("Full name", filters=[strip_text], validators=[DataRequired(), Length(min=2, max=100)])
    username = StringField("Username", filters=[strip_text], validators=[DataRequired(), username_format])
    email = StringField("Email", filters=[strip_text], validators=[DataRequired(), Length(max=254), email_address])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128), strong_password])
    confirm_password = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password", message="Passwords must match.")])
    submit = SubmitField("Create demo account")


class BankingForm(FlaskForm):
    amount = StringField("Amount (₹)", filters=[strip_text], validators=[DataRequired(), Length(max=18), valid_money])
    description = TextAreaField("Description (optional)", validators=[Optional(), Length(max=255)])
    submission_key = HiddenField(validators=[DataRequired(), Length(min=36, max=36)])
    submit = SubmitField("Confirm transaction")


class ProfileForm(FlaskForm):
    full_name = StringField("Full name", filters=[strip_text], validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField("Email", filters=[strip_text], validators=[DataRequired(), Length(max=254), email_address])
    submit = SubmitField("Save changes")
