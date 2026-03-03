"""
Tests for the /api/v1/tokens/deduct endpoint.

Uses an in-memory SQLite database so no external services are required.
"""
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.models import ApiKey, TokenBalance, TokenType, User, UserGroup
from database import Base, get_db
from main import app

# ---------------------------------------------------------------------------
# In-memory SQLite setup (StaticPool keeps the same connection across sessions)
# ---------------------------------------------------------------------------
TEST_DB_URL = "sqlite:///:memory:"
_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def override_get_db():
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=_engine)
    app.dependency_overrides.clear()


@pytest.fixture()
def db():
    session = _TestingSession()
    yield session
    session.close()


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
USER_ID = str(uuid.uuid4())
API_KEY = "deadbeef-cafe-babe-01234abecdef0"
GROUP_ID = 101


def seed(db, agent_balance: int = 500_000, well_balance: int = 5):
    group = UserGroup(group_id=GROUP_ID, name="Test Corp", active=True)
    user = User(user_id=USER_ID, email="test@example.com", group_id=GROUP_ID, active=True)
    key = ApiKey(api_key=API_KEY, user_id=USER_ID, active=True)
    t1 = TokenType(type_id=1, name="agent_inference", description="LLM tokens")
    t2 = TokenType(type_id=2, name="well_pad_monitor", description="Pad units")
    b1 = TokenBalance(group_id=GROUP_ID, type_id=1, balance=agent_balance)
    b2 = TokenBalance(group_id=GROUP_ID, type_id=2, balance=well_balance)
    db.add_all([group, user, key, t1, t2, b1, b2])
    db.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeductTokens:
    def test_variable_cost_success(self, client, db):
        seed(db)
        payload = {
            "email": "test@example.com",
            "api_key": API_KEY,
            "feature_type": "agent_inference",
            "payload_to_measure": "Hello world",
            "model": "gpt-4",
        }
        with patch("app.routers.tokens._count_tokens", return_value=18):
            resp = client.post("/api/v1/tokens/deduct", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["data"]["token_type"] == "agent_inference"
        assert data["data"]["deducted_amount"] == 18
        assert data["data"]["group_id"] == GROUP_ID
        assert "transaction_ref" in data["data"]

    def test_fixed_unit_success(self, client, db):
        seed(db)
        payload = {
            "email": "test@example.com",
            "api_key": API_KEY,
            "feature_type": "well_pad_monitor",
            "quantity": 1,
        }
        resp = client.post("/api/v1/tokens/deduct", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["deducted_amount"] == 1
        assert data["data"]["remaining_balance"] == 4

    def test_insufficient_balance_returns_402(self, client, db):
        seed(db, agent_balance=0)
        payload = {
            "email": "test@example.com",
            "api_key": API_KEY,
            "feature_type": "agent_inference",
            "payload_to_measure": "Any text",
            "model": "gpt-4",
        }
        with patch("app.routers.tokens._count_tokens", return_value=5):
            resp = client.post("/api/v1/tokens/deduct", json=payload)
        assert resp.status_code == 402
        detail = resp.json()["detail"]
        assert detail["code"] == "402"
        assert detail["data"]["current_balance"] == 0

    def test_invalid_api_key_returns_401(self, client, db):
        seed(db)
        payload = {
            "email": "test@example.com",
            "api_key": "wrong-key",
            "feature_type": "agent_inference",
            "payload_to_measure": "Hello",
            "model": "gpt-4",
        }
        resp = client.post("/api/v1/tokens/deduct", json=payload)
        assert resp.status_code == 401

    def test_invalid_email_returns_401(self, client, db):
        seed(db)
        payload = {
            "email": "nobody@example.com",
            "api_key": API_KEY,
            "feature_type": "agent_inference",
            "payload_to_measure": "Hello",
            "model": "gpt-4",
        }
        resp = client.post("/api/v1/tokens/deduct", json=payload)
        assert resp.status_code == 401

    def test_unknown_feature_type_returns_422(self, client, db):
        seed(db)
        payload = {
            "email": "test@example.com",
            "api_key": API_KEY,
            "feature_type": "nonexistent_feature",
            "quantity": 1,
        }
        resp = client.post("/api/v1/tokens/deduct", json=payload)
        assert resp.status_code == 422

    def test_no_payload_or_quantity_returns_422(self, client, db):
        seed(db)
        payload = {
            "email": "test@example.com",
            "api_key": API_KEY,
            "feature_type": "agent_inference",
        }
        resp = client.post("/api/v1/tokens/deduct", json=payload)
        assert resp.status_code == 422

    def test_balance_decrements_correctly(self, client, db):
        seed(db, well_balance=3)
        base = {
            "email": "test@example.com",
            "api_key": API_KEY,
            "feature_type": "well_pad_monitor",
            "quantity": 1,
        }
        client.post("/api/v1/tokens/deduct", json=base)
        client.post("/api/v1/tokens/deduct", json=base)
        resp = client.post("/api/v1/tokens/deduct", json=base)
        assert resp.status_code == 200
        assert resp.json()["data"]["remaining_balance"] == 0

        # Now balance is 0 – next call should 402
        resp = client.post("/api/v1/tokens/deduct", json=base)
        assert resp.status_code == 402

    def test_health_endpoint(self, client, db):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
