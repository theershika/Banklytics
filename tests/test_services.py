"""Exact financial aggregates, carry-forward reports, detection rules and exports."""
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
import pytest
from app.extensions import db
from app.models import Transaction, TransactionFlag
from app.services.banking_service import post_transaction, parse_amount
from app.services.analytics_service import get_analytics, chart_png
from app.services.reporting_service import monthly_report, report_csv, report_pdf, transaction_csv


def add_transaction(account_id, kind, amount, date=None, description="Service test"):
    tx, created = post_transaction(account_id, kind, Decimal(amount), description, str(uuid4()))
    assert created
    if date:
        tx.transaction_date = date
        db.session.commit()
    return tx


def test_empty_analytics_and_monthly_report(app, customer):
    with app.app_context():
        data = get_analytics(customer["account_id"])
        assert data["transaction_count"] == 0
        assert data["total_deposits"] == Decimal("0.00")
        assert data["average_amount"] == Decimal("0.00")
        report = monthly_report(customer["account_id"], 2025, 1)
        assert report["opening_balance"] == report["closing_balance"] == Decimal("0.00")
        assert report["transaction_count"] == 0


def test_monthly_analytics_correct_and_exact(app, customer):
    with app.app_context():
        aid = customer["account_id"]
        add_transaction(aid, "deposit", "1000.10", datetime(2025, 1, 1, 0, 0))
        add_transaction(aid, "withdrawal", "200.05", datetime(2025, 1, 31, 23, 59, 59))
        add_transaction(aid, "deposit", "300.05", datetime(2025, 2, 1, 0, 0))
        data = get_analytics(aid)
        assert data["total_deposits"] == Decimal("1300.15")
        assert data["total_withdrawals"] == Decimal("200.05")
        assert data["net_change"] == Decimal("1100.10")
        assert data["average_amount"] == Decimal("500.07")
        assert data["highest_deposit"] == Decimal("1000.10")
        assert data["highest_withdrawal"] == Decimal("200.05")
        assert data["deposit_count"] == 2 and data["withdrawal_count"] == 1
        assert data["transaction_count"] == 3
        jan = next(m for m in data["monthly"] if m["month"] == "2025-01")
        assert jan["deposits"] == Decimal("1000.10")
        assert jan["withdrawals"] == Decimal("200.05")
        assert jan["count"] == 2
        feb = next(m for m in data["monthly"] if m["month"] == "2025-02")
        assert feb["net"] == Decimal("300.05")


def test_monthly_report_opening_closing_and_empty_carry_forward(app, customer):
    with app.app_context():
        aid = customer["account_id"]
        add_transaction(aid, "deposit", "500", datetime(2025, 1, 15))
        add_transaction(aid, "deposit", "75.50", datetime(2025, 2, 2))
        add_transaction(aid, "withdrawal", "25.25", datetime(2025, 2, 28, 23, 59, 59))
        feb = monthly_report(aid, 2025, 2)
        assert feb["opening_balance"] == Decimal("500.00")
        assert feb["total_deposits"] == Decimal("75.50")
        assert feb["total_withdrawals"] == Decimal("25.25")
        assert feb["closing_balance"] == Decimal("550.25")
        assert feb["transaction_count"] == 2
        march = monthly_report(aid, 2025, 3)
        assert march["opening_balance"] == march["closing_balance"] == Decimal("550.25")
        assert march["transaction_count"] == 0
        before = monthly_report(aid, 2024, 12)
        assert before["opening_balance"] == before["closing_balance"] == Decimal("0.00")


def test_large_amount_flag(app, customer):
    app.config["FLAG_LARGE_THRESHOLD"] = "1000.00"
    with app.app_context():
        tx = add_transaction(customer["account_id"], "deposit", "1000.01")
        flags = db.session.scalars(db.select(TransactionFlag).where(TransactionFlag.transaction_id == tx.transaction_id)).all()
        assert "large_amount" in [f.rule_name for f in flags]
        assert all(f.review_status == "pending" for f in flags)


