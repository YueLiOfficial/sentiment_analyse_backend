"""
app/services/host/host_service.py
Host主持人Agent 领域服务层
# 对外能力
get_discussion_records(task_id): 给FastAPI路由调用，返回该task全部讨论记录
"""
from loguru import logger
from typing import Any

from engines.common.events import EventType, subscribe, unsubscribe
from engines.host_agent.section_ready_listener import SectionReadyListener
from app.services.host.discuss_buffer import DiscussionBuffer


class HostService:
    def __init__(self):
        # 实例化章节就绪事件监听器：内部会实例化host graph
        self._listener = SectionReadyListener()
        # 实例化讨论消息内存缓冲：接收HOST_DISCUSSION_MESSAGE写入内存
        self.discussion_buffer = DiscussionBuffer()
        # 保存回调函数原始对象！unsubscribe必须传入同一个函数对象，禁止lambda，否则取消订阅失效内存泄漏
        self._on_discussion_msg_callback = self._on_discussion_message

    # 注册  host -> service -> 订阅函数
    def register_discussion_buffer(self):
        """
        订阅【HOST_DISCUSSION_MESSAGE】事件；host graph产出主持人讨论消息，写入内存buffer
        生命周期第一步：优先调用】必须在start listener之前调用，防止host产出消息无人接收发生丢包
        """
        subscribe(EventType.HOST_DISCUSSION_MESSAGE, self._on_discussion_msg_callback)
        logger.info("HostService: 已注册 HOST_DISCUSSION_MESSAGE 事件订阅，讨论消息buffer就绪")

    def stop_discussion_buffer(self):
        """取消HOST_DISCUSSION_MESSAGE事件订阅"""
        unsubscribe(self._on_discussion_msg_callback)
        logger.info("HostService: 已取消 HOST_DISCUSSION_MESSAGE 事件订阅")

    def _on_discussion_message(self, _event_type: EventType, data: dict[str, Any]):
        """
        事件总线回调：收到【HOST_DISCUSSION_MESSAGE】事件，把payload交给buffer写入内存
        :param _event_type: 事件枚举 HOST_DISCUSSION_MESSAGE
        :param data: 事件原始payload dict
        """
        logger.info(f"收到讨论消息...")
        self.discussion_buffer.append_message(data)

    # app  启动: register_host_listener register_discussion_buffer  停止: stop_host_listener stop_discussion_buffer

    def register_host_listener(self):
        """
        注册并启动 Host 研判监听器。
        内部调用 SectionReadyListener.start() → 订阅【SECTION_READY】事件，启动后台消费协程
        【生命周期第二步】必须在 register_discussion_buffer() 之后调用！
        """
        self._listener.start()
        logger.info("HostService: 研判引擎启动成功")

    def stop_host_listener(self):
        """停止 Host 章节监听 worker；取消SECTION_READY订阅、释放内存状态"""
        self._listener.stop()
        logger.info("HostService: 研判引擎已停止")















    def get_discussion_records(self, task_id: str) -> dict[str, Any]:
        """
        对外查询接口：获取指定task全部讨论记录；FastAPI路由直接调用
        :param task_id: 任务id
        :return: {"discussion_records": list[dict]}
        """
        return self.discussion_buffer.read_messages(task_id)














