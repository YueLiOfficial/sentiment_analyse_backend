from typing import Annotated

from fastapi import Depends

from app.services.config.config_service import ConfigService


_config_service = ConfigService()

def get_config_service():
    return _config_service

CfgDepends = Annotated[ConfigService, Depends(get_config_service)]