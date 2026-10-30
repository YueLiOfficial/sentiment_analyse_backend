from typing import Generic, TypeVar
from typing_extensions import NotRequired, TypedDict
from engines.contracts.agent_rules import ROLE_KEY

# media/insight -> media -> 网络检索 -> 属性扩展
class SectionState(TypedDict):
    """
    【运行时章节状态】极度容易混淆：区分静态SectionDefinition配置！！

    section_key: str，程序内部唯一标识，例如 background_overview
    title: str，报告展示用章节标题
    body: NotRequired[str]
    NotRequired含义：**该键不是必须存在！**
    """
    section_key: str
    title: str
    body: NotRequired[str]

# 定义泛型,必须是
SectionStateT = TypeVar("SectionStateT", bound=SectionState)

class ResearchGraphState(TypedDict, Generic[SectionStateT]):
    """
    研究图全流程共享的运行标识、章节与报告状态。
    Generic[SectionStateT] 泛型：
        InsightAgent、MediaAgent可以各自扩展自己的章节字段，同时复用这套基础state。
    total=False：渐进式状态
        不需要初始化就拥有全部key；各个节点执行过程中，一点点产出各个字段。
        LangGraph节点返回增量字典，自动合并更新状态。

    公共字段说明：
        task_id: 本次研究任务唯一id
        query: 用户原始查询问题
        role: Agent角色，insight私域 / media公域
        sections: 章节数组，泛型，支持Insight/Media各自扩展章节结构；数组元素是SectionState运行时章节，不是静态SectionDefinition配置！
        cursor: 章节循环游标，标记当前处理到第几个章节，用来控制循环；【流程控制字段，不是业务证据字段】
        final_report: 全部章节处理完成后生成的完整报告文本
    """
    task_id: str
    query: str
    role: ROLE_KEY   # 为了方便打日志 和数据持久化
    # 现状：当前 05 只实现 InsightAgent，看起来完全可以直接写sections: list[SectionState]；
    # 但是这份契约设计是面向后续 Media 公域 Agent，两份 Agent 的章节状态未来可能扩展字段。
    sections: list[SectionStateT]  # 章节的信息 5个 章节英文名字 / 中文名字 / 章节的总结内容
    cursor: int    # 已经完成章节的识别的数量 0 1 2 3 4 5 
    final_report: str  # 最终整体md内容