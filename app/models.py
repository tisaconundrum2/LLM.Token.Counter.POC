from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class UserGroup(Base):
    __tablename__ = "user_group"

    group_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    users: Mapped[list["User"]] = relationship("User", back_populates="group")
    token_balances: Mapped[list["TokenBalance"]] = relationship(
        "TokenBalance", back_populates="group"
    )
    token_audits: Mapped[list["TokenAudit"]] = relationship(
        "TokenAudit", back_populates="group"
    )


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user_group.group_id"), nullable=True
    )
    role: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    group: Mapped["UserGroup | None"] = relationship("UserGroup", back_populates="users")
    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="user")


class ApiKey(Base):
    __tablename__ = "api_keys"

    key_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="api_keys")


class TokenType(Base):
    __tablename__ = "token_types"

    type_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    balances: Mapped[list["TokenBalance"]] = relationship(
        "TokenBalance", back_populates="token_type"
    )
    audits: Mapped[list["TokenAudit"]] = relationship(
        "TokenAudit", back_populates="token_type"
    )


class TokenBalance(Base):
    __tablename__ = "token_balances"
    __table_args__ = (UniqueConstraint("group_id", "type_id", name="uq_group_type"),)

    balance_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_group.group_id"), nullable=False
    )
    type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("token_types.type_id"), nullable=False
    )
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    group: Mapped["UserGroup"] = relationship("UserGroup", back_populates="token_balances")
    token_type: Mapped["TokenType"] = relationship("TokenType", back_populates="balances")


class TokenAudit(Base):
    __tablename__ = "token_audit"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_group.group_id"), nullable=False
    )
    type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("token_types.type_id"), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_dt: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    group: Mapped["UserGroup"] = relationship("UserGroup", back_populates="token_audits")
    token_type: Mapped["TokenType"] = relationship("TokenType", back_populates="audits")
