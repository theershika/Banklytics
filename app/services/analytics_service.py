"""Account-scoped analysis with exact integer paise and real Pandas groupings.

Only display coordinates for charts are converted to floats. All financial
statistics are calculated in integer paise or Decimal, never binary floats.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import threading

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.extensions import db
from app.models import Account, Transaction

CENT = Decimal('0.01')
_PLOT_LOCK = threading.Lock()


def _cents(value) -> int:
    return int(Decimal(str(value)) * 100)


def _money(value: int) -> Decimal:
    return (Decimal(int(value)) / 100).quantize(CENT)


def account_transactions(account_id: int) -> list[Transaction]:
    """Return only this account's ledger, with deterministic timestamp ties."""
    return list(db.session.scalars(select(Transaction).where(
        Transaction.account_id == account_id
    ).order_by(Transaction.transaction_date, Transaction.transaction_id)))


def _frame(transactions: list[Transaction]) -> pd.DataFrame:
    rows = [{
        'account_id': tx.account_id,
        'date': tx.transaction_date,
        'type': tx.transaction_type,
        'cents': _cents(tx.amount),
        'balance_cents': _cents(tx.balance_after),
    } for tx in transactions]
    df = pd.DataFrame(rows, columns=['account_id', 'date', 'type', 'cents', 'balance_cents'])
    # object dtype retains Python's arbitrary-precision integers in sums.
    df['cents'] = pd.Series([r['cents'] for r in rows], dtype=object)
    df['balance_cents'] = pd.Series([r['balance_cents'] for r in rows], dtype=object)
    df['date'] = pd.to_datetime(df['date'])
    df['month'] = df['date'].dt.to_period('M')
    return df


def opening_ledger_balance(account: Account, transactions: list[Transaction]) -> Decimal:
    """Retain a legacy opening balance without inventing a transaction."""
    if not transactions:
        return Decimal(account.balance).quantize(CENT)
    first = transactions[0]
    signed = first.amount if first.transaction_type == 'deposit' else -first.amount
    return (first.balance_after - signed).quantize(CENT)


def get_analytics(account_id: int) -> dict:
    account = db.session.get(Account, account_id)
    if account is None:
        raise ValueError('Account does not exist.')
    transactions = account_transactions(account_id)
    df = _frame(transactions)
    grouped = df.groupby('type', observed=True)['cents'].agg(lambda x: sum(x, 0))
    deposits = int(grouped.get('deposit', 0))
    withdrawals = int(grouped.get('withdrawal', 0))
    kinds = df['type'].to_numpy()
    deposit_count = int(np.count_nonzero(kinds == 'deposit'))
    withdrawal_count = int(np.count_nonzero(kinds == 'withdrawal'))
    count = len(df)
    amounts = np.array(list(df['cents']), dtype=object)
    total_amount = int(np.sum(amounts)) if count else 0
    average = (Decimal(total_amount) / 100 / count).quantize(CENT, rounding=ROUND_HALF_UP) if count else Decimal('0.00')
    highest_deposit = max(df.loc[df['type'] == 'deposit', 'cents'], default=0)
    highest_withdrawal = max(df.loc[df['type'] == 'withdrawal', 'cents'], default=0)
    monthly = []
    balance = opening_ledger_balance(account, transactions)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if count:
        first_month = df['month'].min()
        last_month = max(df['month'].max(), pd.Period(now, freq='M'))
        periods = pd.period_range(first_month, last_month, freq='M')
        monthly_groups = df.groupby(['month', 'type'], observed=True)['cents'].agg(lambda x: sum(x, 0))
        frequencies = df.groupby('month', observed=True).size()
        balance_groups = df.groupby('month', observed=True)['balance_cents'].last()
    else:
        periods = pd.period_range(pd.Period(now, freq='M'), periods=1, freq='M')
        monthly_groups = pd.Series(dtype=object)
        frequencies = pd.Series(dtype=int)
        balance_groups = pd.Series(dtype=object)
    for period in periods:
        dep = int(monthly_groups.get((period, 'deposit'), 0))
        wit = int(monthly_groups.get((period, 'withdrawal'), 0))
        if period in balance_groups:
            balance = _money(balance_groups[period])
        monthly.append({
            'month': str(period), 'label': period.strftime('%b %Y'),
            'deposits': _money(dep), 'withdrawals': _money(wit),
            'net': _money(dep - wit), 'volume': _money(dep + wit),
            'count': int(frequencies.get(period, 0)), 'closing_balance': balance,
        })
    account_group = df.groupby('account_id', observed=True)['cents'].agg(lambda x: sum(x, 0))
    return {
        'total_deposits': _money(deposits), 'total_withdrawals': _money(withdrawals),
        'net_change': _money(deposits - withdrawals), 'average_amount': average,
        'highest_deposit': _money(highest_deposit), 'highest_withdrawal': _money(highest_withdrawal),
        'transaction_count': count, 'deposit_count': deposit_count,
        'withdrawal_count': withdrawal_count, 'monthly': monthly,
        'account_volume': {str(key): _money(value) for key, value in account_group.items()},
        'chart_data': {
            'labels': [r['label'] for r in monthly],
            'deposits': [float(r['deposits']) for r in monthly],
            'withdrawals': [float(r['withdrawals']) for r in monthly],
            'net': [float(r['net']) for r in monthly],
            'volume': [float(r['volume']) for r in monthly],
            'balances': [float(r['closing_balance']) for r in monthly],
            'frequency': [r['count'] for r in monthly],
            'deposit_count': deposit_count, 'withdrawal_count': withdrawal_count,
            'total_deposits': float(_money(deposits)),
            'total_withdrawals': float(_money(withdrawals)),
        },
    }


