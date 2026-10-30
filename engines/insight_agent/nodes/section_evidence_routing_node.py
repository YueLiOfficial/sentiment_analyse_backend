"""
节点：证据‑章节路由分配节点
文件：engines/insight_agent/nodes/section_evidence_routing_node.py

## 节点职责
1. 从运行时上下文或者初始化加载静态章节配置SECTION_DEFINITIONS，拿到私域各章节路由关键词；
2. 读取records_by_id证据权威字典、rerank_scores重排分数；
3. 遍历全部证据：依据证据正文、命中检索词、路由关键词匹配度、重排分数，把证据分配到一个/多个章节；
> 一条证据允许分配给多个章节（例如同时包含事件起因+群众情绪）；
4. 核心输出：section_record_ids；**字典value只存doc_id字符串列表，不拷贝完整EvidenceRecord，避免state数据膨胀**；
> 不做证据裁剪topN；topN截断放到下游section_preparation_node；路由阶段只建立映射关系。

## 输入 state字段
- records_by_id：dict[str,EvidenceRecord] 证据唯一权威副本
- rerank_scores：dict[str,float] 每条证据业务重排分数

## 输出 state增量字段
- section_record_ids：dict[str, list[str]]；key=section_key；value=归属该章节的doc_id字符串列表

## 构造阶段初始化动作【重要】
__init__构造阶段调用一次 get_insight_routing_rules()，把路由关键词加载到self.routing_rules；
禁止在__call__每轮业务执行反复读取全局配置，避免重复解析。

## 上下游
上游：evidence_reranking_node
下游：section_preparation_node 章节输入装配节点
"""
from typing import Any, Dict

from engines.common.research_graph_runtime import ResearchNode
from engines.insight_agent.state import InsightState


class SectionEvidenceRoutingNode(ResearchNode):
    """依据静态章节路由规则，把证据分配到对应报告章节；仅产出章节‑doc_id映射，不拷贝完整证据。"""

    async def __call__( # type: ignore
        self,
        state: InsightState,
    ) -> Dict[str, Any]:
        # 业务实现下一章补齐；当前仅占位
        pass