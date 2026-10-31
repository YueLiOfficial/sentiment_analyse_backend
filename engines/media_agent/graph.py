# engines/media_agent/graph.py
"""
公域MediaAgent LangGraph图构建build_graph
链路：
START → plan_search（搜索规划）
→ search（网页检索执行节点，待实现）
→ summarize_sections（公域摘要子类游标循环）
        ↶条件路由（复用私域route_after_section_summary）
→ generate_agent_report（复用私域报告汇总）
→ persist_agent_report（复用私域报告持久化）
→ END
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
from engines.media_agent.nodes.section_search_node import SearchNode
from engines.media_agent.nodes.section_summary_node import SectionSummaryNode
from engines.media_agent.nodes.search_planning_node import SearchPlanningNode
from engines.media_agent.state import MediaAgentState


def build_graph(ctx: ResearchRunContext) -> Any:
    """
    构造并编译公域研究智能体完整Graph
    :param ctx: ResearchRunContext 单次任务运行上下文；每个节点实例注入context；不可序列化，禁止放入state
    :return: 编译完成的langgraph可执行图对象
    """
    graph = StateGraph(MediaAgentState)

    # 实例化全部业务节点，统一注入运行上下文context
    graph.add_node("plan_search", SearchPlanningNode(ctx))
    graph.add_node("search", SearchNode(ctx))
    graph.add_node("summarize_sections", SectionSummaryNode(ctx))
    graph.add_node("generate_agent_report", AgentReportGenerationNode(ctx))
    graph.add_node("persist_agent_report", ReportPersistenceNode(ctx))

    # 直线基础链路
    graph.add_edge(START, "plan_search")
    graph.add_edge("plan_search", "search")
    graph.add_edge("search", "summarize_sections")

    #游标循环条件路由：【完全复用私域公共路由函数+映射表】，不重复开发
    graph.add_conditional_edges(
        source="summarize_sections",
        path=route_after_section_summary,
        path_map=SECTION_SUMMARY_LOOP_MAPPING,
    )

    graph.add_edge("generate_agent_report", "persist_agent_report")
    graph.add_edge("persist_agent_report", END)

    return graph.compile()