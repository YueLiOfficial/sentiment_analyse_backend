# engines/media_agent/web_search/providers/anspire_client.py
"""
web_search/providers/anspire_client.py
【web_search第三优先级；依赖 base.py、search_results.py】
职责：
1. 继承BaseSearchClient抽象基类，实现三套搜索抽象方法；
2. 读取配置中心：ANSPIRE_API_KEY、ANSPIRE_BASE_URL；
3. **全部搜索基础设施配置收敛到本文件**：权威站点白名单、社交站点白名单、实时搜索时间窗口、返回条数top_k；
4. 集成重试装饰器完成容错HTTP请求；完成第三方原始JSON → 内部领域模型WebpageResult / SearchProviderResponse转换。

重要设计约束：
1. LLM规划节点完全不感知域名白名单、时间窗口、top_k这类底层参数；LLM仅输出SearchTool枚举；
2. 如果运维需要修改站点白名单、条数、时间窗口，只修改本文件，无需改动Prompt、上层业务节点；
3. 上层业务禁止直接import本文件，统一通过factory/facade获取客户端实例。
"""
import datetime
from typing import Any

from engines.common.retrier import with_retry
from engines.contracts.settings import get_settings
from engines.media_agent.web_search.base import BaseSearchClient
from engines.media_agent.web_search.search_results import (
    SearchProviderResponse,
    WebpageResult,
)

# ======================【基础设施配置全部收敛此处】======================
# source_search溯源检索白名单：政府官网、中央权威媒体，逗号分隔字符串
AUTHORITATIVE_SOURCES = (
    "www.gov.cn,news.cn,xinhuanet.com,people.com.cn,"
    "news.cctv.com,chinanews.com.cn"
)

# realtime_search实时检索白名单：社交、资讯UGC站点，逗号分隔字符串
SOCIAL_SOURCES = "weibo.com,zhihu.com,toutiao.com"

# 实时搜索时间窗口：最近N周，当前配置近7天
REALTIME_WEEKS = 1

# 三套搜索策略默认返回结果条数top_k
TOP_K_COMPREHENSIVE = 15   # 综合检索返回条数
TOP_K_SOURCE = 10         # 溯源权威检索返回条数
TOP_K_REALTIME = 5        # 实时社交检索返回条数
# ======================================================================


class AnspireSearchClient(BaseSearchClient):
    """
    Anspire网页搜索Provider适配器
    继承抽象基类 BaseSearchClient，实现comprehensive_search / source_search / realtime_search
    """

    def __init__(self) -> None:
        super().__init__()
        # 从配置读取搜索服务密钥与接口地址
        settings = get_settings()
        self.api_key = settings.ANSPIRE_API_KEY
        self.base_url = settings.ANSPIRE_BASE_URL
        # 复用基类工具方法，构造Bearer鉴权请求头
        self.headers = self.build_request_headers(self.api_key) # type: ignore

    async def comprehensive_search(self, query: str) -> SearchProviderResponse:
        """
        综合检索：不限站点、不限时间范围，通用网页搜索
        :param query: 用户搜索query
        :return: 封装后的内部搜索响应对象
        """
        return await self._execute_search(query=query, top_k=TOP_K_COMPREHENSIVE)

    async def source_search(self, query: str) -> SearchProviderResponse:
        """
        溯源检索：限定政府、央媒等权威站点白名单，用于事实核查、溯源求证场景
        :param query: 用户搜索query
        :return: 封装后的内部搜索响应对象
        """
        return await self._execute_search(
            query=query,
            top_k=TOP_K_SOURCE,
            insite=AUTHORITATIVE_SOURCES
        )

    async def realtime_search(self, query: str) -> SearchProviderResponse:
        """
        实时检索：限定社交UGC站点，时间窗口为近7天，抓取热点、舆情类信息
        :param query: 用户搜索query
        :return: 封装后的内部搜索响应对象
        """
        to_time = datetime.datetime.now()
        from_time = to_time - datetime.timedelta(weeks=REALTIME_WEEKS)
        return await self._execute_search(
            query=query,
            top_k=TOP_K_REALTIME,
            insite=SOCIAL_SOURCES,
            from_time=from_time.strftime("%Y-%m-%d %H:%M:%S"),
            to_time=to_time.strftime("%Y-%m-%d %H:%M:%S"),
        )

    @with_retry
    async def _execute_search(
            self,
            query: str,
            top_k: int,
            insite: str = "",
            from_time: str = "",
            to_time: str = "",
    ) -> SearchProviderResponse:
        """
        内部统一请求执行入口
        组装全部查询参数，调用基类send_request发起GET http请求；
        @with_retry 重试装饰器规则：仅网络异常、5xx服务端错误自动重试；4xx业务错误直接抛出，不重试
        :param query: 搜索关键词
        :param top_k: 返回结果数量
        :param insite: 限定站点白名单，逗号拼接字符串，空代表不限制站点
        :param from_time: 时间过滤起始，格式 %Y-%m-%d %H:%M:%S，空代表不限制开始时间
        :param to_time: 时间过滤结束，格式 %Y-%m-%d %H:%M:%S，空代表不限制结束时间
        :return: SearchProviderResponse 内部领域模型
        """
        params = {
            "query": query,
            "top_k": top_k,
            "Insite": insite,
            "FromTime": from_time,
            "ToTime": to_time,
        }
        # 调用基类封装的通用异步http请求
        resp_dict = await self.send_request(
            method="GET",
            url=self.base_url, # type: ignore
            kwargs={
                "headers": self.headers,
                "params": params
            }
        )
        # 将第三方原始响应字典转换为项目内部领域对象
        return self._process_response(resp_dict, query)

    @staticmethod
    def _process_response(response_dict: dict[str, Any], query: str) -> SearchProviderResponse:
        """
        响应数据转换：Anspire原始接口JSON字典 → 内部领域模型 SearchProviderResponse / WebpageResult
        仅Provider内部调用，WebpageResult不会直接透出给上层业务节点
        :param response_dict: 第三方搜索接口原始返回字典
        :param query: 本次搜索的query，回写到领域模型
        :return: SearchProviderResponse
        """
        raw_results = response_dict.get("results", [])
        webpage_list: list[WebpageResult] = []
        for item in raw_results:
            webpage_list.append(
                WebpageResult(
                    title=item.get("title", ""),      # 网页标题，取不到给默认空字符串
                    url=item.get("url", ""),          # 网页链接
                    content=item.get("content", ""),  # 网页摘要片段
                    date=item.get("date", ""),        # 网页发布时间
                    score=float(item.get("score", 0.0)), # 搜索相关性得分，缺失默认0.0
                )
            )
        return SearchProviderResponse(query=query, webpages=webpage_list)


# 本地调试入口：直接运行本文件可测试三套搜索接口，不参与业务运行
if __name__ == "__main__":
    import asyncio

    async def demo() -> None:
        client = AnspireSearchClient()
        q = "英雄联盟s16什么时候开赛?"
        res_comprehensive = await client.comprehensive_search(q)
        print(f"综合搜索返回条数:{res_comprehensive.webpages}")

        res_source = await client.source_search(q)
        print(f"溯源搜索返回条数:{res_source.webpages}")

        res_realtime = await client.realtime_search(q)
        print(f"实时搜索返回条数:{res_realtime.webpages}")

    asyncio.run(demo())