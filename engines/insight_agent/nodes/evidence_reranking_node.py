"""
节点：证据去重合并与重排打分节点
文件：engines/insight_agent/nodes/evidence_reranking_node.py

## 节点职责
1. 读取上游retrieved_records（存在doc_id重复，多通道/多关键词命中产生多条记录）；
2. 调用hybrid_recall(_dedupe_and_merge)：按doc_id全局去重；合并同doc的matched_queries、合并多通道channel_scores；
3. 执行证据质量过滤：剔除过短、噪声、无效证据；
4. 综合：各通道原始召回分数、帖子热度、发布时效性，计算业务重排分数；
5. 产出：
    - records_by_id：dict[str,EvidenceRecord]，**全链路唯一权威证据副本字典，key=doc_id**；
    - rerank_scores：dict[str,float]，key=doc_id，value=本任务业务综合重排分；

> 重要约束：
> 1. 只修改/产出rerank_scores业务分；**绝对禁止改写EvidenceRecord内部RetrievalMeta.channel_scores原始召回分数，保留原始信号用于评估复现**；
> 2. records_by_id是后续全流程证据唯一权威来源；后续链路优先传递doc_id字符串，不拷贝完整EvidenceRecord，控制state体积。

## 输入 state字段
- retrieved_records：list[EvidenceRecord]，双通道原始召回，存在doc_id重复

## 输出 state增量字段
- records_by_id：dict[str, EvidenceRecord]；doc_id → 完整证据，全局唯一权威副本
- rerank_scores：dict[str, float]；doc_id → 业务综合重排分数

## 上下游
上游：evidence_retrieval_node
下游：section_evidence_routing_node 证据章节路由节点
"""
from typing import Any, Dict

from engines.common.research_graph_runtime import ResearchNode
from engines.insight_agent.state import InsightState


class EvidenceRerankingNode(ResearchNode):
    """合并重复召回证据、合并召回元数据，执行证据过滤，计算统一业务重排分。"""

    async def __call__( # type: ignore
        self,
        state: InsightState,
    ) -> Dict[str, Any]:
        # 业务实现下一章补齐；当前仅占位
        pass