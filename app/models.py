from datetime import datetime, timezone
from decimal import Decimal
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Customer(UserMixin, db.Model):
    __tablename__ = 'customers'
    __table_args__ = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'}
    customer_id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    email = db.Column(db.String(254), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    account = db.relationship('Account', back_populates='customer', uselist=False)

    @property
    def id(self):
        return self.customer_id

    def get_id(self):
        return str(self.customer_id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Account(db.Model):
    __tablename__ = 'accounts'
    __table_args__ = (db.CheckConstraint('balance >= 0', name='ck_account_nonnegative'),
                      {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'})
    account_id = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(32), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.customer_id'), unique=True, nullable=False)
    account_type = db.Column(db.String(30), nullable=False, default='Demo Savings')
    balance = db.Column(db.Numeric(15, 2), nullable=False, default=Decimal('0.00'))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    customer = db.relationship('Customer', back_populates='account')
    transactions = db.relationship('Transaction', back_populates='account', lazy='dynamic')


class Transaction(db.Model):
    __tablename__ = 'transactions'
    __table_args__ = (
        db.CheckConstraint("transaction_type IN ('deposit', 'withdrawal')", name='ck_transaction_type'),
        db.CheckConstraint('amount > 0', name='ck_transaction_positive'),
        db.CheckConstraint('balance_after >= 0', name='ck_transaction_balance'),
        db.Index('ix_transactions_account_date', 'account_id', 'transaction_date', 'transaction_id'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )
    transaction_id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.account_id'), nullable=False)
    transaction_date = db.Column(db.DateTime, nullable=False, default=utcnow)
    transaction_type = db.Column(db.String(12), nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    description = db.Column(db.String(255), nullable=False, default='')
    balance_after = db.Column(db.Numeric(15, 2), nullable=False)
    submission_key = db.Column(db.String(36), unique=True, nullable=False)
    account = db.relationship('Account', back_populates='transactions')
    flags = db.relationship('TransactionFlag', back_populates='transaction')


class TransactionFlag(db.Model):
    __tablename__ = 'transaction_flags'
    __table_args__ = (
        db.UniqueConstraint('transaction_id', 'rule_name', name='uq_transaction_rule'),
        db.CheckConstraint("review_status IN ('pending', 'reviewed')", name='ck_flag_status'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )
    flag_id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.transaction_id'), nullable=False, index=True)
    rule_name = db.Column(db.String(80), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    review_status = db.Column(db.String(12), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    transaction = db.relationship('Transaction', back_populates='flags')
