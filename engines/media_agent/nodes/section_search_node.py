# engines/media_agent/nodes/section_search_node.py
"""
SearchNode（SectionSearchNode）公域网页检索执行节点【3新增节点#2】
职责：
    1. 消费SearchPlanningNode产出的sections（携带search_tool、search_keywords）；
    2. 拼接完整搜索query；同一章节内多条查询并发调用web_search层MediaRetrievalService；
    3. 执行【章内平衡合并算法】_merge_query_results：查询内分数降序 → zip_longest轮询交织合并 → 章内证据id去重；
    4. 产出：section_evidence_records（分章节证据集合）、section_queries（实际搜索记录字符串，下游摘要注入Prompt）；

核心约束：
1. 并发粒度：**同一章节内部多条query并发；章节之间顺序循环执行，禁止全量所有章节一把并发，防止搜索服务限流/配额耗尽**；
2. 去重范围：**仅做章内证据去重；跨章节允许同一条EvidenceRecord重复出现，不要全局去重**；
3. 铁律：sections / section_evidence_records / section_queries 三者列表下标严格一一对应；
4. 本节点只依赖web_search对外导出的MediaRetrievalService；**严禁直接导入WebpageResult、Anspire客户端等底层内部模型**；
5. 本节点不写章节正文，只产出标准化证据集合、搜索记录。

输入state：MediaAgentState；需要query、sections(已完成搜索规划)
输出增量：{"section_evidence_records": list[list[EvidenceRecord]], "section_queries": list[str]}
"""
import asyncio
from itertools import zip_longest
from typing import Any

from loguru import logger

from engines.common.research_graph_runtime import ResearchNode, ResearchRunContext
from engines.contracts.agent_rules import ROLE_INFOS
from engines.contracts.evidence import EvidenceRecord
from engines.media_agent.state import MediaAgentState, MediaSectionState
from engines.media_agent.web_search.retrieval_service import MediaRetrievalService


class SearchNode(ResearchNode):
    """公域网页检索执行节点：按章节执行搜索，证据标准化、章内平衡合并、产出分章节证据集合"""

    def __init__(self, context: ResearchRunContext) -> None:
        super().__init__(context)
        # 实例化检索编排服务；业务节点唯一允许使用的web_search入口
        self._retrieval_service = MediaRetrievalService()

    async def __call__(self, state: MediaAgentState) -> dict[str, Any]: # type: ignore
        """LangGraph节点统一入口"""
        role = state["role"]
        role_info = ROLE_INFOS[role]
        logger.info(f"【{role_info.agent_name}】网页检索执行节点开始执行")

        research_topic: str = state["query"]
        sections: list[MediaSectionState] = state["sections"]

        # 输出两个核心数组，下标必须与sections严格对齐，长度=5
        # [ [] [] [] [] [] ]
        section_evidence_records: list[list[EvidenceRecord]] = []
        # [ "关键字 + query", "" , "" ,"" ,"" ]
        section_queries: list[str] = []

        # =========章节之间：顺序循环执行（避免全量并发打爆搜索配额）=========
        for section in sections:
            tool = section["search_tool"] # type: ignore
            keywords = section["search_keywords"] # type: ignore
            # 拼接完整检索query：原始研究主题 + 每一条补充关键词
            # 事件背景  tool = 溯源搜索  keywords = ["地点" + 问,"时间" + 问,"事件背景" + 问]
            full_query_list = [f"{research_topic} {kw}".strip() for kw in keywords]

            # =========同一个章节内部：多条查询并发执行 =========
            query_tasks = [
                self._retrieval_service.retrieve_evidence(tool_name=tool, query=full_q)
                for full_q in full_query_list
            ]
            # 每一条query返回 list[EvidenceRecord]
            per_query_evidence_list: list[list[EvidenceRecord]] = await asyncio.gather(*query_tasks)
            # list[list[EvidenceRecord]] -> list[EvidenceRecord] list[EvidenceRecord] list[EvidenceRecord]
            # 执行核心业务算法：章内平衡合并、排序、章内去重
            chapter_final_evidences:list[EvidenceRecord]= _merge_query_results(per_query_evidence_list)

            # 组装本章节实际搜索记录字符串；后续摘要节点会把该字符串注入LLM Prompt
            chapter_query_log = "\n".join(f"[{tool}] {full_q}" for full_q in full_query_list)

            section_evidence_records.append(chapter_final_evidences) # [ [] [] [] ]
            section_queries.append(chapter_query_log) # ["","",""]

        logger.info(f"【{role_info.agent_name}】网页检索全部章节执行完成")
        # LangGraph规范：只返回变更字段，框架合并state
        return {
            "section_evidence_records": section_evidence_records,  # [[],[],[],[],[]]
            "section_queries": section_queries #["","","","","",""]
        }


def _merge_query_results(query_results: list[list[EvidenceRecord]]) -> list[EvidenceRecord]:
    """
    【核心业务：章内平衡合并算法】
    输入：一个章节下，多条并发查询各自返回的证据列表 list[list[EvidenceRecord]]
    输出：经过「查询内降序排序 → 查询间zip_longest轮询交织 → 章内id去重」之后的单章节有序证据列表

    三步流程：
    1. 查询内部排序：每一组query返回的证据，依据web_call渠道分数降序；高分排在本组证据前面；
    2. 查询之间轮询交织：使用zip_longest，依次取每个查询的第1条、第2条...；
       禁止简单sum(list,[])直接拼接；拼接会导致第一条query全部证据霸占列表头部，证据多样性变差；
    3. 章内证据去重：用evidence.id做seen集合；**仅本章节内部去重；跨章节不做去重**。

    >>>示例
    queryA原始无序：[A3(70),A1(90),A2(80)] → 内部排序后 [A1,A2,A3]
    queryB原始无序：[B2(60),B1(95)] → 内部排序后 [B1,B2]
    zip_longest轮询取出顺序：A1 → B1 → A2 → B2 → A3
    如果中间出现重复id，只保留第一次出现的实例。
    """
    seen_ev_id: set[str] = set()
    final_records: list[EvidenceRecord] = []

    # Step1：每个查询内部，基于web_call分数降序排序
    ranked_per_query = [
        sorted(
            records,
            key=lambda ev: ev.retrieval.channel_scores.get("web_call", 0.0),
            reverse=True
        )
        for records in query_results
    ]

    # [ [1,2,3] +  [4,5]  +  [6,7,8,9]]


    # [ 1,4,6,2,5,7,3,8,9]  ->   [:topk]


    # for () in zip(1,2,3)





    # zip(1,2,3) zip以最短的为基准! 碰到就停止!!
    # zip_longest(1,2,3) zip_longest以最长的为基准! 缺少的用None填充
    # Step2：zip_longest轮询交织遍历；zip_longest会填充None，需要过滤
    for record_tuple in zip_longest(*ranked_per_query):
        for one_ev in record_tuple:
            if one_ev is None:
                continue
            ev_id = one_ev.id
            # Step3：章内去重；已经见过的id直接跳过
            if ev_id in seen_ev_id:
                continue
            seen_ev_id.add(ev_id)
            final_records.append(one_ev)

    return final_records