# engines/media_agent/agent.py
"""
公域MediaAgent对外入口handler
对齐私域invoke_insight_agent；组装context，build_graph，调用公共handle_research_graph驱动图执行。
"""
import asyncio

from engines.common.llm import LLMClient
from engines.common.reports import get_output_dir
from engines.common.research_graph_runtime import ResearchRunContext, ProgressCallback, handle_research_graph
from engines.contracts.agent_rules import ROLE_KEY
from engines.media_agent.graph import build_graph


async def invoke_media_agent(
        task_id: str,
        query: str,
        role: ROLE_KEY,
        llm_client: LLMClient,
        output_dir: str,
        progress_callback: ProgressCallback | None = None
):
    """
    公域舆情智能体统一对外调用入口
    :param role: 角色标识，固定media
    :param query: 用户研究分析主题
    :param task_id: 任务全局唯一ID
    :param llm_client: 已经实例化完成的media角色LLM客户端
    :param output_dir: 当前任务报告输出目录
    :param progress_callback: 进度回调，上层业务可传入接收实时进度；可以为None
    """
    # 构造不可序列化运行上下文，注入给Graph全部节点；禁止存入LangGraph State
    context = ResearchRunContext(
        task_id=task_id,
        role=role,
        llm_client=llm_client,
        output_dir=output_dir,
        progress_callback=progress_callback,
    )
    # build_graph传入context，实例化全部业务节点；调用公共统一执行入口
    await handle_research_graph(context, build_graph(context), query)


async def main_test():
    """本地main调试入口，直接运行完整公域链路；真实调用LLM、真实调用Anspire搜索"""
    await invoke_media_agent(
        role="media",
        query="宁德时代为啥这么跌?",
        task_id="media‑demo‑001",
        llm_client=LLMClient.from_role("media"),
        output_dir=get_output_dir(task_id="media‑demo‑001", role="media"),
        progress_callback=None
    )


if __name__ == '__main__':
    asyncio.run(main_test())