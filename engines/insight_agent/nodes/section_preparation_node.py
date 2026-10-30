from typing import Any, Mapping

from loguru import logger

from engines.common.research_graph_runtime import ResearchNode
from engines.contracts.agent_rules import ROLE_INFOS
from engines.contracts.evidence import EvidenceRecord
from engines.contracts.research_graph_state import SectionState
from engines.contracts.section_definitions import SECTION_DEFINITIONS
from engines.insight_agent.state import InsightState


class SectionPreparationNode(ResearchNode):
    """
    章节预处理节点：初始化固定章节元数据，并为每个章节筛选、排序、截断证据。

    输入state依赖字段：
        records_by_id: dict[str, EvidenceRecord]
            全部证据ID -> 完整证据对象
        section_record_ids: dict[str, list[str]]
            上一步路由节点输出：章节key → 证据id列表
        rerank_scores: dict[str, float]
            证据id → 融合重排分数，分数越高优先级越高

    输出增量（两个列表严格下标一一对应）：
        sections: list[SectionState]
            每一章的元数据：section_key、title中文标题
        section_evidence_records: list[list[EvidenceRecord]]
            下标和sections一一对应；每个章节最多保留20条证据，按融合分数降序
    """

    async def __call__(self, state: InsightState) -> dict[str, Any]: # type: ignore
        """生成固定章节状态及供摘要节点消费的章节证据列表。"""
        role = state['role']
        role_info = ROLE_INFOS[role]
        logger.info(f"{role_info.agent_name} 开始初始化固定章节并为各章节选择、排序和截取证据。")

        # 从Graph状态取出上游输出
        # {doc_id : EvidenceRecord}
        records_by_id: Mapping[str, EvidenceRecord] = state["records_by_id"]
        # {section_key : [doc_id, ...]}
        section_record_ids: Mapping[str, list[str]] = state["section_record_ids"]
        # {doc_id : rerank_score}
        rerank_scores: Mapping[str, float] = state["rerank_scores"]

        sections: list[SectionState] = []
        # [] [] [证据列表]
        section_evidence_records: list[list[EvidenceRecord]] = []

        # 遍历全局定义全部章节；循环顺序 = 报告最终输出章节顺序
        for definition in SECTION_DEFINITIONS.values():
            # 组装章节基础元数据 key + 中文标题
            sections.append(
                {
                    "section_key": definition.key,
                    "title": definition.title,
                }
            )
            # 获取章节证据对象，按分数降序，最多取20条

            chapter_records = _select_section_records(
                definition.key,
                records_by_id,
                section_record_ids,
                rerank_scores,
            )[:20]
            section_evidence_records.append(chapter_records)

        logger.info(
            f"{role_info.agent_name} 初始化章节完成，总章节数:{len(sections)}，"
            f"各章节证据数量：{[len(x) for x in section_evidence_records]}"
        )

        return {
            "sections": sections,  # [SectionState(title,key,body),]
            "section_evidence_records": section_evidence_records, # [[ EvidenceRecord, ... 20], [EvidenceRecord, ...],[]]
        }


def _select_section_records(
    section_key: str,
    records_by_id: Mapping[str, EvidenceRecord],
    section_record_ids: Mapping[str, list[str]],
    rerank_scores: Mapping[str, float],
) -> list[EvidenceRecord]:
    """
    按章节键筛选证据，将id还原为完整EvidenceRecord对象，按融合重排分数降序排列。

    :param section_key: 章节唯一key，如 background_overview
    :param records_by_id: 证据id ->完整证据对象 全量映射
    :param section_record_ids: 章节 → 证据id列表（上一步路由输出）
    :param rerank_scores: 证据id →融合排序分数，分数越高越靠前
    """
    # 取不到章节返回空列表，防止None迭代报错
    # [doc_id,...]
    record_id_list = section_record_ids.get(section_key, [])

    # ID还原完整证据对象
    # [EvidenceRecord,...]
    matched_records = [
        records_by_id[record_id]
        for record_id in record_id_list
    ]

    # 缺失分数默认0.0，避免sorted因为None崩溃；reverse=True降序
    return sorted(
        matched_records,
        key=lambda record: rerank_scores.get(record.id, 0.0),
        reverse=True,
    )