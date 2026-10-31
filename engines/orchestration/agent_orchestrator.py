from pathlib import Path
from typing import Callable, Awaitable

from engines.common.llm import LLMClient
from engines.common.research_graph_runtime import ProgressUpdate
from engines.common.research_tasks import research_task_manager
from engines.common.reports import get_output_dir
from engines.contracts.agent_rules import ROLE_KEY
from engines.insight_agent.agent import invoke_insight_agent
from engines.media_agent.agent import invoke_media_agent
from engines.common.logger import route_logs_by_role
from loguru import logger
from engines.common.events import (
    RoleErrorEvent,
    publish_role_error,
    publish_role_result,
    RoleResultEvent,
    publish_role_progress, RoleProgressEvent
)

# 代表一个agent-handler函数
# Callable[[入参类型列表], 返回值类型]：Python typing 用来描述函数类型。
AgentHandler = Callable[
    [
        str, # task_id
        str, # query
        str, # role
        LLMClient, # 模型对象
        str,   # 输出目标
        Awaitable | None  # 异步的回到函数,参数不确定! 后续用于返回进度 progress_callback 进度回调
    ] , # 参数 每个AGENT参数
    Awaitable[None]
]

# Awaitable[None] -> 调用的agent异步没有返回值函数 -> 这是一个可等待对象（协程）；当你 await 这个对象 执行完毕之后，最终函数返回 None。

class ResearchAgentOrchestrator:

    def __init__(self):
        # Agent映射表：RoleKey → AgentHandler异步函数
        # 新增智能体：只需要实现符合AgentHandler签名的入口函数，在这里增加一条映射，编排器主体无需改动
        self._agent_handlers : dict[ROLE_KEY,AgentHandler] = { # type: ignore
            "insight": invoke_insight_agent,
            "media": invoke_media_agent
        }

    def dispatch_tasks(self, task_id: str, query: str) -> None:
        """
        分派任务：遍历所有注册Agent，构造协程对象，提交后台并发执行。

        重要特性：本函数是同步函数，**不会阻塞当前HTTP请求**；
        协程对象只是被打包，由research_task_manager.submit_task交给asyncio.create_task放到事件循环后台运行；
        HTTP接口拿到task_id可以立刻返回给前端，不需要等待Agent大模型、检索耗时逻辑执行完毕。

        :param task_id: 全局唯一任务UUID
        :param query: 用户提交的舆情研究主题/查询
        """

        for role in self._agent_handlers:
            task_coroutine = self._execute_research_task(task_id, role, query)
            research_task_manager.submit_task(task_coroutine)


    async def _execute_research_task(self, task_id: str, role: ROLE_KEY, query: str) -> None:
        """
        【Agent执行切面层】单个角色Agent完整执行流程
        本层职责（统一横切逻辑，避免每个Agent复制粘贴重复样板）：
        1. 进入角色专属日志上下文 router_log_by_role(role)，日志自动分流到对应角色日志文件；
        2. 根据角色role读取配置，构造对应角色LLMClient实例；
        3. 调用公共工具 get_output_dir 获取该Agent专属产物输出目录；
        4. 调用真正Agent业务入口invoke_xxx_agent，将output_dir路径传递给Agent；
        5. 全局捕获单个Agent内部全部异常；**一个Agent失败，不影响另外一个Agent运行，不崩整个事件循环**。

        本切面层不做：
            - 文件IO落盘（save_report交给Agent业务层，common.reports提供工具）
            - 业务检索、Prompt组装、LLM调用、报告生成；全部下沉各个Agent内部。

        :param task_id: 全局任务id
        :param role: 当前要执行的智能体角色 insight / media
        :param query: 用户原始研究query
        """
        with route_logs_by_role(role):
            # ---------- 任务刚启动，发送第一条进度事件 starting 0% ----------
            self._publish_progress(
                task_id,
                role,
                ProgressUpdate(status="starting", message="开始执行研究", progress_pct=0)
            )

            try:
                # 构造llm_client
                llm = LLMClient.from_role(role)
                # 获取输出路径
                output_dir = get_output_dir(task_id, role)
                # 调用agent
                logger.info(f"{role}开始执行")
                agent = self._agent_handlers[role]
                # 拆分语法：lambda update: self._publish_progress(task_id, role, update)
                #    lambda：python 匿名函数关键字；
                #    update：是这个匿名函数的【形参变量名】！！
                #    名字叫update，完全是自定义起名，你改成xxx、pu都可以，只是变量名；
                #    但是！调用这个 lambda 的时候，会把一个ProgressUpdate对象赋值给这个形参update。
                #    :冒号后面：是这个 lambda 函数的函数体；
                #    python
                #    self._publish_progress(task_id, role, update)
                #    调用静态方法_publish_progress，传 3 个实参：
                #    task_id：来自外层 orchestrator 当前局部变量（闭包捕获）
                #    role：来自外层 orchestrator 当前局部变量（闭包捕获）
                #    update：就是 lambda 收到的那个入参，也就是 runtime 传过来的 ProgressUpdate 对象
                await agent(task_id, query, role, llm, output_dir, lambda update: self._publish_progress(task_id, role, update)) # type: ignore
                logger.info(f"{role}执行完毕")
                publish_role_result(RoleResultEvent(task_id=task_id, role=role))
            except Exception as e:
                logger.exception(f"{role}执行错误: {e}")
                publish_role_error(
                    RoleErrorEvent(task_id=task_id, role=role, error=str(exec))
                )
                raise e

    @staticmethod
    def _publish_progress(
            task_id: str, role: ROLE_KEY, update: ProgressUpdate
    ) -> None:
        """发布指定研究角色的进度事件。
        【ROLE_PROGRESS事件唯一收敛出口】
        所有Agent Graph内部各个node上报的进度，全部回调到这里；
        入参：ProgressUpdate（来自research_graph_runtime运行时封装）
        动作：组装强类型RoleProgressEvent pydantic对象 → 调用publish_role_progress，投递事件总线。

        注意：ProgressUpdate里面只有status/message/progress_pct；**不存在section_key**；
        如果需要携带结构化章节，需要扩展ProgressUpdate结构，再同步扩展RoleProgressEvent模型；当前版本不做。
        """
        publish_role_progress(
            RoleProgressEvent(
                task_id=task_id,
                role=role,
                status=update.status,
                message=update.message,
                progress_pct=update.progress_pct
            )
        )
