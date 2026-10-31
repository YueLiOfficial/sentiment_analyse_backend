# engines/media_agent/web_search/factory.py
"""
web_search/factory.py
【web_search第四优先级；依赖 base.py、anspire_client、search_results.py】
Facade外观模式：网页搜索统一对外门面。
职责：
1. 对外暴露三个语义搜索方法 comprehensive_search / source_search / realtime_search；
2. 内部持有BaseSearchClient实现实例；后续切换搜索引擎，只修改此处实例化对象；
3. 返回SearchProviderResponse（Provider内部模型，本层只做转发，不做转换）。

约束：
上层业务节点禁止直接import本文件；业务节点只能调用retrieval_service。
"""
from engines.media_agent.web_search.base import BaseSearchClient
from engines.media_agent.web_search.providers.anspire_client import AnspireSearchClient
from engines.media_agent.web_search.search_results import SearchProviderResponse


class WebSearchClient:
    """网页搜索Facade外观；隔离底层Provider实现"""

    def __init__(self) -> None:
        # 后续切换搜索引擎，只修改这里new的实现类，上层全部不动
        # 读取配置文件
        # settings = get_settings()
        # if settings.SEARCH_PROVIDER == "anspire":
        #
        self._client: BaseSearchClient = AnspireSearchClient()

    async def comprehensive_search(self, query: str) -> SearchProviderResponse:
        """委托底层Provider执行综合检索语义策略"""
        return await self._client.comprehensive_search(query)

    async def source_search(self, query: str) -> SearchProviderResponse:
        """委托底层Provider执行溯源检索语义策略"""
        return await self._client.source_search(query)

    async def realtime_search(self, query: str) -> SearchProviderResponse:
        """委托底层Provider执行实时检索语义策略"""
        return await self._client.realtime_search(query)