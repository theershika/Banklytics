import re
from decimal import Decimal, InvalidOperation
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..models import Account, Transaction
from .flagging_service import flag_transaction

MAX_MONEY = Decimal('9999999999999.99')


def parse_amount(raw):
    text = str(raw).strip()
    if not re.fullmatch(r'[0-9]{1,13}(\.[0-9]{1,2})?', text):
        raise ValueError('Enter a positive amount with at most two decimal places (for example 250.50).')
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ValueError('Enter a valid amount.') from None
    if amount <= 0 or amount > MAX_MONEY:
        raise ValueError('Amount must be greater than zero and within the supported limit.')
    return amount.quantize(Decimal('0.01'))


def post_transaction(account_id, kind, amount, description, submission_key):
    """Lock the account, then commit balance, ledger and flags as one unit.

    MySQL InnoDB SELECT FOR UPDATE serializes independent workers. An account
    lock is acquired before checking the globally unique idempotency key.
    """
    amount = parse_amount(amount)
    if kind not in ('deposit', 'withdrawal'):
        raise ValueError('Invalid transaction type.')
    description = (description or '').strip()
    if len(description) > 255:
        raise ValueError('Description must contain at most 255 characters.')
    try:
        UUID(str(submission_key))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid submission token. Reload the form.') from None
    try:
        account = db.session.execute(db.select(Account).where(Account.account_id == account_id).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
        if not account:
            raise ValueError('Account not found.')
        # Locking reads see the latest committed row even under REPEATABLE READ.
        existing = db.session.execute(db.select(Transaction).where(Transaction.submission_key == str(submission_key)).with_for_update()).scalar_one_or_none()
        if existing:
            if (existing.account_id, existing.transaction_type, existing.amount, existing.description) != (account_id, kind, amount, description):
                raise ValueError('This submission token was already used. Reload the form.')
            db.session.commit()
            return existing, False
        balance = account.balance + (amount if kind == 'deposit' else -amount)
        if balance < 0:
            raise ValueError('Insufficient simulated balance for this withdrawal.')
        if balance > MAX_MONEY:
            raise ValueError('This deposit would exceed the supported account balance limit.')
        account.balance = balance
        tx = Transaction(account_id=account_id, transaction_type=kind, amount=amount,
                         description=description, balance_after=balance, submission_key=str(submission_key))
        db.session.add(tx)
        db.session.flush()
        flag_transaction(tx)
        db.session.commit()
        return tx, True
    except (Exception,):
        db.session.rollback()
        raise
