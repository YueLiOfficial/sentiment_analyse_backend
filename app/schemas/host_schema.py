from pydantic import BaseModel, Field

class HostDiscussionRecord(BaseModel):
    """主持人讨论区单条发言记录"""
    task_id: str          # 所属任务id
    source: str           # 发言来源：insight / media / host
    message_text: str     # 发言内容文本
    sent_at: str          # 发言产生时间字符串
    dimension_key: str    # 对应五维章节section_key

class HostDiscussionRecordsResponse(BaseModel):
    """主持人讨论区发言记录列表，接口返回最外层结构体"""
    discussion_records: list[HostDiscussionRecord] = Field(default_factory=list)