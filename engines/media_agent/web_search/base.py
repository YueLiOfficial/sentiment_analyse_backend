# engines/media_agent/web_search/base.py
"""
web_search/base.py
【web_search第二优先级；依赖search_results.py】
职责：
1. BaseSearchClient：搜索引擎Provider的抽象基类；所有第三方搜索适配器必须继承；
2. 封装通用工具：Bearer鉴权头、异步httpx请求send_request；

约束：
1. 上层业务流程禁止直接import本文件；只能通过factory/facade间接调用；
2. 本文件导入search_results.SearchProviderResponse作为抽象方法返回值。
"""
from abc import ABC, abstractmethod
from typing import Any, TypedDict
import httpx

from engines.media_agent.web_search.search_results import SearchProviderResponse


class HttpRequestOptions(TypedDict, total=False):
    """统一HTTP请求参数选项，send_request入参"""
    headers: dict[str, str]
    params: dict[str, Any]
    json: dict[str, Any]


class BaseSearchClient(ABC):
    """所有网页搜索Provider适配器的抽象基类"""

    def __init__(self) -> None:
        pass

    @staticmethod
    def build_request_headers(api_key: str, *, accept: str = "application/json") -> dict[str, str]:
        """构造标准Bearer鉴权请求头；多个provider复用"""
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": accept,
        }

    async def send_request(
        self,
        method: str,
        url: str,
        kwargs: HttpRequestOptions,
    ) -> dict[str, Any]:
        """
        通用异步http请求封装；所有Provider子类复用
        :param method: GET / POST
        :param url: 完整请求url
        :param kwargs: headers / params / json
        :return: http响应原始json字典
        """
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.request(
                method=method,
                url=url,
                headers=kwargs.get("headers"),
                params=kwargs.get("params"),
                json=kwargs.get("json"),
            )
            resp.raise_for_status()
            return resp.json()

    @abstractmethod
    async def comprehensive_search(self, query: str) -> SearchProviderResponse:
        """综合检索：不限站点、不限时间"""
        ...

    @abstractmethod
    async def source_search(self, query: str) -> SearchProviderResponse:
        """溯源检索：限定权威官媒/政府站点"""
        ...

    @abstractmethod
    async def realtime_search(self, query: str) -> SearchProviderResponse:
        """实时检索：社交站点 + 近7天时间窗口"""
        ...