import asyncio
from typing import Optional
from engines.common.llm import LLMClient
from engines.common.reports import save_report


async def invoke_insight_agent(
        run_id: str,
        query: str,
        role: str,
        llm_client: LLMClient,
        output_dir: str,
        progress_callback: Optional = None # type: ignore
) -> None:
    """
    Insight智能体：私域数据分析
    统一AgentHandler入口，编排器会调用该函数
    :param run_id: 全局任务task_id
    :param query: 用户原始研究query
    :param role: 角色key insight
    :param llm_client: insight角色模型客户端实例
    :param output_dir: 该角色产物目录，RUNTIME_DIR/{task_id}/insight
    :param progress_callback: 进度上报回调（预留，当前demo暂不使用）
    """

    # ========== 模拟业务：模拟私域数据检索、大模型分析耗时，实际业务删除sleep ==========
    await asyncio.sleep(2.0)

    # 【可选：打开下面代码模拟Agent异常，测试results接口key缺失场景】
    # raise RuntimeError("模拟InsightAgent执行异常，不会生成report.md")

    # 模拟生成私域分析markdown报告
    demo_md = f"""# 私域检索分析报告【模拟占位】
    > task_id: `{run_id}`
    > 研究主题：**{query}**
    > 角色：{role}

    ## 1. 私域证据概览
    - 模拟从MySQL/Milvus拉取私域UGC证据
    - 共模拟获取12条相关证据

    ## 2. 维度分析
    1. 舆情整体态势：模拟私域舆情研判结果
    2. 风险点：模拟识别到若干风险言论
    3. 传播路径：模拟私域社群传播链路分析

    > 注意：本文件为Demo模拟产物；后续接入真实检索与LLM之后替换全部内容。
    """
    # 调用公共IO工具，写入report.md到output_dir
    save_report(
        output_dir=output_dir,
        filename="report.md",
        content=demo_md
    )