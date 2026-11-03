"""End-to-end Flask tests for authentication, forms, money, isolation and exports."""
from decimal import Decimal
from uuid import uuid4
import pytest
from werkzeug.security import check_password_hash
from app import create_app
from app.extensions import db
from app.models import Customer, Account, Transaction, TransactionFlag
from app.services.banking_service import post_transaction
from conftest import PASSWORD, transfer, form_token


def test_homepage_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"AccountPulse" in response.data
    assert b"simulation" in response.data.lower()


def test_registration_and_unique_zero_balance_account(client, app):
    response = client.post("/register", data={"full_name": "New Customer", "username": "newcustomer", "email": "new@example.com",
                          "password": PASSWORD, "confirm_password": PASSWORD})
    assert response.status_code == 302
    with app.app_context():
        person = db.session.execute(db.select(Customer).where(Customer.username == "newcustomer")).scalar_one()
        assert check_password_hash(person.password_hash, PASSWORD)
        assert person.password_hash != PASSWORD
        assert person.account.balance == Decimal("0.00")
        assert person.account.account_number
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 0


@pytest.mark.parametrize("field,value", [("username", "testcustomer"), ("email", "test@example.com")])
def test_duplicate_registration_rejected(client, customer, app, field, value):
    data = {"full_name": "Second Customer", "username": "secondcustomer", "email": "second@example.com", "password": PASSWORD, "confirm_password": PASSWORD}
    data[field] = value
    response = client.post("/register", data=data)
    assert response.status_code == 200
    assert b"already registered" in response.data
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Customer)) == 1


@pytest.mark.parametrize("changes", [{"username": "bad user"}, {"email": "invalid"}, {"password": "short", "confirm_password": "short"}, {"confirm_password": "Mismatch123"}, {"full_name": " A "}])
def test_registration_validation(client, app, changes):
    data = {"full_name": "Valid Customer", "username": "validuser", "email": "valid@example.com", "password": PASSWORD, "confirm_password": PASSWORD}
    data.update(changes)
    assert client.post("/register", data=data).status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Customer)) == 0


def test_login_success_and_logout(authenticated):
    assert authenticated.get("/dashboard").status_code == 200
    assert authenticated.get("/logout").status_code == 405
    assert authenticated.post("/logout").status_code == 302
    assert authenticated.get("/dashboard").status_code == 302


def test_invalid_login_rejected(client, customer):
    response = client.post("/login", data={"username": customer["username"], "password": "WrongPassword123"})
    assert response.status_code == 200
    assert b"Invalid username or password" in response.data
    assert client.get("/dashboard").status_code == 302


@pytest.mark.parametrize("path", ["/dashboard", "/deposit", "/withdraw", "/transactions", "/analytics", "/reports", "/reviews", "/profile"])
def test_routes_require_login(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert "/login" in response.location


def test_deposit_withdrawal_balance_and_history(authenticated, app, customer):
    assert transfer(authenticated, "/deposit", "1500.25", "Tuition fund").status_code == 302
    assert transfer(authenticated, "/withdraw", "125.10", "Books").status_code == 302
    with app.app_context():
        account = db.session.get(Account, customer["account_id"])
        assert account.balance == Decimal("1375.15")
        transactions = db.session.execute(db.select(Transaction).order_by(Transaction.transaction_id)).scalars().all()
        assert len(transactions) == 2
        assert transactions[0].balance_after == Decimal("1500.25")
        assert transactions[1].balance_after == Decimal("1375.15")
    history = authenticated.get("/transactions").get_data(as_text=True)
    assert "Tuition fund" in history
    assert "Books" in history


def test_insufficient_balance_rejected(authenticated, app, customer):
    transfer(authenticated, "/deposit", "10.00")
    response = transfer(authenticated, "/withdraw", "10.01")
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Account, customer["account_id"]).balance == Decimal("10.00")
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 1


@pytest.mark.parametrize("amount", ["0", "-1", "0.00", "abc", "1,000", "1e3", "NaN", "Infinity", "1.001", ".50", "10000000000000.00", "١٢٣", "000000000000000001", ""])
def test_invalid_amounts_do_not_change_balance(authenticated, app, customer, amount):
    assert transfer(authenticated, "/deposit", amount).status_code == 200
    with app.app_context():
        assert db.session.get(Account, customer["account_id"]).balance == Decimal("0.00")
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 0


def test_decimal_precision_preserved(authenticated, app, customer):
    for amount in ("0.10", "0.20", "0.01"):
        transfer(authenticated, "/deposit", amount)
    transfer(authenticated, "/withdraw", "0.30")
    with app.app_context():
        assert db.session.get(Account, customer["account_id"]).balance == Decimal("0.01")


