"""
app/services/host/discuss_buffer.py
主持人Agent讨论消息内存缓冲

# 数据流位置
生产者：SectionReadyListener 发布【HOST_DISCUSSION_MESSAGE】事件
消费者：HostService收到事件 → 调用本类append_message写入内存
对外读取：HostService.get_discussion_records → FastAPI接口返回前端

纯内存存储！进程重启所有讨论记录全部丢失；未来生产需要持久化，需要在此层扩展数据库写入。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class DiscussionRecord:
    """单条讨论记录数据模型
    task_id: 任务唯一id
    source: 消息来源，枚举：insight / media / host
    message_text: 讨论消息正文
    sent_at: 记录入库时间 HH:MM:SS
    dimension_key: 关联章节section_key
    """
    task_id: str
    source: str
    message_text: str
    sent_at: str
    dimension_key: str


class DiscussionBuffer:
    def __init__(self) -> None:
        # 内存列表，存储全量DiscussionRecord；多task全部混存，读取时按task_id过滤
        self._discuss_records: list[DiscussionRecord] = []

    # 被订阅的函数 = host -> 数据 -> 函数 -> 添加到容器中
    def append_message(self, data: dict[str, Any]):
        """
        收到HOST_DISCUSSION_MESSAGE事件原始payload，转为DiscussionRecord追加内存
        :param data: 事件总线投递的HOST_DISCUSSION_MESSAGE原始dict payload
        """
        self._discuss_records.append(DiscussionRecord(
            task_id=data.get("task_id"), # type: ignore
            source=data.get("source"), # type: ignore
            message_text=data.get("content"), # type: ignore
            sent_at=datetime.now().strftime("%H:%M:%S"),
            dimension_key=data.get("section_key"), # type: ignore
        ))

    # 读取函数 = 前端接口 - router -> host_service -> task_id
    def read_messages(self, task_id: str) -> dict[str, Any]:
        """
        根据task_id，过滤返回该task全部讨论记录；返回结构化dict，上层HostService/FastAPI直接使用
        :param task_id: 任务id
        :return: {"discussion_records": [dict]}
        """
        return {
            "discussion_records": [
                {
                    "task_id": record.task_id,
                    "source": record.source,
                    "message_text": record.message_text,
                    "sent_at": record.sent_at,
                    "dimension_key": record.dimension_key
                }
                for record in self._discuss_records
                if record.task_id == task_id
            ]}