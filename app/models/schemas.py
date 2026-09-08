"""Pydantic request/response models for the FastAPI layer."""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Natural language question")
    session_id: str | None = Field(
        None,
        description="Reuse across calls for rate limiting and trace grouping. "
        "A new one is generated and returned if omitted.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {"question": "What are the top 5 customers by revenue?"}
        }
    }


class ClarifyRequest(BaseModel):
    session_id: str = Field(
        ..., description="The session_id returned by the /query call that asked for clarification"
    )
    response: str = Field(..., min_length=1, description="The user's answer to the clarification question")

    model_config = {
        "json_schema_extra": {
            "example": {"session_id": "3f1b1e0a-...", "response": "MRR from active subscriptions"}
        }
    }


class QueryResponse(BaseModel):
    status: str = Field(..., description="'success', 'error', or 'clarification_needed'")
    session_id: str

    # populated when status == "success"
    sql: str | None = None
    assumptions: str | None = None
    columns: list[str] | None = None
    rows: list[dict] | None = None
    explanation: str | None = None

    # populated when status == "clarification_needed"
    clarification_question: str | None = None
    clarification_options: list[str] | None = None
    clarification_round: int | None = None

    # populated when status == "error"
    error: str | None = None


class TableSchema(BaseModel):
    table_name: str
    content: str
    column_count: int
    row_count: int


class SchemaResponse(BaseModel):
    tables: list[TableSchema]


class HealthResponse(BaseModel):
    status: str
    version: str