def test_repeated_form_submission_is_idempotent(authenticated, app, customer):
    key = form_token(authenticated)
    assert transfer(authenticated, "/deposit", "50.00", key=key).status_code == 302
    assert transfer(authenticated, "/deposit", "50.00", key=key).status_code == 302
    with app.app_context():
        assert db.session.get(Account, customer["account_id"]).balance == Decimal("50.00")
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 1


def test_unissued_form_key_rejected(authenticated, app):
    transfer(authenticated, "/deposit", "50", key=str(uuid4()))
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 0


def test_each_page_renders_empty_and_populated(authenticated):
    paths = ("/dashboard", "/transactions", "/analytics", "/reports", "/reviews", "/profile")
    for path in paths:
        assert authenticated.get(path).status_code == 200, path
    transfer(authenticated, "/deposit", "250.00")
    for path in paths:
        assert authenticated.get(path).status_code == 200, path


def test_profile_update(authenticated, app, customer):
    response = authenticated.post("/profile", data={"full_name": "Updated Name", "email": "updated@example.com"})
    assert response.status_code == 302
    with app.app_context():
        person = db.session.get(Customer, customer["customer_id"])
        assert person.full_name == "Updated Name"
        assert person.email == "updated@example.com"
        assert person.account.account_number == "TEST1001"


def test_history_search_filter_sort_pagination_and_export(authenticated):
    transfer(authenticated, "/deposit", "100", "Unique deposit memo")
    transfer(authenticated, "/withdraw", "15", "Unique withdrawal memo")
    response = authenticated.get("/transactions?q=deposit")
    assert b"Unique deposit memo" in response.data
    assert b"Unique withdrawal memo" not in response.data
    response = authenticated.get("/transactions?type=withdrawal&sort=oldest")
    assert b"Unique withdrawal memo" in response.data
    assert b"Unique deposit memo" not in response.data
    assert authenticated.get("/transactions?page=2").status_code == 200
    response = authenticated.get("/transactions/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.content_type
    assert b"Unique deposit memo" in response.data


def test_account_authorization(authenticated, app, customer):
    with app.app_context():
        other = Customer(full_name="Other Customer", username="othercustomer", email="other@example.com", password_hash="unused")
        db.session.add(other); db.session.flush()
        account = Account(account_number="OTHER1002", customer_id=other.customer_id, balance=Decimal("0.00"))
        db.session.add(account); db.session.commit()
        other_id = account.account_id
        tx, _ = post_transaction(other_id, "deposit", Decimal("120000.00"), "Secret other-account memo", str(uuid4()))
        tx_id = tx.transaction_id
        flag = TransactionFlag(transaction_id=tx_id, rule_name="test", reason="Secret review memo", review_status="pending")
        db.session.add(flag); db.session.commit()
        flag_id = flag.flag_id
    for path in ("/dashboard", "/transactions", "/analytics", "/reports", "/reviews", "/transactions/export.csv"):
        response = authenticated.get(path + "?account_id=" + str(other_id))
        assert response.status_code == 200, path
        assert b"Secret other-account memo" not in response.data
        assert b"Secret review memo" not in response.data
    assert authenticated.post(f"/reviews/{flag_id}").status_code == 404


def test_persistence_across_app_restarts(authenticated, app, customer):
    transfer(authenticated, "/deposit", "789.12", "Persistent record")
    restarted = create_app({"TESTING": True, "SECRET_KEY": "new-test-key", "SQLALCHEMY_DATABASE_URI": app.config["SQLALCHEMY_DATABASE_URI"],
                            "WTF_CSRF_ENABLED": False, "RATELIMIT_ENABLED": False, "SQLALCHEMY_ENGINE_OPTIONS": {}})
    with restarted.app_context():
        assert db.session.get(Account, customer["account_id"]).balance == Decimal("789.12")
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 1


def test_csrf_rejects_missing_token(app, customer):
    app.config["WTF_CSRF_ENABLED"] = True
    client = app.test_client()
    assert client.post("/login", data={"username": customer["username"], "password": PASSWORD}).status_code == 400


def test_transaction_date_filter_includes_whole_end_day(authenticated, app, customer):
    from datetime import datetime
    with app.app_context():
        for date, description in [(datetime(2025, 1, 1), "January-only memo"),
                                  (datetime(2025, 2, 28, 23, 59, 59), "February-end memo"),
                                  (datetime(2025, 3, 1), "March-only memo")]:
            tx, _ = post_transaction(customer["account_id"], "deposit", Decimal("1.00"), description, str(uuid4()))
            tx.transaction_date = date
            db.session.commit()
    page = authenticated.get("/transactions?start_date=2025-02-01&end_date=2025-02-28")
    assert b"February-end memo" in page.data
    assert b"January-only memo" not in page.data
    assert b"March-only memo" not in page.data
    export = authenticated.get("/transactions/export.csv?start_date=2025-02-01&end_date=2025-02-28")
    assert b"February-end memo" in export.data
    assert b"January-only memo" not in export.data


def test_transaction_history_paginates_records(authenticated, app, customer):
    with app.app_context():
        for i in range(18):
            post_transaction(customer["account_id"], "deposit", Decimal("1.00"), f"Pagination record {i:03d}", str(uuid4()))
    first = authenticated.get("/transactions?page=1")
    second = authenticated.get("/transactions?page=2")
    assert first.status_code == second.status_code == 200
    assert b"Pagination record 017" in first.data
    assert b"Pagination record 000" not in first.data
    assert b"Pagination record 000" in second.data
    assert b"Pagination record 017" not in second.data


@pytest.mark.parametrize("query", ["year=not-a-year&month=1", "year=2025&month=13", "year=9999&month=12", "year=2025&month=0"])
def test_invalid_report_periods_rejected(authenticated, query):
    assert authenticated.get("/reports?" + query).status_code == 400


def test_maximum_date_filter_is_valid(authenticated):
    assert authenticated.get("/transactions?end_date=9999-12-31").status_code == 200
    assert authenticated.get("/transactions/export.csv?end_date=9999-12-31").status_code == 200


def test_database_user_loader_failure_returns_safe_actionable_error(authenticated, monkeypatch, caplog):
    from sqlalchemy.exc import OperationalError

    secret_marker = "private-test-password-do-not-render"

    def unavailable_database(*args, **kwargs):
        raise OperationalError("SELECT private_customer_data WHERE password=:password",
                               {"password": secret_marker}, RuntimeError("Database server unavailable"))

    # The browser already has a valid login session. A subsequent request fails
    # while Flask-Login loads that customer, before the dashboard route executes.
    monkeypatch.setattr(db.session, "get", unavailable_database)
    response = authenticated.get("/dashboard")
    assert response.status_code == 503
    page = response.get_data(as_text=True)
    assert "Database unavailable" in page
    assert "DATABASE_URL" in page and "init-db" in page
    assert secret_marker not in page
    assert "SELECT private_customer_data" not in page
    assert secret_marker not in caplog.text
    assert "SELECT private_customer_data" not in caplog.text


def _real_csrf_token(client, path):
    import re
    response = client.get(path)
    assert response.status_code == 200
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.get_data(as_text=True))
    assert match, "Rendered form must contain a real signed CSRF token"
    return match.group(1)


