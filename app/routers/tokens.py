from datetime import datetime, timezone

import tiktoken
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import ApiKey, TokenAudit, TokenBalance, TokenType, User
from app.schemas import (
    DeductErrorData,
    DeductErrorResponse,
    DeductRequest,
    DeductSuccessData,
    DeductSuccessResponse,
)
from database import get_db

router = APIRouter(prefix="/api/v1/tokens", tags=["tokens"])


def _count_tokens(text: str, model: str) -> int:
    """Return the number of tokens in *text* using the given tiktoken model encoding."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def _authenticate(db: Session, email: str, api_key: str) -> User:
    """Validate email + API key and return the active User row.

    Raises HTTPException 401 when credentials are invalid or the user is inactive.
    """
    stmt = (
        select(User)
        .join(ApiKey, ApiKey.user_id == User.user_id)
        .where(
            User.email == email,
            ApiKey.api_key == api_key,
            ApiKey.active.is_(True),
            User.active.is_(True),
        )
    )
    user = db.execute(stmt).scalars().first()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials or inactive account.")

    # Check API key expiry
    key_row = (
        db.execute(
            select(ApiKey).where(
                ApiKey.api_key == api_key, ApiKey.user_id == user.user_id
            )
        )
        .scalars()
        .first()
    )
    if key_row and key_row.expire_at and key_row.expire_at < datetime.now(timezone.utc).replace(
        tzinfo=None
    ):
        raise HTTPException(status_code=401, detail="API key has expired.")

    return user


@router.post(
    "/deduct",
    response_model=DeductSuccessResponse,
    responses={
        401: {"description": "Unauthorized – invalid credentials or inactive account"},
        402: {"description": "Payment Required – insufficient token balance"},
        422: {"description": "Validation Error"},
    },
    summary="Deduct tokens from a group's balance",
    description=(
        "Authenticate the user, count tokens (via tiktoken when a text payload is supplied), "
        "atomically deduct from the matching token-type bucket, and write an audit log entry.\n\n"
        "**Scenario A – Variable cost (agent inference)**:  supply `payload_to_measure` and "
        "`model`; tiktoken determines the cost.\n\n"
        "**Scenario B – Fixed unit cost (e.g., well pad monitor)**:  supply `quantity` instead."
    ),
)
def deduct_tokens(payload: DeductRequest, db: Session = Depends(get_db)):
    # 1. Authenticate
    user = _authenticate(db, payload.email, payload.api_key)

    if user.group_id is None:
        raise HTTPException(status_code=401, detail="User is not assigned to a group.")

    # 2. Determine cost
    if payload.payload_to_measure is not None:
        cost = _count_tokens(payload.payload_to_measure, payload.model)
    elif payload.quantity is not None:
        cost = payload.quantity
    else:
        raise HTTPException(
            status_code=422,
            detail="Either 'payload_to_measure' or 'quantity' must be provided.",
        )

    # 3. Resolve token type
    token_type_row = db.execute(
        select(TokenType).where(TokenType.name == payload.feature_type)
    ).scalars().first()
    if token_type_row is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown feature_type '{payload.feature_type}'.",
        )

    group_id = user.group_id
    type_id = token_type_row.type_id

    # 4. Atomic check-and-deduct
    result = db.execute(
        update(TokenBalance)
        .where(
            TokenBalance.group_id == group_id,
            TokenBalance.type_id == type_id,
            TokenBalance.balance >= cost,
        )
        .values(balance=TokenBalance.balance - cost)
        .returning(TokenBalance.balance, TokenBalance.balance_id)
    )
    row = result.fetchone()

    if row is None:
        # Either no balance record or insufficient funds
        balance_row = db.execute(
            select(TokenBalance).where(
                TokenBalance.group_id == group_id,
                TokenBalance.type_id == type_id,
            )
        ).scalars().first()
        current = balance_row.balance if balance_row else 0
        db.rollback()
        error_body = DeductErrorResponse(
            status="error",
            code="402",
            message=f"Insufficient balance for feature '{payload.feature_type}'.",
            data=DeductErrorData(
                required=cost,
                current_balance=current,
                token_type=payload.feature_type,
            ),
        )
        raise HTTPException(status_code=402, detail=error_body.model_dump())

    new_balance = row[0]

    # 5. Audit log (same transaction)
    audit = TokenAudit(
        group_id=group_id,
        type_id=type_id,
        amount=-cost,
        source=(
            "AGENT_API_USAGE"
            if payload.payload_to_measure is not None
            else "FEATURE_UNIT_USAGE"
        ),
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)

    return DeductSuccessResponse(
        data=DeductSuccessData(
            deducted_amount=cost,
            remaining_balance=new_balance,
            token_type=payload.feature_type,
            group_id=group_id,
            transaction_ref=f"audit_{audit.audit_id}",
        )
    )
