from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from engines.common.llm import LLMClient
from engines.contracts.agent_rules import ROLE_KEY

# 本次不用关注
@dataclass(slots=True)
class ProgressUpdate:
    """
    节点进度更新载荷【数据载体】
    作用：节点调用report_progress()向上层业务推送进度时，封装状态、提示消息、进度百分比
    """
    status: str  # 状态标记，例如 "starting" / "finished"
    message: str  # 人类可读进度提示文本
    progress_pct: int  # 进度百分比 0‑100


ProgressCallback = Callable[[ProgressUpdate], None]


@dataclass(slots=True)
class ResearchRunContext:
    """
    单次 Insight/Media 研究任务运行所需的共享依赖与元数据。
    红线：本类存放【运行时工具资源】，**对象整体不可序列化，严禁写入LangGraph State！**

    生命周期：
        每一次调用agent.run()启动新舆情任务，new一份独立ResearchRunContext；
        Graph构建、实例化每一个Node节点的时候，通过节点__init__(context)构造函数注入；
        节点内部通过 self.context.xxx 访问资源；
        任务执行完毕，graph实例销毁，context随之销毁；**全程不进入LangGraph state字典流转！**
    context中的task_id/role只是给节点运行时快速读取；
    """
    task_id: str  # 当前研究任务唯一ID
    role: ROLE_KEY  # Agent角色: insight / media
    llm_client: LLMClient  # LLM大模型IO客户端实例 不可序列化！禁止进state
    output_dir: str  # 报告输出本地目录路径（运行环境配置字符串，不放state）
    progress_callback: ProgressCallback | None  # 上层传入进度回调函数,函数对象不可序列化！严禁存入state

    def report_progress(self, status: str, message: str, pct: int) -> None:
        """节点统一上报进度；存在回调则推送进度；无回调空执行 / 后续更新"""
        if self.progress_callback:
            self.progress_callback(ProgressUpdate(status, message, pct))
            
            
async def handle_research_graph(
        context: ResearchRunContext,
        graph: Any,
        query: str,
):
    """
    以统一初始状态执行研究 Agent 的 LangGraph。
    Insight、Media两套Agent共用该执行函数，消除重复代码
    - 只构造最小初始state：task_id / query / role
    - 其余全部业务字段，在各个节点运行过程中逐步产出
    :param context: 运行上下文工具包
    :param graph: 已经编译完成的langgraph图对象
    :param query: 用户原始查询问题
    """
    initial_state = {"task_id": context.task_id, "query": query, "role": context.role}
    await graph.ainvoke(initial_state)


def route_after_section_summary(state: dict[str, Any]) -> str:
    """
    按游标判断继续下一章节摘要或全部完成。
    公共同步路由函数，**不是业务节点**，两套Agent直接复用
    逻辑：读取state中的cursor游标与sections章节列表
        cursor < len(sections) → 返回 "next_section"：继续循环，写下一个章节
        cursor >= len(sections) → 返回 "all_done"：全部章节完成，退出循环进入报告生成
    :param state: graph状态字典，读取cursor、sections字段
    :return: 字符串key，匹配SECTION_SUMMARY_LOOP_MAPPING映射表
    """
    cursor = state.get("cursor", 0)
    sections = state.get("sections")
    return "next_section" if cursor < len(sections) else "all_done" # type: ignore


SECTION_SUMMARY_LOOP_MAPPING = {
    "next_section": "summarize_sections",
    "all_done": "generate_agent_report",
}

class ResearchNode(ABC):
    """
    研究 Agent 图节点抽象基类。
    所有LangGraph业务节点（检索/重排/路由/摘要/报告生成/持久化）必须继承该基类

    选择【可调用类实例】而不是普通async函数节点，解决4个工程痛点：
    1. 规避循环构建graph时lambda闭包延迟绑定bug：
    实例__init__立刻绑定变量存入self，不会出现变量串值。
    2. ABC抽象约束，IDE编码阶段校验节点签名；普通函数只有运行时报错。
    3. __init__一次性初始化service/模型，实例持有资源，多次任务复用，无全局变量，并发安全。
    4. 业务语义清晰：节点是独立处理单元，self挂载自己的上下文、依赖服务。

    强制两条编码规约：
    ① 所有业务节点构造函数签名：def __init__(self, context: ResearchRunContext)；保存self.context；可以在__init__实例化内部service、加载静态配置；不要在__call__里面做重量级初始化；
    ② 必须实现抽象方法：async def __call__(self, state: dict[str, Any]) -> dict[str, Any]
        - 入参state：LangGraph流转完整state字典；节点只读自己需要的key；
        - 禁止原地修改入参state里面的list/dict可变对象！会导致LangGraph增量合并失效！【高频坑】
        - 返回值：**只返回发生变更字段的增量字典，不要返回完整state大对象！LangGraph自动把返回dict合并到全局state**
    """
    def __init__(self, context: ResearchRunContext) -> None:
        self.context = context

    @abstractmethod
    async def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        节点执行入口。
        :param state: LangGraph流转的状态字典（传送带，业务数据）
        :return: dict，仅返回变更字段增量字典，不要返回完整state
        """
        ...