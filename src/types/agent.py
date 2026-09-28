from pydantic import BaseModel


class AgentRequest(BaseModel):
    message: str


class AgentResponse(BaseModel):
    run_id: str
    reply: str
    steps: int
    tool_calls: list[str]
    stopped_by: str
