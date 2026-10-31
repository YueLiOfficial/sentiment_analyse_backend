# engines/media_agent/state.py
"""
media_agent/state.py
公域MediaAgent LangGraph全局状态定义【业务流程层，和web_search平级】
继承关系：
    SectionState（公私域公共契约） → MediaSectionState（公域扩展）
    ResearchGraphState → MediaAgentState（公域全局Graph状态）

铁律：sections / section_evidence_records / section_queries 三者列表下标严格一一对应。
导入：仅从web_search.__init__导出导入SearchTool，**不导入web_search内部模型WebpageResult**。
"""
from typing import NotRequired, TypedDict

from engines.contracts.evidence import EvidenceRecord
from engines.contracts.research_graph_state import ResearchGraphState, SectionState
from engines.media_agent.web_search.search_results import SearchTool


class MediaSectionState(SectionState):
    """
    公域单章节状态：继承公共SectionState，扩展公域搜索规划产出字段
    继承来自SectionState基础字段：
        section_key: str
        title: str
        body: str | None
    公域扩展字段（SearchPlanningNode节点输出填充）：
        search_tool: SearchTool          本章节选定的搜索策略枚举
        search_keywords: list[str]       本章节1‑3条补充搜索关键词（不是完整query）

     章节 -> 数据 ->  model -> 1. 哪个网络搜索策略    search_tool
                             2.  query  +  关键字

    """
    search_tool: NotRequired[SearchTool]
    search_keywords: NotRequired[list[str]]


class MediaAgentState(ResearchGraphState[MediaSectionState], total=False):
    """
    公域智能体全局LangGraph状态
    继承公共ResearchGraphState基础字段：
        task_id: str
        query: str
        role: str
        cursor: NotRequired[int]
        sections: list[MediaSectionState]
        final_report: NotRequired[str]

    公域新增专属状态字段：
    section_evidence_records: list[list[EvidenceRecord]]
        长度=5；下标和sections严格对齐；每一项是该章节检索完成、平衡排序、章内去重后的证据集合。

    section_queries: list[str]
        长度=5；下标对齐sections；
        每一项是多行字符串，记录本章全部实际执行搜索：工具枚举+完整拼接query；
        该字段会在摘要节点覆写钩子 _retrieval_text 注入LLM Prompt，让模型知道本章检索上下文。
        示例字符串：
        "[source_search] 高考 官方通报\n[source_search] 高考 政策调整"
    """
    # 五组章节证据，下标与sections一一对应；每个元素是该章节的一组EvidenceRecord有序证据
    # 章节的证据 [[],[],[],[],[]]
    section_evidence_records: NotRequired[list[list[EvidenceRecord]]]

    # 五组实际执行查询记录；下标对齐sections；存储字符串，记录该章节全部拼接完成的搜索请求，摘要阶段喂给LLM
    # query问题
    # 章节1: 关键字 + query    章节2: 关键字 + query   章节3: 关键字 + query  章节4: 关键字 + query 章节5: 关键字 + query
    section_queries: NotRequired[list[str]]  # query + 关键词 -> 维度 -> 1 - 3 关键词