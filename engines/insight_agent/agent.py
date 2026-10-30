"""
私域舆情Agent对外调用入口
文件：engines/insight_agent/agent.py

## 设计原则：入口层轻量化，业务逻辑全部下沉Graph节点；入口不实现任何业务逻辑
1. 接收外部调用方传入参数：task_id、用户query、role角色、llm客户端、输出根目录、进度回调callback；
2. 组装本次任务运行时上下文 ResearchRunContext（运行时对象，不序列化，不写入state）；
3. 调用build_graph(ctx)，构建编译完成的LangGraph图；
4. 调用公共通用执行器 run_research_graph，把ctx、编译后的graph、原始query传入；
> 初始state字典**不在本入口手动拼装**；初始state由公共run_research_graph统一构造；
> 初始state最小集合：
> {
>    "run_id": context.run_id,
>    "query": query,
>    "role": context.role,
> }
> 其余state字段（retrieved_records、records_by_id、sections、cursor、final_report等）全部由Graph各个节点逐步增量产出。

## 入参说明
- task_id：外部业务系统分配的任务唯一ID；用于目录命名、日志、快照命名
- query：用户原始舆情研究查询
- role：RoleKey枚举，这里固定为insight；本入口是私域Agent入口
- llm_client：全局统一大模型客户端实例；注入context，所有节点从context获取，节点不自己新建llm连接
- output_dir：任务输出根目录；每个task会在下面新建task_id子目录，存放report.md、evidence.json
- progress_callback：进度回调；Graph内部各节点通过context调用，向上推送进度字符串、百分比；可为None

## 返回
协程async函数；无返回值；全部输出产物写磁盘；异常会向上抛出，由上层调用方捕获处理。
"""
from engines.common.llm import LLMClient
from engines.common.research_graph_runtime import (
    ProgressCallback,
    ResearchRunContext,
    handle_research_graph,
)
from engines.contracts.agent_rules import ROLE_KEY
from engines.insight_agent.graph import build_graph

async def insight_agent_handler(
    task_id: str,
    query: str,
    role: ROLE_KEY,
    llm_client: LLMClient,
    output_dir: str,
    progress_callback: ProgressCallback | None = None,
) -> None:
    """
    私域舆情分析Agent对外入口函数。
    :param task_id: 业务侧任务唯一id
    :param query: 用户原始舆情研究query
    :param role: Agent角色枚举；私域入口调用传入RoleKey.INSIGHT
    :param llm_client: 大模型客户端实例；注入上下文，节点统一从context访问
    :param output_dir: 文件输出根目录；每个任务会创建 {output_dir}/{task_id}/ 子目录
    :param progress_callback: 可选进度回调；节点内部上报进度使用；None代表不需要进度推送
    :return: None；分析产物全部输出到磁盘；异常向上抛出，上层调用方捕获
    """
    # Step1：组装单次任务运行时上下文；聚合全部运行期依赖；不做序列化，不写入state
    context = ResearchRunContext(
        task_id=task_id,
        role=role,
        llm_client=llm_client,
        output_dir=output_dir,
        progress_callback=progress_callback,
    )

    # Step2：传入上下文，构建并编译完整私域Agent LangGraph工作流
    compiled_graph = build_graph(context)

    # Step3：调用公共通用执行器；统一负责初始化state、invoke执行、快照、异常处理
    # 注意：初始state字典不在本入口手动组装；交给公共run_research_graph内部统一生成最小初始state
    await handle_research_graph(
        context=context,
        graph=compiled_graph,
        query=query,
    )
