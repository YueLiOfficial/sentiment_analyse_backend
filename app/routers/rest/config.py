from fastapi import APIRouter

from app.dependences import CfgDepends
from app.schemas.config import ConfigResponse, ConfigUpdateRequest

config_router = APIRouter(prefix="/api/config", tags=["配置参数管理"])

# 配置参数查询接口
@config_router.get(path="", summary="配置参数查询接口", response_model=ConfigResponse)
def get_config(config_service: CfgDepends):
    config: dict = config_service.get_config_info()

    return ConfigResponse(
        config=config
    )

@config_router.post(path="", summary="配置参数更新接口")
def update_config(req: ConfigUpdateRequest, config_service: CfgDepends):
    config_service.update_config_info(req.root)

    return {"status": "ok"}