def chart_png(account_id: int) -> BytesIO:
    """Render a professional headless Matplotlib analysis image, safely per request."""
    data = get_analytics(account_id)
    chart = data['chart_data']
    # Matplotlib's global state and font manager are not thread safe.
    with _PLOT_LOCK:
        from matplotlib.figure import Figure
        figure = Figure(figsize=(12, 7), dpi=160, facecolor='#f3f6fb')
        axes = figure.subplots(2, 1)
        figure.suptitle('AccountPulse | Financial activity', fontsize=18, color='#13233d', fontweight='bold')
        x = np.arange(len(chart['labels']))
        axes[0].bar(x - 0.18, chart['deposits'], width=0.36, color='#087f8c', label='Deposits')
        axes[0].bar(x + 0.18, chart['withdrawals'], width=0.36, color='#5278bf', label='Withdrawals')
        axes[0].set_ylabel('Amount (INR)')
        axes[0].legend(frameon=False)
        axes[0].set_title('Monthly deposits and withdrawals', loc='left', fontsize=11)
        axes[1].plot(x, chart['balances'], marker='o', color='#087f8c', linewidth=2)
        axes[1].set_ylabel('Closing balance (INR)')
        axes[1].set_title('Account balance trend', loc='left', fontsize=11)
        # Keep long histories readable while preserving every data point.
        stride = max(1, len(x) // 12)
        positions = list(range(0, len(x), stride))
        if len(x) and len(x) - 1 not in positions:
            positions.append(len(x) - 1)
        for ax in axes:
            ax.set_xticks(positions, [chart['labels'][i] for i in positions], rotation=30, ha='right', fontsize=8)
            ax.set_facecolor('white')
            ax.grid(axis='y', alpha=0.15)
            ax.set_axisbelow(True)
            ax.spines[['top', 'right']].set_visible(False)
        if not data['transaction_count']:
            axes[0].text(0.5, 0.5, 'No recorded transactions', transform=axes[0].transAxes, ha='center', color='#68768b')
        figure.text(0.5, 0.015, 'Educational simulation • Synthetic financial data • UTC', ha='center', fontsize=9, color='#68768b')
        figure.tight_layout(rect=(0, 0.04, 1, 0.94))
        output = BytesIO()
        figure.savefig(output, format='png', facecolor=figure.get_facecolor())
        output.seek(0)
        figure.clear()
    return output
