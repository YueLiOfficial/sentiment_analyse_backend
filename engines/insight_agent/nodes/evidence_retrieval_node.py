"""
节点：原始证据接入节点
文件：engines/insight_agent/nodes/evidence_retrieval_node.py

## 节点职责
1. 读取state中的用户原始query；
2. 调用工具层 InsightRetrievalService 双通道检索（MySQL关键词 + Milvus混合向量）；
3. 获取**尚未doc_id全局去重**的原始EvidenceRecord列表；
4. 将原始召回列表写入state["retrieved_records"]；
> 本节点约定：**只做调用检索服务，不做去重、不做重排打分**；去重合并交给下游evidence_reranking_node。

## 输入 state字段
- query：用户原始舆情研究query

## 输出 state增量字段
- retrieved_records：list[EvidenceRecord]，双通道召回原始证据集合，尚未全局doc_id去重

## 上下游
上游：Graph入口 START
下游：evidence_reranking_node 证据去重重排节点
"""
from typing import Any, Dict

from engines.common.research_graph_runtime import ResearchNode
from engines.insight_agent.state import InsightState


class EvidenceRetrievalNode(ResearchNode):
    """调用私域双通道召回服务，获取未做全局去重的原始召回证据。"""

    async def __call__( # type: ignore
        self,
        state: InsightState,
    ) -> Dict[str, Any]:
        # 业务实现下一章补齐；当前仅占位
        pass