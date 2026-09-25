from datetime import datetime

from pydantic import BaseModel


class Error(BaseModel):
    timestamp: datetime
    status: int
    error: str
    message: str
    path: str
    details: list[str] | None = None