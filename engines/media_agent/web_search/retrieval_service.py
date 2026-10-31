# engines/media_agent/web_search/retrieval_service.py
"""
web_search/retrieval_service.py
【web_search第五优先级；依赖factory、search_results、全局contracts.evidence】
【LangGraph业务节点唯一允许依赖的web_search模块】
职责：
1. 对外唯一方法：retrieve_evidence(tool_name,query) → list[EvidenceRecord]
2. 根据SearchTool枚举，分发调用Facade WebSearchClient；
3. 【核心转换器】Provider内部WebpageResult → 公私域统一契约EvidenceRecord；
4. 配套工具：_extract_source_name域名提取；_generate_content_hash_id正文哈希生成稳定mysql_primary_key，用于上层业务章内证据去重。

数据流：
业务节点SearchNode
    → MediaRetrievalService.retrieve_evidence(SearchTool枚举 + query)
        → WebSearchClient(Facade)
            → AnspireSearchClient(Provider)
        ← SearchProviderResponse / WebpageResult（仅本层内部可见，不透传给业务节点）
        → _map_to_evidence_records()转换器
    ← list[EvidenceRecord]（公私域统一证据对象，返回给业务节点）

约束：
业务节点禁止直接import base/factory/providers；全部通过本服务隔离。
"""
import hashlib
from urllib.parse import urlparse
from typing import List

from engines.contracts.evidence import EvidenceDocument, EvidenceRecord, RetrievalMeta
from engines.media_agent.web_search.factory import WebSearchClient
from engines.media_agent.web_search.search_results import (
    SearchProviderResponse,
    SearchTool,
    WebpageResult,
)


class MediaRetrievalService:
    """公域网页检索编排服务；业务节点调用本服务，获取标准化证据列表。"""

    def __init__(self) -> None:
        self._web_search_client = WebSearchClient()

    async def retrieve_evidence(
        self,
        tool_name: SearchTool,
        query: str,
    ) -> list[EvidenceRecord]:
        """
        对外暴露唯一入口
        :param tool_name: 搜索策略枚举 SearchTool
        :param query: 完整拼接后的搜索query
        :return: list[EvidenceRecord] 标准化公私域统一证据对象
        """
        provider_resp:SearchProviderResponse = await self._dispatch_search(tool_name, query)
        evidence_records:list[EvidenceRecord] = _map_to_evidence_records(provider_resp, matched_query=query)
        return evidence_records

    async def _dispatch_search(
        self,
        tool_name: SearchTool,
        query: str,
    ) -> SearchProviderResponse:
        """内部：根据SearchTool枚举分发调用Facade三个语义搜索"""
        match tool_name:
            case "source_search":
                return await self._web_search_client.source_search(query)
            case "realtime_search":
                return await self._web_search_client.realtime_search(query)
            case _:
                # 其余全部走综合搜索 comprehensive_search
                return await self._web_search_client.comprehensive_search(query)


def _map_to_evidence_records(
    response: SearchProviderResponse,
    matched_query: str,
) -> list[EvidenceRecord]:
    """
    【核心转换器】
    Provider内部模型 WebpageResult → 公私域统一契约 EvidenceRecord
    设计目的：
    1. 屏蔽第三方网页搜索返回结构；后续换搜索引擎，只修改本转换器；
    2. 公私域证据对象完全统一，BaseSectionSummaryNode、build_evidence_context可以直接复用，不需要两套渲染逻辑。

    字段映射规则：
    - document.platform / source_name：从url提取标准化域名；
    - source_table固定="webpage"，标记证据来源为公域网页；
    - mysql_primary_key：基于网页正文归一化后md5哈希生成稳定id，**给上层SearchNode做章内证据去重**；
    - retrieval元数据：记录本次匹配query，Anspire分数存入channel_scores["web_call"]。
    """
    records: list[EvidenceRecord] = []
    for page in response.webpages:
        source_name = _extract_source_name(page.url)
        content = page.content
        records.append(
            EvidenceRecord(
                document=EvidenceDocument(
                    platform=source_name,
                    source_table="webpage",
                    mysql_primary_key=_generate_content_hash_id(content),  # 依然是唯一标识,借用mysql_primary_key # type: ignore
                    content=content,
                    published_at=page.date, # type: ignore
                    url=page.url,
                    title=page.title,
                    source_name=source_name,
                ),
                retrieval=RetrievalMeta(
                    matched_queries=[matched_query],
                    channel_scores={"web_call": page.score},
                ),
            )
        )
    return records


def _extract_source_name(url: str) -> str:
    """
    工具函数：url解析hostname，去除www.前缀，产出标准化来源域名。
    示例：https://www.xinhuanet.com/a/b/c → xinhuanet.com
    """
    hostname = urlparse(url).hostname
    if not hostname:
        return "unknown_web"
    hostname = hostname.lower()
    return hostname.removeprefix("www.")


def _generate_content_hash_id(content: str) -> str:
    """
    工具函数：网页正文归一化后md5哈希生成mysql_primary_key；
    用途：上层SearchNode【章内证据去重】；
    优势：**同一篇报道多个镜像不同url，正文一致，hash_id一致，可以识别重复；只用url会漏判重复网页**。
    """
    normalized_content = " ".join(content.split()).strip()
    raw_key = normalized_content
    return hashlib.md5(raw_key.encode("utf-8")).hexdigest()


# 本地调试入口：直接跑检索服务，看转换之后EvidenceRecord输出
if __name__ == "__main__":
    import asyncio

    async def demo() -> None:
        service = MediaRetrievalService()
        query = "高考舆情"
        tools: list[SearchTool] = ["comprehensive_search", "source_search", "realtime_search"]
        for tool in tools:
            print(f"\n=====测试工具 {tool} =====")
            records = await service.retrieve_evidence(tool_name=tool, query=query)
            print(f"获取证据条数={len(records)}")
            for idx, rec in enumerate(records[:2], start=1):
                doc = rec.document
                score = rec.retrieval.channel_scores.get("web_call", 0.0)
                print(f"[{idx}] domain={doc.platform}, mysql_primary_key={doc.mysql_primary_key}, score={score:.2f}, title={doc.title[:60]}")

    asyncio.run(demo())