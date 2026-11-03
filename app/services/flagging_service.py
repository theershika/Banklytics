"""Explainable educational review rules; never a fraud classification."""
from datetime import timedelta
from decimal import Decimal
from flask import current_app
from ..extensions import db
from ..models import Transaction, TransactionFlag


def flag_transaction(transaction):
    cfg = current_app.config
    prior = db.session.scalars(db.select(Transaction).where(
        Transaction.account_id == transaction.account_id,
        Transaction.transaction_id != transaction.transaction_id,
    ).with_for_update()).all()
    rules = []
    threshold = Decimal(str(cfg['FLAG_LARGE_THRESHOLD']))
    if transaction.amount > threshold:
        rules.append(('large_amount', f'Amount exceeds the configured demo threshold of INR {threshold:,.2f}.'))
    if transaction.transaction_type == 'withdrawal':
        start = transaction.transaction_date - timedelta(minutes=cfg['FLAG_WINDOW_MINUTES'])
        count = 1 + sum(t.transaction_type == 'withdrawal' and start <= t.transaction_date <= transaction.transaction_date for t in prior)
        if count >= cfg['FLAG_WITHDRAWAL_COUNT']:
            rules.append(('frequent_withdrawals', f'{count} withdrawals within {cfg["FLAG_WINDOW_MINUTES"]} minutes.'))
    if len(prior) >= cfg['FLAG_HISTORY_MIN']:
        average = sum((t.amount for t in prior), Decimal(0)) / len(prior)
        if transaction.amount > average * cfg['FLAG_HISTORY_MULTIPLIER']:
            rules.append(('above_historical_average', f'Amount exceeds {cfg["FLAG_HISTORY_MULTIPLIER"]} times the average of {len(prior)} earlier transactions.'))
    for name, reason in rules:
        db.session.add(TransactionFlag(transaction=transaction, rule_name=name, reason=reason))
    return rules
