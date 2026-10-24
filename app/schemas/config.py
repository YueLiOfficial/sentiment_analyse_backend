from typing import Any

from pydantic import BaseModel, Field, RootModel, field_validator

class ConfigUpdateRequest(RootModel[dict[str, Any]]):

    @field_validator("root")
    @classmethod
    def is_not_empty(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError(f"配置更新请求体不能为空")
        return value

class ConfigResponse(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict, description="读取完成的脱敏配置字典")