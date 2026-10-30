from typing import Any, Mapping, List, Dict
from loguru import logger

from engines.common.research_graph_runtime import ResearchNode
from engines.contracts.agent_rules import ROLE_INFOS
from engines.contracts.evidence import EvidenceRecord, RetrievalMeta
from engines.insight_agent.state import InsightState


class EvidenceRerankingNode(ResearchNode):
    """
    证据去重合并与重排序节点
    输入state字段：retrieved_records：原始召回证据列表，允许同id多条重复
    输出增量：
        records_by_id: dict[str, EvidenceRecord] 全局证据索引，id映射完整证据对象
        rerank_scores: dict[str, float] 每个文档id对应的融合排序分数
    三大职责：
        1. 根据doc_id合并多路召回重复证据，只合并RetrievalMeta，document本体不变
        2. 融合【召回通道相关性】+【归一化热度】计算统一排序分数
        3. 构建id索引字典，供下游路由、章节准备节点消费

    契约说明：
        records_by_id仅作为索引字典，业务禁止依赖records_by_id.values()的遍历顺序；
        如果需要有序证据列表，需要基于rerank_scores重新排序。
    """

    async def __call__(self, state: InsightState) -> dict[str, Any]: # type: ignore
        role = state["role"]
        role_info = ROLE_INFOS[role]
        logger.info(f"{role_info.agent_name} 开始执行证据去重合并、重排序")

        # 获取所有证据信息,没有去重复的信息
        retrieved_records:List[EvidenceRecord] = state.get("retrieved_records", [])

        # 1、按doc_id合并重复证据
        # 根据doc_id去重复, 重复 合并 meta
        merged_records:List[EvidenceRecord] = _dedupe_and_merge(retrieved_records)

        # 2、计算每条证据融合排序分数
        rerank_scores:dict[str, float] = _calculate_rerank_scores(merged_records)

        # 3、按照融合分数降序排序证据列表
        #  集合.sort(key=lambda)
        #  sorted(排序的数据,key=)
        sorted_records = sorted(
            merged_records,
            key=lambda r: rerank_scores.get(r.id, 0.0),
            reverse=True
        )
        # 4、构建全局id证据索引字典
        records_by_id = {rec.id: rec for rec in sorted_records}

        logger.info(
            f"{role_info.agent_name} 处理完成：原始召回{len(retrieved_records)}条，去重后{len(merged_records)}条"
        )
        return {
            "records_by_id": records_by_id,
            "rerank_scores": rerank_scores
        }

def _dedupe_and_merge(retrieved_records: List[EvidenceRecord]) -> list[EvidenceRecord]:
    """
    根据证据id(doc_id)合并多路召回重复的EvidenceRecord
    规则：document本体保留不变；只合并RetrievalMeta元数据
        matched_queries：列表拼接+set去重
        channel_scores：同一通道多次命中取该通道最大值，避免后序记录直接覆盖分数
    """

    # 掌柜智库  node_rrf  dict
    id_map: dict[str, EvidenceRecord] = {}

    for record in retrieved_records:
        rid = record.id
        if rid not in id_map:
            id_map[rid] = record
            # 没记录过,不重复! 跳过本次循环!
            continue

        # 同一个id，代表同一篇帖子，执行元数据合并
        # 老
        exist_record:EvidenceRecord = id_map[rid]
        exist_meta:RetrievalMeta = exist_record.retrieval

        # 新
        incoming_meta:RetrievalMeta = record.retrieval

        # 合并元数据! 分数值保留一个渠道! 就算mysql db_call查询多次也记录一次分数!
        merged_meta: RetrievalMeta = RetrievalMeta(
            # 不同路 milvus和mysql完整查询的时候可能会重复!
            matched_queries=list(set(exist_record.retrieval.matched_queries + incoming_meta.matched_queries)),
            # 同一路 mysql只保留一次分数
            channel_scores={
                **exist_record.retrieval.channel_scores, **incoming_meta.channel_scores
            }
        )
        new_record = EvidenceRecord(
            document=exist_record.document,
            retrieval=merged_meta
        )
        id_map[rid] = new_record
    return list(id_map.values())

def _calculate_rerank_scores(merged_records: List[EvidenceRecord]) -> dict[str, float]:
    """
    计算融合排序分数：recall_score*0.6 + 批次归一化热度*0.4
    recall_score：db通道0.5，向量通道0.5权重
    """
    score_map: dict[str, float] = {}
    if not merged_records:
        return score_map

    # 获取本批次证据最大热度
    max_hot = max(r.document.hotness_score for r in merged_records)

    for rec in merged_records:
        # 查询的分  mysql + milvus
        recall_score = _calc_recall_channel_score(rec)
        # 批次热度归一化，防止除零
        if max_hot > 0:
            norm_hot = rec.document.hotness_score / max_hot
        else:
            norm_hot = 0.0
        final = recall_score * 0.6 + norm_hot * 0.4
        score_map[rec.id] = final
    return score_map

def _calc_recall_channel_score(record: EvidenceRecord) -> float:
    """
    计算召回相关性分数
    db_call权重0.5，semantic_recall权重0.5；双通道同时命中最高1.0，单通道最高0.5；
    """
    cs = record.retrieval.channel_scores
    db_s = cs.get("db_call", 0.0)
    vec_s = cs.get("semantic_recall", 0.0)
    return db_s * 0.5 + vec_s * 0.5

async def run_evidence_reranking_node_real():
    """
    真实链路测试：
    1. 先执行证据检索节点拿到原始retrieved_records
    2. 送入EvidenceRerankingNode执行去重合并打分
    3. 打印统计信息，观察合并效果、分数
    """
    from engines.insight_agent.nodes.evidence_retrieval_node import EvidenceRetrievalNode

    input_state: InsightState = {
        "query": "校园安全事件",
        "role": "insight"
    } # type: ignore

    print("===== EvidenceRerankingNode 真实环境测试 =====")
    # 第一步：执行上游检索节点，拿到原始召回
    retrieve_node = EvidenceRetrievalNode(context=None) # type: ignore
    retrieve_inc = await retrieve_node(input_state)
    retrieved_records = retrieve_inc["retrieved_records"]
    print(f"原始召回条数: {len(retrieved_records)}")

    # 第二步：执行本重排节点
    rerank_node = EvidenceRerankingNode(context=None) # type: ignore
    rerank_inc = await rerank_node({**input_state, **retrieve_inc}) # type: ignore

    records_by_id = rerank_inc["records_by_id"]
    rerank_scores = rerank_inc["rerank_scores"]

    print(f"去重合并之后条数: {len(records_by_id)}")
    print(f"原始条数 / 去重之后条数 = {len(retrieved_records)} / {len(records_by_id)}")
    print("-"*70)

    # 打印前5条合并之后证据，查看元数据与融合分数
    show_cnt = 5
    for idx, (doc_id, rec) in enumerate(list(records_by_id.items())[:show_cnt]):
        print(f"\n【{idx+1}】doc_id={doc_id}")
        print(f"命中检索词 matched_queries: {rec.retrieval.matched_queries}")
        print(f"通道分数 channel_scores: {rec.retrieval.channel_scores}")
        print(f"热度分数 hotness_scores: {rec.document.hotness_score}")
        print(f"融合排序分 rerank_score: {rerank_scores[doc_id]:.4f}")
        print(f"帖子片段: {rec.document.content[:100]}...")

    print("\n=====测试结束 =====")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_evidence_reranking_node_real())