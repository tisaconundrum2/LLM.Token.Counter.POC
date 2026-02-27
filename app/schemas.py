from pydantic import BaseModel, Field


class DeductRequest(BaseModel):
    email: str = Field(..., description="User email address")
    api_key: str = Field(..., description="API key for authentication")
    feature_type: str = Field(
        ...,
        description=(
            "Token type name to deduct from (e.g., 'agent_inference', 'well_pad_monitor')"
        ),
    )
    payload_to_measure: str | None = Field(
        default=None,
        description="Text to tokenize using tiktoken (for variable-cost features)",
    )
    model: str = Field(
        default="gpt-4",
        description="tiktoken encoding model to use when counting payload tokens",
    )
    quantity: int | None = Field(
        default=None,
        description="Fixed quantity to deduct (for fixed-unit features). Ignored when payload_to_measure is provided.",
        ge=1,
    )


class DeductSuccessData(BaseModel):
    deducted_amount: int
    remaining_balance: int
    token_type: str
    group_id: int
    transaction_ref: str


class DeductSuccessResponse(BaseModel):
    status: str = "success"
    data: DeductSuccessData


class DeductErrorData(BaseModel):
    required: int
    current_balance: int
    token_type: str


class DeductErrorResponse(BaseModel):
    status: str = "error"
    code: str
    message: str
    data: DeductErrorData
