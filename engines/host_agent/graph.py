from typing import Any

from langgraph.graph import END, START, StateGraph

from engines.host_agent.nodes import HostNodes
from engines.host_agent.section_judge import HostSectionJudge
from engines.host_agent.state import HostState


def build_graph(section_judge: HostSectionJudge) -> Any:
    """
    Host研判图工厂函数
    :param section_judge: 研判器实例，支持传入mock对象用于单元测试
    :return: 编译完成的LangGraph可执行实例
    """
    # 实例化节点类，注入研判器
    nodes = HostNodes(section_judge)
    graph = StateGraph(HostState)

    # 注册业务节点
    graph.add_node("collect_agent_output", nodes.collect_agent_output)
    graph.add_node("generate_section_judgement", nodes.generate_section_judgement)
    graph.add_node("apply_section_judgement", nodes.apply_section_judgement)
    graph.add_node("save_judgements", nodes.save_judgements)

    # 起始边：启动后先收集章节输出
    graph.add_edge(START, "collect_agent_output")

    # 条件路由1：收集输出完毕，判断是否存在就绪待研判配对
    graph.add_conditional_edges(
        "collect_agent_output",
        _route_after_output_collection,
        {
            "ready": "generate_section_judgement",  # 配对就绪，进入LLM研判
            "waiting": END,                         # 无就绪配对，直接结束
        },
    )

    # 研判生成完成，流转到apply应用研判结果
    graph.add_edge("generate_section_judgement", "apply_section_judgement")

    # 条件路由2：apply执行完毕，判断是否全部章节研判完成
    graph.add_conditional_edges(
        "apply_section_judgement",
        _route_after_judgement,
        {
            "save": "save_judgements",  # 全部章节完成，执行磁盘持久化
            "waiting": END,             # 尚有章节未完成，直接结束
        },
    )

    # 持久化节点执行完毕，结束图流程
    graph.add_edge("save_judgements", END)

    return graph.compile()


def _route_after_output_collection(state: HostState) -> str:
    """
    collect_agent_output之后的条件路由
    直接调用store的API做业务判断，不手写重复业务逻辑
    """
    if state["section_pair_store"].has_ready_pair(): # type: ignore
        return "ready"
    return "waiting"


def _route_after_judgement(state: HostState) -> str:
    """
    apply_section_judgement之后的条件路由
    直接调用store的API做业务判断，不手写重复业务逻辑
    """
    if state["section_pair_store"].all_sections_judged(): # type: ignore
        return "save"
    return "waiting"