from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="UUID")
    message: str = Field(..., description="Message", min_length=1, max_length=2000)

class ChatResponse(BaseModel):
    session_id: str = Field(..., description="UUID")
    reply: str = Field(..., description="Message")
    token_used: float = Field(..., description="Token used", ge=0)
    cost: float = Field(..., description="Cost", ge=0)
    model_used: str = Field(..., description="Model used")
    created_at: datetime