def test_frequent_withdrawal_flag(app, customer):
    with app.app_context():
        aid = customer["account_id"]
        add_transaction(aid, "deposit", "1000")
        for _ in range(3):
            tx = add_transaction(aid, "withdrawal", "10")
        names = db.session.scalars(db.select(TransactionFlag.rule_name).where(TransactionFlag.transaction_id == tx.transaction_id)).all()
        assert "frequent_withdrawals" in names


def test_historical_amount_rule(app, customer):
    with app.app_context():
        for _ in range(5):
            add_transaction(customer["account_id"], "deposit", "10")
        tx = add_transaction(customer["account_id"], "deposit", "100")
        names = db.session.scalars(db.select(TransactionFlag.rule_name).where(TransactionFlag.transaction_id == tx.transaction_id)).all()
        assert "above_historical_average" in names


def test_review_can_be_marked_completed(authenticated, app, customer):
    with app.app_context():
        tx = add_transaction(customer["account_id"], "deposit", "100001")
        flag_id = db.session.scalar(db.select(TransactionFlag.flag_id).where(TransactionFlag.transaction_id == tx.transaction_id))
    assert authenticated.post(f"/reviews/{flag_id}").status_code == 302
    with app.app_context():
        assert db.session.get(TransactionFlag, flag_id).review_status == "reviewed"


def test_idempotency_key_cannot_be_reused_with_altered_amount(app, customer):
    with app.app_context():
        key = str(uuid4())
        post_transaction(customer["account_id"], "deposit", Decimal("10"), "memo", key)
        with pytest.raises(ValueError):
            post_transaction(customer["account_id"], "deposit", Decimal("20"), "memo", key)
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 1


@pytest.mark.parametrize("raw", ["0", "-1", "1e5", "NaN", "Infinity", "1.001", "abc", "10000000000000"])
def test_service_revalidates_amounts(raw):
    with pytest.raises(ValueError):
        parse_amount(raw)


def test_matplotlib_png_and_report_downloads(authenticated, app, customer):
    with app.app_context():
        add_transaction(customer["account_id"], "deposit", "250.25", datetime(2025, 1, 12))
        assert chart_png(customer["account_id"]).getvalue().startswith(b"\x89PNG")
    csv = authenticated.get("/reports/monthly.csv?year=2025&month=1")
    assert csv.status_code == 200 and b"250.25" in csv.data
    pdf = authenticated.get("/reports/monthly.pdf?year=2025&month=1")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF-")


def test_csv_escapes_spreadsheet_formula_injection(app, customer):
    with app.app_context():
        tx = add_transaction(customer["account_id"], "deposit", "10", description="=HYPERLINK(\"https://example.com\")")
        exported = transaction_csv([tx])
        if isinstance(exported, bytes):
            exported = exported.decode("utf-8-sig")
        assert "'=HYPERLINK" in exported


def test_transaction_and_balance_roll_back_together(app, customer, monkeypatch):
    def broken_rule(_transaction):
        raise RuntimeError("Simulated rule storage failure")

    monkeypatch.setattr("app.services.banking_service.flag_transaction", broken_rule)
    with app.app_context():
        with pytest.raises(RuntimeError, match="Simulated rule storage failure"):
            post_transaction(customer["account_id"], "deposit", Decimal("10.00"), "Must roll back", str(uuid4()))
        from app.models import Account
        assert db.session.get(Account, customer["account_id"]).balance == Decimal("0.00")
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 0


def test_balance_overflow_is_rejected_atomically(app, customer):
    with app.app_context():
        from app.models import Account
        post_transaction(customer["account_id"], "deposit", Decimal("9999999999999.99"), "Maximum amount", str(uuid4()))
        with pytest.raises(ValueError):
            post_transaction(customer["account_id"], "deposit", Decimal("0.01"), "Would overflow", str(uuid4()))
        assert db.session.get(Account, customer["account_id"]).balance == Decimal("9999999999999.99")
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 1
