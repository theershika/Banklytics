"""Opt-in real MySQL locking tests against an EMPTY, dedicated ap_test_* schema.

Set TEST_MYSQL_URL=mysql+pymysql://user:password@host:3306/ap_test_unique.
This suite refuses banking_analysis and any schema that already contains tables.
It removes only the tables it created in that dedicated test schema.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from app import create_app
from app.extensions import db
from app.models import Customer, Account, Transaction
from app.services.banking_service import post_transaction

pytestmark = pytest.mark.mysql


@pytest.fixture
def mysql_app():
    raw_url = os.getenv("TEST_MYSQL_URL")
    if not raw_url:
        pytest.skip("Set TEST_MYSQL_URL for a dedicated empty ap_test_* MySQL database")
    url = make_url(raw_url)
    if url.get_backend_name() != "mysql" or not url.database or not url.database.startswith("ap_test_"):
        pytest.fail("TEST_MYSQL_URL must use MySQL with a dedicated database named ap_test_*")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        if inspect(engine).get_table_names():
            pytest.fail("MySQL tests refuse any nonempty database; choose an empty ap_test_* database")
    finally:
        engine.dispose()
    app = create_app({"TESTING": True, "SECRET_KEY": "mysql-isolation-test-only", "SQLALCHEMY_DATABASE_URI": raw_url,
                      "WTF_CSRF_ENABLED": False, "RATELIMIT_ENABLED": False})
    with app.app_context():
        db.create_all()
        customer = Customer(full_name="MySQL Test Customer", username="mysqltest", email="mysqltest@example.com", password_hash="not-a-login")
        db.session.add(customer); db.session.flush()
        account = Account(customer_id=customer.customer_id, account_number="MYSQL-TEST-ACCOUNT", balance=Decimal("0.00"))
        db.session.add(account); db.session.commit()
        app.config["TEST_ACCOUNT_ID"] = account.account_id
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


def test_mysql_concurrent_withdrawals_cannot_overdraw(mysql_app):
    app = mysql_app
    account_id = app.config["TEST_ACCOUNT_ID"]
    with app.app_context():
        post_transaction(account_id, "deposit", Decimal("100.00"), "Opening deposit", str(uuid4()))
    barrier = Barrier(2)

    def withdraw():
        with app.app_context():
            # Load a stale identity-map value before the race to ensure locking
            # refreshes existing SQLAlchemy objects as well as database rows.
            assert db.session.get(Account, account_id).balance == Decimal("100.00")
            barrier.wait(timeout=10)
            try:
                post_transaction(account_id, "withdrawal", Decimal("80.00"), "Concurrent withdrawal", str(uuid4()))
                return "committed"
            except ValueError as error:
                assert "Insufficient" in str(error)
                return "rejected"
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: withdraw(), range(2)))
    assert sorted(results) == ["committed", "rejected"]
    with app.app_context():
        assert db.session.get(Account, account_id).balance == Decimal("20.00")
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 2


def test_mysql_concurrent_duplicate_submission_is_once(mysql_app):
    app = mysql_app
    aid = app.config["TEST_ACCOUNT_ID"]
    key = str(uuid4())
    barrier = Barrier(2)

    def deposit():
        with app.app_context():
            barrier.wait(timeout=10)
            try:
                _, created = post_transaction(aid, "deposit", Decimal("0.10"), "Repeated request", key)
                return created
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=2) as pool:
        created = list(pool.map(lambda _: deposit(), range(2)))
    assert sorted(created) == [False, True]
    with app.app_context():
        assert db.session.get(Account, aid).balance == Decimal("0.10")
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 1


def test_mysql_decimal_persistence_after_restart(mysql_app):
    app = mysql_app
    aid = app.config["TEST_ACCOUNT_ID"]
    with app.app_context():
        post_transaction(aid, "deposit", Decimal("0.10"), "First", str(uuid4()))
        post_transaction(aid, "deposit", Decimal("0.20"), "Second", str(uuid4()))
        db.session.remove()
        db.engine.dispose()
    restarted = create_app({"TESTING": True, "SECRET_KEY": "mysql-restart-test", "SQLALCHEMY_DATABASE_URI": app.config["SQLALCHEMY_DATABASE_URI"],
                            "WTF_CSRF_ENABLED": False, "RATELIMIT_ENABLED": False})
    with restarted.app_context():
        assert db.session.get(Account, aid).balance == Decimal("0.30")
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 2
        db.session.remove()
        db.engine.dispose()


def test_mysql_all_accountpulse_tables_use_innodb(mysql_app):
    from sqlalchemy import text

    with mysql_app.app_context():
        rows = db.session.execute(text(
            "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE()"
        )).all()
        engines = {name: engine.upper() for name, engine in rows}
        assert set(engines) == {"customers", "accounts", "transactions", "transaction_flags"}
        assert all(engine == "INNODB" for engine in engines.values())
