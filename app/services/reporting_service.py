"""Monthly statements and portable exports of the authenticated account's ledger."""
from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from io import BytesIO, StringIO
from xml.sax.saxutils import escape

from app.extensions import db
from app.models import Account
from app.services.analytics_service import account_transactions, opening_ledger_balance


def monthly_report(account_id: int, year: int, month: int) -> dict:
    if not 1900 <= year <= 9998 or not 1 <= month <= 12:
        raise ValueError('Choose a valid month and year (1900–9998).')
    account = db.session.get(Account, account_id)
    if account is None:
        raise ValueError('Account does not exist.')
    start = datetime(year, month, 1)
    end = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1)
    ledger = account_transactions(account_id)
    before = [tx for tx in ledger if tx.transaction_date < start]
    transactions = [tx for tx in ledger if start <= tx.transaction_date < end]
    opening = before[-1].balance_after if before else opening_ledger_balance(account, ledger)
    deposits = sum((tx.amount for tx in transactions if tx.transaction_type == 'deposit'), Decimal('0.00'))
    withdrawals = sum((tx.amount for tx in transactions if tx.transaction_type == 'withdrawal'), Decimal('0.00'))
    closing = opening + deposits - withdrawals
    return {
        'year': year, 'month': month, 'label': start.strftime('%B %Y'),
        'opening_balance': opening, 'total_deposits': deposits,
        'total_withdrawals': withdrawals, 'closing_balance': closing,
        'transaction_count': len(transactions), 'transactions': transactions,
        'account_number': account.account_number,
    }


def _safe_cell(value):
    """Prevent spreadsheet applications interpreting user-controlled formulas."""
    if value is None:
        return ''
    text = str(value)
    if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'" + text
    return text


def transaction_csv(transactions, account_number=None) -> str:
    output = StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['Transaction ID', 'Date (UTC)', 'Account number', 'Type', 'Amount (INR)', 'Description', 'Balance after (INR)'])
    for tx in transactions:
        number = account_number if account_number is not None else tx.account.account_number
        writer.writerow([
            tx.transaction_id, tx.transaction_date.isoformat(sep=' ', timespec='seconds'),
            _safe_cell(number), tx.transaction_type, format(tx.amount, '.2f'),
            _safe_cell(tx.description), format(tx.balance_after, '.2f'),
        ])
    return output.getvalue()


def report_csv(report: dict) -> str:
    output = StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['AccountPulse monthly statement', report['label']])
    writer.writerow(['Educational simulation — not a real bank'])
    writer.writerow(['Account number', _safe_cell(report['account_number'])])
    for title, key in [('Opening balance (INR)', 'opening_balance'), ('Deposits (INR)', 'total_deposits'),
                       ('Withdrawals (INR)', 'total_withdrawals'), ('Closing balance (INR)', 'closing_balance')]:
        writer.writerow([title, format(report[key], '.2f')])
    writer.writerow(['Transaction count', report['transaction_count']])
    writer.writerow([])
    output.write(transaction_csv(report['transactions'], report['account_number']))
    return output.getvalue()


def report_pdf(report: dict, customer, account) -> BytesIO:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

    output = BytesIO()
    navy = colors.HexColor('#13233d')
    teal = colors.HexColor('#087f8c')
    muted = colors.HexColor('#62738b')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='PulseTitle', fontName='Helvetica-Bold', fontSize=26, leading=30, textColor=navy, spaceAfter=6))
    styles.add(ParagraphStyle(name='PulseSubtitle', fontSize=13, leading=18, textColor=teal, spaceAfter=14))
    styles.add(ParagraphStyle(name='PulseSmall', fontSize=8, leading=12, textColor=muted))
    styles.add(ParagraphStyle(name='PulseCell', fontSize=8, leading=11, textColor=navy))
    styles.add(ParagraphStyle(name='PulseMoney', fontSize=8, leading=11, alignment=TA_RIGHT, textColor=navy))
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=23 * mm,
                            title=f'AccountPulse statement - {report["label"]}', author='AccountPulse')
    name = escape(customer.full_name)
    number = escape(str(account.account_number))
    story = [Paragraph('AccountPulse', styles['PulseTitle']),
             Paragraph(f'Monthly statement · {escape(report["label"])}', styles['PulseSubtitle']),
             Paragraph(f'{name}<br/>Demo account {number}<br/>All transaction times are UTC.', styles['Normal']), Spacer(1, 8 * mm)]
    summary = [
        ['Opening balance', 'Deposits', 'Withdrawals', 'Closing balance'],
        [f'INR {report[key]:,.2f}' for key in ('opening_balance', 'total_deposits', 'total_withdrawals', 'closing_balance')],
    ]
    table = Table(summary, colWidths=[43 * mm] * 4)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#eef5f7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), muted), ('TEXTCOLOR', (0, 1), (-1, 1), navy),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 11), ('BOTTOMPADDING', (0, 0), (-1, -1), 11),
    ]))
    story += [table, Spacer(1, 8 * mm), Paragraph(f'Transaction details ({report["transaction_count"]})', styles['Heading2'])]
    rows = [['ID / Date (UTC)', 'Type / Description', 'Amount (INR)', 'Balance (INR)']]
    for tx in report['transactions']:
        rows.append([
            Paragraph(f'#{tx.transaction_id}<br/>{tx.transaction_date:%d %b %Y %H:%M}', styles['PulseCell']),
            Paragraph(f'<b>{tx.transaction_type.title()}</b><br/>{escape(tx.description or "No description")}', styles['PulseCell']),
            Paragraph(f'{tx.amount:,.2f}', styles['PulseMoney']),
            Paragraph(f'{tx.balance_after:,.2f}', styles['PulseMoney']),
        ])
    if not report['transactions']:
        story.append(Paragraph('No transactions were recorded in this month. The opening balance carries forward unchanged.', styles['Normal']))
    else:
        ledger_table = Table(rows, repeatRows=1, colWidths=[40 * mm, 66 * mm, 33 * mm, 33 * mm])
        ledger_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), navy), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f7fa')]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
        ]))
        story.append(ledger_table)
    story += [Spacer(1, 8 * mm), Paragraph('Educational simulation only. All funds are simulated and financial data is synthetic. This document is not an official bank statement.', styles['PulseSmall'])]

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#dde5ed'))
        canvas.line(18 * mm, 18 * mm, 192 * mm, 18 * mm)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(muted)
        canvas.drawString(18 * mm, 13 * mm, 'AccountPulse | Educational simulation | Synthetic financial data')
        canvas.drawRightString(192 * mm, 13 * mm, f'Page {document.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    output.seek(0)
    return output
