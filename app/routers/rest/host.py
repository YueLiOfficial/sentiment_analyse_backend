"""
app/api/host_router.py
Host主持人Agent对外HTTP接口
接口：GET /api/host/discussion?task_id=xxx
从DiscussionBuffer内存读取该task全部agent+host讨论记录返回前端
数据来自内存，进程重启全部丢失；生产持久化需要改造buffer层
"""
from fastapi import APIRouter, Query

from app.dependences import HostServiceDep
from app.schemas.host_schema import HostDiscussionRecordsResponse

host_router = APIRouter(prefix="/api/host", tags=["主持人 Agent"])


@host_router.get(
    "/discussion",
    response_model=HostDiscussionRecordsResponse,
    description=" 获取讨论区里收集到的发言记录；数据来自内存buffer，进程重启丢失"
)
def get_host_discussion_records_endpoint(
        service: HostServiceDep,
        task_id: str = Query(..., description="任务唯一task_id")
):
    """返回讨论区发言记录。"""
    discussion_records = service.get_discussion_records(task_id)
    return HostDiscussionRecordsResponse(**discussion_records)