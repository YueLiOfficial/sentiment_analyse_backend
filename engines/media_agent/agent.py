import asyncio
from typing import Optional
from engines.common.llm import LLMClient
from engines.common.reports import save_report


async def invoke_media_agent(
        run_id: str,
        query: str,
        role: str,
        llm_client: LLMClient,
        output_dir: str,
        progress_callback: Optional = None # type: ignore
) -> None:
    """
    Media智能体：公域网络数据检索
    统一AgentHandler入口，编排器会调用该函数

    :param run_id: 全局任务task_id
    :param query: 用户原始研究query
    :param role: 角色key media
    :param llm_client: media角色模型客户端实例
    :param output_dir: 该角色产物目录，RUNTIME_DIR/{task_id}/media
    :param progress_callback: 进度上报回调（预留，当前demo暂不使用）
    """

    # ========== 模拟业务：模拟公域搜索、大模型分析耗时，实际业务删除sleep ==========
    await asyncio.sleep(3.0)

    # 【可选：打开下面代码模拟Agent异常，测试results接口key缺失场景】
    # raise RuntimeError("模拟MediaAgent执行异常，不会生成report.md")

    # 模拟生成公域分析markdown报告
    demo_md = f"""# 公域检索分析报告【模拟占位】
    > task_id: `{run_id}`
    > 研究主题：**{query}**
    > 角色：{role}

    ## 1. 公域证据概览
    - 模拟调用外部搜索API抓取网页、新闻资讯
    - 模拟获取18条公域相关网页证据

    ## 2. 维度分析
    1. 全网舆情走势：模拟公域媒体舆情统计
    2. 重点媒体观点汇总：模拟主流媒体立场梳理
    3. 热点事件溯源：模拟公域事件时间线还原

    > 注意：本文件为Demo模拟产物；后续接入真实检索与LLM之后替换全部内容。
    """
    # 调用公共IO工具，写入report.md到output_dir
    save_report(
        output_dir=output_dir,
        filename="report.md",
        content=demo_md
    )