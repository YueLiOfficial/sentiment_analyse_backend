"""
engines/host_agent/nodes.py
Host LangGraph 三大业务节点
原则：节点只做胶水编排；复杂业务全部下沉能力层(section_pair_store / section_judge / discussion_events)

数据流：
collect → 条件路由判断是否存在就绪配对
    → 有就绪配对 → generate（调用LLM） → apply（保存+mark+生成host事件） → END
    → 无就绪配对 → END

重要时序约束：
mark_judged 只能放在apply节点；必须拿到合法SectionJudgement之后才标记章节完成；
如果generate节点提前mark，LLM异常没有产出裁决，章节被永久标记完成，无法重试研判。
"""
import json
from typing import Any, List

from loguru import logger

from engines.common.events import HostDiscussionMessageEvent
from engines.common.reports import get_output_dir, save_report
from engines.contracts.agent_rules import role_display_name
from engines.contracts.judgement import SectionJudgement
from engines.host_agent.models import AgentSectionOutput, AgentSectionPair
from engines.host_agent.section_judge import HostSectionJudge
from engines.host_agent.section_pair_store import SectionPairStore
from engines.host_agent.discussion_events import (
    build_agent_discussion_event,
    build_judgement_discussion_event
)
from engines.host_agent.state import HostState



class HostNodes:
    """
    Host LangGraph 的章节收集、研判、记录与持久化节点。

    整体说明：
    1. 本类全部为LangGraph业务节点，全部是async异步方法，适配LangGraph异步执行模型；
    2. 研判器HostSectionJudge不在节点内部new，通过构造函数外部注入，便于单元测试mock LLM；
    3. 所有节点禁止直接操作事件总线publish；事件对象全部写入state["discussion_events"]，交由上层SectionReadyListener监听器统一批量发布；
    4. 状态存储全部复用入参state快照内部对象，节点不持有任何task全局状态；
    5. 链路末尾固定执行save_judgements持久化节点，每次Graph调用都会覆盖写judgements.json磁盘文件。
    """

    def __init__(self,section_judge:HostSectionJudge):
        """
        HostNodes构造方法
        :param section_judge: 外部传入的Host LLM研判器实例；由build_graph上层工厂传入，支持mock注入用于单元测试
        """
        # 保存LLM研判器实例，供generate_section_judgement节点调用
        self._section_judge = section_judge

    async def collect_agent_output(self,state:HostState)->dict[str,Any]:
        """
        节点1: 保存当前Agent章节输出并生成对应讨论事件
        业务流程:
            1. 从本次Graph调用的state快照中取出SECTION_READY原始事件payload
            2. 通过AgentSectionOutput静态from_section_ready_event方法,将原始dict载体转成强类型的领域模型AgentSectionOutput
            3. 将Agent章节输出存入state快照内的SectionPairStore,支持重跑场景覆盖同source+section_key旧输出
            4. 调用能力层build_agent_discussion_event构造Agent发言事件对象
            5. 打印业务日志,记录收到章节就绪事件
            6. 返回Langgraph状态增量字典,Langgraph会自动合并返回state快照
        注意：
        本节点无论单边/双边Agent到达都会执行；只要收到SECTION_READY事件就会执行；
        仅构造事件对象写入state，本节点不调用publish；由监听器Graph调用结束后统一批量发布；
        :param state:  HostState，本次Graph调用的task维度快照，包含event_payload、section_pair_store、task_id等信息
        :return:  dict[str, Any] LangGraph状态增量字典；更新section_pair_store、discussion_events
        """
        # 从state快照的原始事件payload,构建强类型Agent章节输出对象
        #  models.AgentSectionOutput -> 接收单个insight/media发送的章节总结对象
        # 接收传递过来的 media/insight的章节信息
        agent_output:AgentSectionOutput = AgentSectionOutput.from_section_ready_event(event_payload=state['event_payload']) # type: ignore
        # 将Agent输出存入快照内存的配对存储, 重跑会覆盖同来源同章节旧数据
        state['section_pair_store'].store_output(agent_output) # type: ignore
        # 构造单条Agent发言讨论事件；仅写入state，不对外发布
        # host  ->  单个章节 | 单个章节一对凑齐了,做好了研判 -> host web service
        discussion_events = [
            build_agent_discussion_event(state['task_id'],agent_output) # type: ignore
        ]
        # 获取host角色展示名称,打印业务链路日志,便于上线排查链路
        host_name  = role_display_name("host")
        logger.info(
            f"【{host_name}】收到章节就绪事件 "
            f"章节={agent_output.section_key} 来源={agent_output.source}"
        )
        return {
            "section_pair_store": state["section_pair_store"], # type: ignore
            "discussion_events": discussion_events,
        }

    # 条件 section_pair_store.has_ready_pair = true

    async def generate_section_judgement(self,state:HostState)->dict[str,Any]:
        """
        节点2：调用 Host LLM 为当前已齐备章节生成结构化研判。
        触发条件: collect_agent_output节点执行完成后，条件路由cond_has_ready_pair判定store存在就绪未研判配对，才会进入本节点。
        业务流程:
        1. 从state快照内SectionPairStore获取一个就绪待研判的章节配对(双方Agent章节全部到达)
        2. 打印业务日志,标记LLM开始研判,记录章节key
        3. 调用注入的self._section_judge研判器,传入配对对象,调用LLM生成结构化SectionJudgement对象
        4. 返回Langgraph增量字典,把SectionJudgement写入state字段section_judgement,交给后续app_section_
        judgement节点进行消费!

        :param state:
        :return:
        """
        # 获取还未研判的章节配对列表
        section_pair:AgentSectionPair = state['section_pair_store'].get_ready_pair() # type: ignore
        host_name = role_display_name("host")
        logger.info(
            f"【{host_name}】双 Agent 章节已齐备，开始研判 "
            f"章节={section_pair.section_key}"
        )
        # 从存储取出一个就绪双Agent章节配对；未做None判空保护
        section_judgement:SectionJudgement = await self._section_judge.judge_section(section_pair)

        # 返回增量，将裁决写入state瞬时字段，供apply节点使用
        return {"section_judgement": section_judgement}

    async def apply_section_judgement(
            self,
            state: HostState,
    ) -> dict[str, Any]:
        """
        节点3: 将章节研判应用到host状态并生成讨论事件
        触发条件: generate_section_judgement节点执行完成后，条件路由cond_has_judgement判定store存在未应用的judgement，才会进入本节点。
        业务流程：
        1. 从state快照的瞬时字段取出LLM生成的SectionJudgement结构化裁决；
        2. 【时序关键点】优先调用mark_judged，把该section_key标记为Host研判完成；
        3. 将新生成的裁决追加到state["judgements"]完整裁决列表；使用列表解包生成新列表，不原地修改原list；
        4. 调用能力层build_judgement_discussion_event，构造Host主持人的讨论事件；追加到discussion_events；
        5. 打印业务日志，记录该章节研判完成；
        6. 返回LangGraph增量字典；LangGraph合并更新state中的section_pair_store、judgements、discussion_events。
        :param state:
        :return:
        """
        # 获取研判结果
        section_judgement:SectionJudgement = state['section_judgement'] # type: ignore
        # 先标记该章节host已经研判完成
        state['section_pair_store'].mark_judged(section_judgement.section_key) # type: ignore
        # 解包旧列表 + 追加新裁决；生成全新judgements列表，不原地修改state原list
        judgements = [*state["judgements"], section_judgement] # type: ignore

        # 原有全部讨论事件 + 新增Host主持人裁决事件；生成新的事件列表
        discussion_events = [
            *state["discussion_events"], # type: ignore
            build_judgement_discussion_event(
                state["task_id"], # type: ignore
                section_judgement,
            ),
        ]
        logger.info(
            f"【{role_display_name('host')}】章节研判完成 "
            f"章节={section_judgement.section_key}"
        )
        return {
            "section_pair_store": state["section_pair_store"], # type: ignore
            "judgements": judgements,
            "discussion_events": discussion_events,
        }

    # 条件 judgements = len = 5

    async def save_judgements(self, state: HostState) -> dict[str, Any]:
        """
        节点4：后置持久化节点，保存 Host 结构化研判到磁盘judgements.json。
        触发条件：
        【必执行节点】Graph的**全部业务分支最后都会流转进入本节点**；
        无论本次Graph是单边Agent到达（没有触发LLM研判）、还是已经完成LLM研判，都会执行磁盘覆盖写。

        业务流程：
        1. 根据task_id与模块host，调用get_output_dir获取该任务host产物输出目录；
        2. 遍历state["judgements"]裁决列表，调用model_dump()把每一个结构化裁决模型转为dict；
        3. 使用json.dumps序列化为格式化json字符串；ensure_ascii=False保证中文正常输出；indent=2美化缩进；
        4. 调用公共工具save_report，把json内容写入输出目录下judgements.json；**覆盖写原有文件**；
        5. 打印业务日志，输出json文件保存绝对路径；
        6. 返回空增量字典；本节点只做磁盘IO，**不会修改state快照中任何内存字段**。

        :param state:
        :return:
        """
        # 获取当前task下host模块产物输出目录
        output_dir = get_output_dir(state["task_id"], "host") # type: ignore

        # 将内存中全部结构化裁决Pydantic对象序列化为json字符串；全量导出，覆盖写磁盘
        structured_content = json.dumps(
            [judgement.model_dump() for judgement in state["judgements"]], # type: ignore
            ensure_ascii=False,
            indent=2,
        )
        # 调用通用报告存储工具，写入judgements.json；覆盖已有文件
        json_path = save_report(
            output_dir,
            "judgements.json",
            structured_content,
        )
        logger.info(f"Host 结构化研判已保存 {json_path}")
        # save_judgements仅做磁盘导出，不修改内存state，返回空增量
        return {}