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
import dataclasses
from typing import Any
from loguru import logger
from engines.common.research_graph_runtime import ResearchNode
from engines.contracts.agent_rules import ROLE_INFOS

from engines.contracts.evidence import EvidenceRecord
from engines.insight_agent.state import InsightState
from engines.insight_agent.services.retrieval_service import InsightRetrievalService


class EvidenceRetrievalNode(ResearchNode):
    """调用私域召回服务获取尚未合并的原始证据。
    返回状态增量：{"retrieved_records": list[EvidenceRecord]}
    """
    async def __call__(self, state: InsightState) -> dict[str, Any]: # type: ignore


        """执行私域召回并返回尚未合并的原始命中记录。"""
        role = state['role']
        role_info = ROLE_INFOS[role]
        logger.info(f"{role_info.agent_name} 开始执行私域信息检索")

        # 日志会输出到哪个文件: role有关系

        # 调用双通道检索服务
        self.context.report_progress("searching", f"{role_info.agent_name} 开始执行私域信息搜索", 10)
        evidence_records = await InsightRetrievalService().retrieve_evidence(state["query"])
        self.context.report_progress("searching", f"{role_info.agent_name} 执行私域信息搜索完成", 20)
        logger.info(f"{role_info.agent_name} 私域信息检索完成，原始召回数量:{len(evidence_records)}")
        # node节点尽量返回增量结果! 如果返回state,并发节点会出现更新异常!
        return {"retrieved_records": evidence_records}


# ====================== 真实环境测试入口（直接运行脚本） ======================
async def run_evidence_retrieval_node_real():
    """
    前置条件：
        1. 项目配置加载完成
        2. MySQL可连通，有测试业务数据
        3. Milvus服务正常，向量数据已入库
        4. INSIGHT_VECTOR_ENABLED = True
    """
    # 构造图初始输入状态（和LangGraph启动时传入state格式完全一致）
    input_state: InsightState = {
        "query": "校园安全事件",   # 改成你的业务测试query
        "role": "insight",
    } # type: ignore

    print(f"=====【EvidenceRetrievalNode 真实场景测试】=====")
    print(f"输入查询query: {input_state['query']}")
    print(f"role: {input_state['role']}\n")

    # 实例化节点；真实graph运行会注入context，这里测试传None，当前节点不依赖context
    node = EvidenceRetrievalNode(context=None) # type: ignore

    # 执行节点真实逻辑
    output_increment = await node(input_state)

    # 拿到节点输出的状态增量
    retrieved_records: list[EvidenceRecord] = output_increment["retrieved_records"]

    print(f"\n>>>> 节点返回状态增量键: {list(output_increment.keys())}")
    print(f">>>> 双通道原始召回总条数: {len(retrieved_records)}")
    print("-" * 80)

    # 打印前5条证据预览（真实双通道结果，可以观察db_call / semantic_recall通道、命中词）
    show_max = 5
    for idx, rec in enumerate(retrieved_records[:show_max]):
        print(f"\n【证据 {idx+1}】")
        print(f"文档ID: {rec.id}")
        print(f"命中查询词: {rec.retrieval.matched_queries}")
        print(f"通道分数: {rec.retrieval.channel_scores}")
        print(f"文档片段: {rec.document.content[:120]}...")

    if len(retrieved_records) > show_max:
        print(f"\n......剩余 {len(retrieved_records)-show_max} 条省略")

    print("\n===== 真实节点测试执行完成 =====")


if __name__ == "__main__":
    import asyncio
    # 运行真实测试
    asyncio.run(run_evidence_retrieval_node_real())