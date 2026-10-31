from typing import Annotated

from fastapi import Depends

from app.services.config.config_service import ConfigService
from app.services.research.research_service import ResearchService


_config_service = ConfigService()

def get_config_service():
    return _config_service

CfgDepends = Annotated[ConfigService, Depends(get_config_service)]

_research_service = ResearchService()

def get_research_service():
    return _research_service

ResearchDepends = Annotated[ResearchService, Depends(get_research_service)]

from app.services.host.host_service import HostService

# 全局单例，会在fastapi启动时由lifecycle_manager实例化赋值
_host_service: HostService = HostService()


def get_host_service() -> HostService:
    return _host_service

HostServiceDep = Annotated[HostService, Depends(get_host_service)]