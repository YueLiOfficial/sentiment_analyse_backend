from typing import Any
from dotenv import set_key

from engines.contracts.settings import get_settings, ENV_FILE, reload_settings


# ---------------- 配置白名单 ----------------
# 允许通过HTTP接口读写、修改.env的key清单
# 硬性约束：必须和engines.contracts.settings.Settings类定义字段一一对应；
# 不在白名单的配置项，前端接口禁止读取、禁止修改，保障系统安全。
ALLOWED_CONFIG_KEYS = [
    "DB_HOST", "DB_PORT", "DB_USER", "DB_NAME",
    "INSIGHT_ENGINE_API_KEY", "INSIGHT_ENGINE_BASE_URL", "INSIGHT_ENGINE_MODEL_NAME", "INSIGHT_ENGINE_MODEL_PROVIDER",
    "MEDIA_ENGINE_API_KEY", "MEDIA_ENGINE_BASE_URL", "MEDIA_ENGINE_MODEL_NAME", "MEDIA_ENGINE_MODEL_PROVIDER",
    "REPORT_ENGINE_API_KEY", "REPORT_ENGINE_BASE_URL", "REPORT_ENGINE_MODEL_NAME", "REPORT_ENGINE_MODEL_PROVIDER",
    "HOST_API_KEY", "HOST_BASE_URL", "HOST_MODEL_NAME", "HOST_MODEL_PROVIDER",
    "SEARCH_SWITCH", "TAVILY_API_KEY",
    "ANSPIRE_API_KEY", "ANSPIRE_BASE_URL"
]

class ConfigService:
    def __init__(self):
        ...

    def get_config_info(self) -> dict[str, Any]:
        env_config: dict = {}
        settings = get_settings()
        for key in ALLOWED_CONFIG_KEYS:
            value = getattr(settings, key, "")

            if key.endswith("_API_KEY"):
                value = f"****{value[-4:]}"

            env_config[key] = value
        print(env_config)

        return env_config

    def update_config_info(self, req: dict[str, Any]) -> None:
        update_config = {
            k: v for k, v in req.items()
            if k in ALLOWED_CONFIG_KEYS
        }

        if not update_config:
            raise ValueError("没有需要更新的配置信息")

        for k, v in update_config.items():
            set_key(ENV_FILE, k, v, quote_mode="never")

        reload_settings()
