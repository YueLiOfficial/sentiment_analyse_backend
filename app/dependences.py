from typing import Annotated

from fastapi import Depends

from app.services.config.config_service import ConfigService
from app.services.lifecycle.lifecycle_service import AppLifecycleManager
from app.services.report.report_service import ReportService
from app.services.research.research_service import ResearchService
from app.services.sse.research_progress_stream import ResearchProgressStream


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

_report_service = ReportService()


def get_report_service() -> ReportService:
    """提供全局报告生成服务单例"""
    return _report_service

ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]

_research_progress_stream = ResearchProgressStream()


def get_research_progress_stream() -> ResearchProgressStream:
    """提供全局研究进度 SSE 事件流单例"""
    return _research_progress_stream


_lifecycle_manager = AppLifecycleManager(_host_service,_research_progress_stream)


def get_lifecycle_manager() -> AppLifecycleManager:
    """提供全局生命周期管理器单例。"""
    return _lifecycle_manager