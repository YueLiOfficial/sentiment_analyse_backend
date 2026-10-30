"""
私域舆情Agent LangGraph图构建
文件：engines/insight_agent/graph.py

## 整体流程
START
    → retrieve_evidence          # 1 双通道原始证据召回
    → rerank_evidence            # 2 doc_id去重合并、证据过滤、业务重排打分
    → route_section_evidence     # 3 证据按规则路由分配到各个章节，产出章节‑doc_id映射
    → prepare_sections           # 4 初始化5章节骨架、组装分章证据子集、cursor=0
    → summarize_sections         # 5 循环体：生成cursor指向的单章正文；cursor +=1
        ↓（条件边route_after_section_summary）
        ├─ next_section → summarize_sections （还有章节未完成，继续循环）
        └─ all_done → generate_agent_report （全部章节完成，跳出循环）
    → generate_agent_report      # 6 按固定顺序拼接完整markdown报告
    → persist_agent_report       # 7 report.md + evidence.json落盘
    → END

## 架构自检清单（写代码前后逐条核对）
[ ] 所有节点文件全部存在，类定义齐全
[ ] 公共节点（报告生成、落盘）来自common包，不在insight_agent重复拷贝
[ ] state字段数据流闭环：每一个节点输入字段，确认是上游节点输出字段；不存在未定义字段
[ ] 依赖方向正确：节点依赖state，节点不互相直接import调用；全部通过state解耦
[ ] 循环存在出口：条件边存在all_done分支，不会死循环
[ ] 条件边不是普通边；章节循环使用add_conditional_edges
[ ] 节点实例化全部传入ctx；不使用lambda闭包捕获上下文，规避延迟绑定
[ ] SearchResult / SearchHit仓储私有对象，不流入Graph层；Graph只操作EvidenceRecord
[ ] 区分三类对象：ResearchRunContext（运行时，不进state）、InsightState（可序列化业务状态）、SectionDefinition（静态配置，不进state）
"""
from typing import Any

from langgraph.graph import END, START, StateGraph

from engines.common.agent_report_generation_node import AgentReportGenerationNode
from engines.common.report_persistence_node import ReportPersistenceNode
from engines.common.research_graph_runtime import (
    SECTION_SUMMARY_LOOP_MAPPING,
    ResearchRunContext,
    route_after_section_summary,
)
from engines.insight_agent.nodes.evidence_reranking_node import EvidenceRerankingNode
from engines.insight_agent.nodes.evidence_retrieval_node import EvidenceRetrievalNode
from engines.insight_agent.nodes.section_evidence_routing_node import (
    SectionEvidenceRoutingNode,
)
from engines.insight_agent.nodes.section_preparation_node import SectionPreparationNode
from engines.insight_agent.nodes.section_summary_node import SectionSummaryNode
from engines.insight_agent.state import InsightState


def build_graph(ctx: ResearchRunContext) -> Any:
    """
    构建并编译私域舆情智能体的 LangGraph 工作流。
    :param ctx: 单次任务运行时上下文（llm_client、task_id、role、output_dir、progress_callback），**不可序列化，不写入state**
    :return: CompiledGraph，编译完成可直接执行的图实例
    """
    # 1. 创建StateGraph，绑定私域Agent完整状态InsightState
    builder = StateGraph(InsightState)

    # 2. 实例化全部节点；所有节点构造传入同一个运行时上下文ctx；禁止lambda闭包捕获ctx
    builder.add_node("retrieve_evidence", EvidenceRetrievalNode(ctx))
    builder.add_node("rerank_evidence", EvidenceRerankingNode(ctx))
    builder.add_node("route_section_evidence", SectionEvidenceRoutingNode(ctx))
    builder.add_node("prepare_sections", SectionPreparationNode(ctx))
    builder.add_node("summarize_sections", SectionSummaryNode(ctx)) # type: ignore
    builder.add_node("generate_agent_report", AgentReportGenerationNode(ctx))
    builder.add_node("persist_agent_report", ReportPersistenceNode(ctx))

    # 3. 线性主流程边
    builder.set_entry_point("retrieve_evidence")
    builder.add_edge("retrieve_evidence", "rerank_evidence")
    builder.add_edge("rerank_evidence", "route_section_evidence")
    builder.add_edge("route_section_evidence", "prepare_sections")
    builder.add_edge("prepare_sections", "summarize_sections")

    # 4. 进入章节循环：prepare_sections → summarize_sections循环体

    # 核心：章节摘要节点输出后，走【条件边】；公共路由函数route_after_section_summary判断cursor
    # 返回next_section 继续回到summarize_sections；返回all_done跳出循环进入报告生成
    builder.add_conditional_edges(
        "summarize_sections",
        route_after_section_summary,
        SECTION_SUMMARY_LOOP_MAPPING # type: ignore
    )

    # 5. 循环结束之后：报告汇总 → 持久化 → END
    builder.add_edge("generate_agent_report", "persist_agent_report")
    builder.add_edge("persist_agent_report", END)

    # 6. 编译Graph；返回编译后的可执行对象，交给公共run_research_graph执行
    compiled_graph = builder.compile()
    return compiled_graph
