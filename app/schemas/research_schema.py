from pydantic.fields import Field
from pydantic.functional_validators import field_validator
from pydantic.main import BaseModel


class ResearchRequest(BaseModel):
    query: str = Field(..., description="研究主题，不能为空")

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(f"主题为空，请传入有效主题")
        return value

class ResearchResponse(BaseModel):
    task_id: str = Field(description="任务id")

class ResearchResultsResponse(BaseModel):
    task_id: str
    results: dict = Field(default_factory=dict)