from pydantic import BaseModel, Field


class GenerateChangeRequest(BaseModel):
    prompt: str = Field(..., min_length=5, description="Natural language description of the change")


class GeneratedChangeResponse(BaseModel):
    title: str
    change_type: str
    action: str
    environment: str
    description: str
    execution_plan: str
    rollback_plan: str
    target_components: list[str]
    risk_level: str | None = None
