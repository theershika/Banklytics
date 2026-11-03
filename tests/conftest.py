"""Isolated fixtures; the application database is never used by tests."""
from decimal import Decimal
import re
import pytest
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import Customer, Account

PASSWORD = "TestPassword123!"


@pytest.fixture
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "isolated-tests-only-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "accountpulse-test.sqlite"),
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "SQLALCHEMY_ENGINE_OPTIONS": {},
    })
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def customer(app):
    with app.app_context():
        person = Customer(full_name="Test Customer", username="testcustomer", email="test@example.com",
                          password_hash=generate_password_hash(PASSWORD))
        db.session.add(person)
        db.session.flush()
        account = Account(customer_id=person.customer_id, account_number="TEST1001", balance=Decimal("0.00"))
        db.session.add(account)
        db.session.commit()
        return {"customer_id": person.customer_id, "account_id": account.account_id, "username": person.username}


@pytest.fixture
def authenticated(client, customer):
    response = client.post("/login", data={"username": customer["username"], "password": PASSWORD})
    assert response.status_code == 302
    return client


def form_token(client, path="/deposit"):
    response = client.get(path)
    assert response.status_code == 200
    match = re.search(r'name="submission_key"[^>]*value="([^"]+)"', response.get_data(as_text=True))
    assert match, "Banking form must contain an idempotency key"
    return match.group(1)


def transfer(client, path, amount, description="Test transaction", key=None):
    key = key or form_token(client, path)
    return client.post(path, data={"amount": amount, "description": description, "submission_key": key})
