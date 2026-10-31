"""
engines/host_agent/discussion_events.py
讨论事件转换器｜能力层薄工具类

归属：Host能力层；被LangGraph nodes.py节点调用。

职责：纯对象转换；零业务逻辑、零LLM、零IO、零发布；
将领域对象，转换为事件总线的 HostDiscussionMessageEvent Pydantic对象。

重要：只构造事件对象；不调用publish发布！
nodes把事件放入state["discussion_events"]；
Graph执行完毕，由section_ready_listener监听器统一批量publish事件总线。

两个转换函数：
1. build_agent_discussion_event
    AgentSectionOutput（insight/media单章节输出） → HostDiscussionMessageEvent
    业务：Agent原始body截断前2000字符；前端讨论区仅做预览；完整正文保存在上游原始产物。
2. build_judgement_discussion_event
    SectionJudgement（结构化裁决） → HostDiscussionMessageEvent
    关键：渲染逻辑收敛 contracts/judgement.py；直接读取 judgement.content @property；
    禁止本文件二次手写Markdown渲染，避免两份渲染逻辑分裂、输出格式不一致BUG。

数据流：
collect_agent_output_node → build_agent_discussion_event → state.discussion_events
apply_judgement_node → build_judgement_discussion_event → state.discussion_events
        ↓
section_ready_listener监听器取出state.discussion_events，统一publish_host_discussion_message发布总线

设计约束：
1. 只做转换，不执行业务判断；共识/冲突/研判逻辑全部在section_judge LLM；
2. Host主持人消息Markdown渲染逻辑100%收敛在 contracts/judgement.py 的 @property content；本文件绝不复制渲染代码；
3. 仅构造Pydantic对象；publish动作上移到监听器统一处理；便于单元测试：单元测试可以直接断言state内事件列表，不需要mock事件总线publish。
"""
from engines.common.events import HostDiscussionMessageEvent
from engines.contracts.judgement import SectionJudgement
from engines.host_agent.models import AgentSectionOutput


def build_agent_discussion_event(
        task_id: str,
        output: AgentSectionOutput,
) -> HostDiscussionMessageEvent:
    """
    构造 Insight 或 Media 的章节讨论事件。
    :param task_id: 当前任务唯一ID
    :param output: AgentSectionOutput 上游单Agent单章节输出
    :return: HostDiscussionMessageEvent Pydantic对象；body截断前2000字符，前端讨论区预览
    注意：只构造对象，不publish发布；由监听器后续统一批量发布事件总线。
    """
    return HostDiscussionMessageEvent(
        task_id=task_id,
        source=output.source,  # type: ignore  insight agent
        content=output.body[:2000],
        section_key=output.section_key,
    )


def build_judgement_discussion_event(
        task_id: str,
        judgement: SectionJudgement,
) -> HostDiscussionMessageEvent:
    """
    构造 Host 单章节研判讨论事件。
    :param task_id: 当前任务唯一ID
    :param judgement: 结构化裁决对象 SectionJudgement
    :return: HostDiscussionMessageEvent Pydantic对象
    关键：直接读取 judgement.content；content是contracts/judgement.py内部@property，自动渲染完整Markdown；
    禁止在本文件重复写markdown渲染逻辑，防止多版本渲染逻辑分裂。
    注意：只构造对象，不publish发布；监听器后续统一批量发布。
    """
    return HostDiscussionMessageEvent(
        task_id=task_id,
        source="host",
        content=judgement.content,
        section_key=judgement.section_key,
    )