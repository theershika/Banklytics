import os
import tempfile
import re
import pytest

fd, path = tempfile.mkstemp(suffix=".db")
os.close(fd)
os.environ["DATABASE_URL"] = f"sqlite:///{path}"
os.environ["SECRET_KEY"] = "test"
from app import app, db, Customer, Account, Transaction, User

@pytest.fixture()
def client():
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI=f"sqlite:///{path}", WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all(); db.create_all()
        customer = Customer(customer_code="CUS-00001", full_name="Test User", email="test@example.test", phone="9999999999")
        db.session.add(customer); db.session.flush()
        db.session.add(Account(account_number="ACC-00001", customer=customer, opening_balance=1000, account_type="Savings")); db.session.commit()
        user = User(full_name="Tester", email="tester@example.test")
        user.set_password("securepass")
        user.customer_id = customer.id
        db.session.add(user); db.session.commit()
    with app.test_client() as test_client:
        with test_client.session_transaction() as session:
            session["user_id"] = 1
        yield test_client

def test_dashboard_loads(client):
    assert client.get("/").status_code == 200

def test_positive_deposit_is_recorded(client):
    response = client.post("/transactions", data={"account_id": 1, "transaction_type":"Deposit", "amount":"50", "transaction_date":"2026-10-01"}, follow_redirects=True)
    assert b"Transaction recorded" in response.data
    with app.app_context(): assert Transaction.query.count() == 1

def test_invalid_withdrawal_rejected(client):
    response = client.post("/transactions", data={"account_id": 1, "transaction_type":"Withdrawal", "amount":"1500", "transaction_date":"2026-10-01"}, follow_redirects=True)
    assert b"cannot exceed" in response.data
    with app.app_context(): assert Transaction.query.count() == 0

def test_high_value_transaction_is_flagged(client):
    client.post("/transactions", data={"account_id": 1, "transaction_type":"Deposit", "amount":"60000", "transaction_date":"2026-10-01"})
    with app.app_context(): assert Transaction.query.one().is_unusual

def test_registration_login_and_protected_dashboard(client):
    client.post("/logout")
    assert client.get("/", follow_redirects=False).status_code == 302
    response = client.post("/register", data={"full_name": "New User", "email": "new@example.test", "password": "password9", "confirm_password": "password9"}, follow_redirects=True)
    assert b"Registration complete" in response.data
    client.post("/logout")
    response = client.post("/login", data={"email": "new@example.test", "password": "password9"}, follow_redirects=True)
    assert b"Welcome back" in response.data

def test_history_reports_csv_and_matplotlib_chart(client):
    client.post("/transactions", data={"account_id": 1, "transaction_type":"Deposit", "amount":"60000", "transaction_date":"2026-10-01"})
    assert b"TXN-" in client.get("/transactions").data
    assert client.get("/reports").status_code == 200
    csv_response = client.get("/export/transactions.csv")
    assert csv_response.status_code == 200 and b"Transaction ID" in csv_response.data
    chart = client.get("/reports/monthly-chart.png")
    assert chart.status_code == 200 and chart.mimetype == "image/png" and chart.data.startswith(b"\x89PNG")

def test_pdf_receipt_statement_and_admin_restriction(client):
    client.post("/transactions", data={"account_id": 1, "transaction_type":"Deposit", "amount":"100", "transaction_date":"2026-10-01"})
    receipt = client.get("/transactions/1/receipt.pdf")
    statement = client.get("/accounts/1/statement.pdf?month=2026-10")
    assert receipt.status_code == 200 and receipt.data.startswith(b"%PDF")
    assert statement.status_code == 200 and statement.data.startswith(b"%PDF")
    assert client.get("/admin", follow_redirects=False).status_code == 302

def test_five_demo_accounts_balances_history_and_filters(client):
    """QA coverage for five independent demo accounts in the isolated database."""
    with app.app_context():
        customer = Customer.query.first()
        for i in range(2, 6):
            db.session.add(Account(account_number=f"ACC-0000{i}", customer=customer, opening_balance=1000 * i, account_type="Savings"))
        db.session.commit()
        accounts = Account.query.order_by(Account.id).all()
        assert len(accounts) == 5
    for index, account in enumerate(accounts, 1):
        result = client.post("/transactions", data={"account_id": account.id, "transaction_type":"Deposit", "amount":str(index * 100), "transaction_date":"2026-10-01", "description":f"Deposit {index}"}, follow_redirects=True)
        assert b"Transaction recorded" in result.data
        result = client.post("/transactions", data={"account_id": account.id, "transaction_type":"Withdrawal", "amount":"50", "transaction_date":"2026-10-02", "description":f"Withdrawal {index}"}, follow_redirects=True)
        assert b"Transaction recorded" in result.data
    assert b"Deposit 3" in client.get("/transactions?search=Deposit+3&sort=amount_high").data
    assert client.get("/transactions?date_from=2026-10-01&date_to=2026-10-31&min_amount=50&max_amount=500").status_code == 200
    with app.app_context():
        assert db.session.get(Account, 1).balance == 1050
        assert Transaction.query.count() == 10

def test_invalid_amount_and_admin_authorization(client):
    for amount in ("0", "-10", "not-a-number"):
        response = client.post("/transactions", data={"account_id":1, "transaction_type":"Deposit", "amount":amount, "transaction_date":"2026-10-01"}, follow_redirects=True)
        assert b"positive amount" in response.data
    with app.app_context():
        user = User.query.filter_by(email="tester@example.test").one(); user.role = "admin"; db.session.commit()
    response = client.get("/admin")
    assert response.status_code == 200 and b"Administrator analytics" in response.data

def test_navigation_pages_and_responsive_stylesheet(client):
    for path in ("/", "/transactions", "/reports"):
        assert client.get(path).status_code == 200
    assert client.get("/customers").status_code == 403
    assert client.get("/accounts").status_code == 403
    stylesheet = client.get("/static/css/style.css")
    assert stylesheet.status_code == 200 and b"@media(max-width:767px)" in stylesheet.data

def test_health_and_csrf_protection(client):
    assert client.get("/health").status_code == 200
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        page = client.get("/transactions")
        assert b'name="csrf_token"' in page.data
        assert client.post("/transactions", data={"account_id": 1}).status_code == 400
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        response = client.post("/transactions", data={"csrf_token": token, "account_id": 1, "transaction_type":"Deposit", "amount":"10", "transaction_date":"2026-10-01"})
        assert response.status_code == 302
    finally:
        app.config["WTF_CSRF_ENABLED"] = False

def test_customer_cannot_access_another_customers_account(client):
    with app.app_context():
        outsider = Customer(customer_code="CUS-00002", full_name="Other User", email="other@example.test", phone="9000000000")
        db.session.add(outsider); db.session.flush()
        db.session.add(Account(account_number="ACC-00002", customer=outsider, opening_balance=500, account_type="Savings"))
        other_user = User(full_name="Other", email="otheruser@example.test", customer_id=outsider.id)
        other_user.set_password("securepass")
        db.session.add(other_user); db.session.commit()
    response = client.post("/transactions", data={"account_id": 2, "transaction_type":"Deposit", "amount":"25", "transaction_date":"2026-10-01"})
    assert response.status_code == 403
    assert client.get("/accounts/2/statement.pdf").status_code == 403
