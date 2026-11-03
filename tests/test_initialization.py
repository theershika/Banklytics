"""Additive demo initialization preserves users, balances and credentials."""
from decimal import Decimal
from uuid import uuid4
import pytest
from app.cli import seed_demo_accounts
from app.extensions import db
from app.models import Customer, Account, Transaction
from app.services.banking_service import post_transaction

PASSWORD = "LocalDemoPassword123!"


def test_five_demo_accounts_start_empty(app):
    with app.app_context():
        assert seed_demo_accounts(PASSWORD) == 5
        accounts = db.session.scalars(db.select(Account).order_by(Account.account_number)).all()
        assert [a.account_number for a in accounts] == ["1001", "1002", "1003", "1004", "1005"]
        assert all(a.balance == Decimal("0.00") for a in accounts)
        assert [a.customer.full_name for a in accounts] == [f"Demo Customer {i}" for i in range(1, 6)]
        assert all(a.customer.check_password(PASSWORD) for a in accounts)
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 0


def test_demo_seed_idempotent_and_preserves_balances_passwords(app):
    with app.app_context():
        seed_demo_accounts(PASSWORD)
        account = db.session.scalar(db.select(Account).where(Account.account_number == "1001"))
        account_id = account.account_id
        original_hash = account.customer.password_hash
        post_transaction(account_id, "deposit", Decimal("12.34"), "Preserve this existing balance", str(uuid4()))
        assert seed_demo_accounts("DifferentLocalPassword456!") == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(Account)) == 5
        account = db.session.get(Account, account_id)
        assert account.balance == Decimal("12.34")
        assert account.customer.password_hash == original_hash
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 1


def test_seed_conflict_rolls_back_without_replacing_existing_data(app, customer):
    with app.app_context():
        account = db.session.get(Account, customer["account_id"])
        account.account_number = "1003"
        account.balance = Decimal("35.00")
        db.session.commit()
        with pytest.raises(ValueError, match="already belongs"):
            seed_demo_accounts(PASSWORD)
        assert db.session.scalar(db.select(db.func.count()).select_from(Account)) == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(Customer)) == 1
        account = db.session.get(Account, customer["account_id"])
        assert account.account_number == "1003" and account.balance == Decimal("35.00")


def test_cli_init_db_is_additive_and_seed_repeats_safely(app):
    runner = app.test_cli_runner()
    assert runner.invoke(args=["init-db"]).exit_code == 0
    first = runner.invoke(args=["seed-demo", "--password", PASSWORD])
    assert first.exit_code == 0 and "Created 5" in first.output
    second = runner.invoke(args=["seed-demo", "--password", PASSWORD])
    assert second.exit_code == 0 and "Created 0" in second.output
    inspection = runner.invoke(args=["inspect-db"])
    assert inspection.exit_code == 0
    assert "accounts: 5 rows" in inspection.output


def test_init_db_refuses_incompatible_existing_schema_without_changes(tmp_path):
    from app import create_app
    from sqlalchemy import text, inspect
    application = create_app({"TESTING": True, "SECRET_KEY": "schema-preservation-test", "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "legacy.sqlite"),
                              "WTF_CSRF_ENABLED": False, "RATELIMIT_ENABLED": False, "SQLALCHEMY_ENGINE_OPTIONS": {}})
    with application.app_context():
        db.session.execute(text("CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, legacy_name TEXT)"))
        db.session.execute(text("INSERT INTO customers (customer_id, legacy_name) VALUES (1, 'Preserved legacy customer')"))
        db.session.commit()
    result = application.test_cli_runner().invoke(args=["init-db"])
    assert result.exit_code != 0
    assert "data-preserving migration" in result.output
    with application.app_context():
        assert inspect(db.engine).get_table_names() == ["customers"]
        assert db.session.execute(text("SELECT legacy_name FROM customers WHERE customer_id=1")).scalar_one() == "Preserved legacy customer"
        db.session.remove()
        db.engine.dispose()
