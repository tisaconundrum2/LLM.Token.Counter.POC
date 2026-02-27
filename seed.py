"""
seed.py – Populate the database with sample data for manual testing.

Usage:
    python seed.py
"""
import uuid

from sqlalchemy.orm import Session

from app.models import ApiKey, TokenAudit, TokenBalance, TokenType, User, UserGroup
from database import Base, SessionLocal, engine

Base.metadata.create_all(bind=engine)


def seed():
    db: Session = SessionLocal()
    try:
        # -- Groups --
        mg = UserGroup(group_id=101, name="Morgan Stanley", active=True)
        db.merge(mg)

        # -- Token types --
        agent = TokenType(type_id=1, name="agent_inference", description="LLM inference tokens")
        well = TokenType(type_id=2, name="well_pad_monitor", description="Active pad monitor units")
        db.merge(agent)
        db.merge(well)

        # -- User --
        uid = str(uuid.uuid4())
        user = User(
            user_id=uid,
            email="nfinch@somedomain.com",
            group_id=101,
            role="user",
            active=True,
        )
        db.merge(user)

        # -- API key --
        key = ApiKey(
            api_key="deadbeef-cafe-babe-01234abecdef0",
            user_id=uid,
            active=True,
        )
        db.merge(key)

        # -- Balances --
        b1 = TokenBalance(group_id=101, type_id=1, balance=1_000_000)
        b2 = TokenBalance(group_id=101, type_id=2, balance=5)
        db.merge(b1)
        db.merge(b2)

        # -- Audit: grant event --
        db.add(
            TokenAudit(group_id=101, type_id=1, amount=1_000_000, source="STRIPE_PURCHASE")
        )
        db.add(TokenAudit(group_id=101, type_id=2, amount=5, source="ADMIN_GRANT"))

        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