def _login_with_real_csrf(client, customer):
    token = _real_csrf_token(client, "/login")
    response = client.post("/login", data={"username": customer["username"], "password": PASSWORD, "csrf_token": token})
    assert response.status_code == 302
    assert response.location.endswith("/dashboard")


def test_real_csrf_valid_login_and_deposit_flow(app, client, customer):
    # Keep the application's configured expiration. Overriding it here would
    # conceal incompatibilities between Flask-WTF and itsdangerous.
    app.config["WTF_CSRF_ENABLED"] = True
    _login_with_real_csrf(client, customer)
    token = _real_csrf_token(client, "/deposit")
    with client.session_transaction() as browser_session:
        submission_key = browser_session["transaction_tokens"][-1]
    response = client.post("/deposit", data={"amount": "12.34", "description": "Valid signed form", "submission_key": submission_key,
                                            "csrf_token": token})
    assert response.status_code == 302
    assert response.location.endswith("/transactions")
    with app.app_context():
        assert db.session.get(Account, customer["account_id"]).balance == Decimal("12.34")
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 1


def test_real_csrf_invalid_deposit_token_rejected(app, client, customer):
    app.config["WTF_CSRF_ENABLED"] = True
    _login_with_real_csrf(client, customer)
    _real_csrf_token(client, "/deposit")
    with client.session_transaction() as browser_session:
        submission_key = browser_session["transaction_tokens"][-1]
    response = client.post("/deposit", data={"amount": "12.34", "description": "Must not be posted", "submission_key": submission_key,
                                            "csrf_token": "invalid-signed-token"})
    assert response.status_code == 400
    with app.app_context():
        assert db.session.get(Account, customer["account_id"]).balance == Decimal("0.00")
        assert db.session.scalar(db.select(db.func.count()).select_from(Transaction)) == 0
