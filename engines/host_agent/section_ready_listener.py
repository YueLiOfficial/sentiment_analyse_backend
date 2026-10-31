"""
engines/host_agent/section_ready_listener.py
HostAgent 事件入口监听器 SectionReadyListener

模块定位
Host模块唯一外部事件入口；订阅全局事件总线的 SECTION_READY 事件；
接收上游Insight/Media Agent章节产出完成通知；通过异步队列解耦事件总线回调阻塞；
维护每个task_id独立HostState内存快照，驱动LangGraph Host图执行；
Graph执行完成之后，取出本次调用产出的discussion_events，打印消息摘要日志，批量发布HOST_DISCUSSION_MESSAGE讨论事件到事件总线。
"""
import asyncio
from typing import Any

from loguru import logger

from engines.common.events import (
    EventType,
    publish_host_discussion_message,
    subscribe,
    unsubscribe
)
from engines.common.research_tasks import research_task_manager
from engines.contracts.agent_rules import role_display_name
from engines.host_agent.graph import build_graph
from engines.host_agent.section_judge import HostSectionJudge
from engines.host_agent.section_pair_store import SectionPairStore
from engines.host_agent.state import HostState


class SectionReadyListener:
    """串行消费章节就绪事件并驱动 Host LangGraph"""

    def __init__(self) -> None:
        """
        监听器构造函数
        现状缺口：硬编码实例化HostSectionJudge，无法外部注入mock研判器；单元测试mock LLM困难；
        优化建议：增加judge入参，可选外部注入，build_graph传入该实例。
        """
        # 硬编码创建LLM研判实例；当前无法外部替换mock对象
        self._graph = build_graph(HostSectionJudge())
        # task维度内存快照仓库
        # key: task_id；value：裁剪之后的HostState快照，仅保留task_id、section_pair_store、judgements
        self._host_states: dict[str, HostState] = {}
        # 异步串行消费队列；仅start()执行之后才会被实例化；start前访问会抛AttributeError
        self._event_queue: asyncio.Queue[dict[str, Any]]

    def start(self) -> None:
        """
        订阅章节就绪事件并启动消费任务
        执行步骤：
        1. 实例化异步事件队列；
        2. 向事件总线订阅SECTION_READY，绑定回调_enqueue_event；
        3. 将后台消费协程提交全局任务管理器执行；
        4. 打印启动日志。
        """
        self._event_queue = asyncio.Queue()
        subscribe(EventType.SECTION_READY, self._enqueue_event)
        # self._process_events()
        research_task_manager.submit_task(self._process_events())
        logger.info("SectionReadyListener: 已启动 Host 章节研判")

    def stop(self) -> None:
        """
        取消事件订阅并释放运行状态

        执行步骤：
        1. 取消SECTION_READY事件总线订阅；后续新事件不会再进入回调；
        2. 清空全部task内存快照字典，释放内存；
        """
        unsubscribe(self._enqueue_event)
        self._host_states.clear()
        logger.info("SectionReadyListener: 已停止")

    def _enqueue_event(
            self,
            _event_type: EventType,
            event_payload: dict[str, Any],
    ) -> None:
        """
        将章节就绪事件加入串行消费队列

        事件总线同步回调入口；**只做入队，禁止await、禁止LLM、禁止IO、禁止执行业务逻辑**。
        put_nowait 同步入队，不会阻塞事件总线回调。
        前提：必须已经调用start()初始化_event_queue；未start调用会直接抛AttributeError。

        :param _event_type: 事件枚举，固定EventType.SECTION_READY
        :param event_payload: 事件总线model_dump后的原始dict载荷，非Pydantic对象
        """
        self._event_queue.put_nowait(event_payload)

    async def _process_events(self) -> None:
        """
        持续消费章节就绪事件并发布 Host 讨论事件

        业务主循环：死循环从队列阻塞获取SECTION_READY事件payload；
        每一条payload触发一次完整Host Graph调用。

        快照裁剪逻辑：
        graph.ainvoke返回完整updated_state，里面包含本次瞬时字段discussion_events、section_judgement；
        但是回写_host_states的时候，**手动重建字典，只持久保存task_id、section_pair_store、judgements**；
        瞬时产物discussion_events、section_judgement不会跨事件保存在内存快照；
        设计意图：discussion_events是本次调用对外输出事件，不需要留存；section_judgement是generate→apply节点瞬时传递，apply节点已经置None，不需要持久。
        """
        while True:
            # 阻塞等待队列事件
            event_payload = await self._event_queue.get()
            task_id = event_payload["task_id"]

            # 读取该task已有快照；没有则初始化全新快照+全新SectionPairStore实例
            host_state = self._host_states.get(task_id)
            if host_state is None:
                host_state = {
                    "task_id": task_id,
                    "section_pair_store": SectionPairStore(),
                    "judgements": []
                }

            # 组装本次Graph调用输入快照：基于历史快照，灌入本次原始事件payload
            invocation_state: HostState = {
                **host_state,
                "event_payload": event_payload
            } # type: ignore

            # 执行一次短生命周期Host LangGraph调用
            updated_state: HostState = await self._graph.ainvoke(invocation_state)

            # 取出本次Graph调用产出的讨论事件列表（瞬时产物，不会写入持久快照）
            discussion_events = updated_state["discussion_events"] # type: ignore

            # ==========【快照裁剪：手动重建持久快照，丢弃瞬时字段】==========
            # 只把跨事件需要保留的三个字段写回 _host_states；
            # discussion_events、section_judgement 属于本次调用瞬时字段，不做跨事件持久化。
            self._host_states[task_id] = {
                "task_id": task_id,
                "section_pair_store": updated_state["section_pair_store"], # type: ignore
                "judgements": updated_state["judgements"] # type: ignore
            }

            # 逐条遍历本次产出的全部讨论事件：打印摘要日志 + 发布事件总线
            for discussion_event in discussion_events:
                logger.info(
                    f"【{role_display_name('host')}】发送讨论事件 "
                    f"来源={role_display_name(discussion_event.source):<12} "
                    f"章节={discussion_event.section_key:<10} "
                    f"内容={discussion_event.content[:20]}..."
                )
                publish_host_discussion_message(discussion_event)