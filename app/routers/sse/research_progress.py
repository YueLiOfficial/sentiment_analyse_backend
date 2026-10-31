"""
app/api/research_progress.py
SSE 实时事件流路由

职责：
1. 对外暴露GET /api/events/stream SSE长连接HTTP入口；浏览器EventSource访问此接口建立长连接；
2. 从dependencies全局单例获取ResearchProgressStream实例；
3. 调用实例的stream_research_progress(request)得到异步生成器；
4. 将生成器交给 sse‑starlette 库 EventSourceResponse，由库完成SSE协议封装，返回给浏览器。
"""
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.dependences import get_research_progress_stream

search_progress_router = APIRouter(tags=["SSE实时事件流路由"])


@search_progress_router.get("/api/events/stream")
async def stream_research_progress(request: Request):
    """推送研究进度 SSE 事件流
    浏览器EventSource访问本接口建立SSE长连接；
    1. request: starlette原始请求对象；内部携带客户端连接信息；会传递给stream_research_progress生成器；
    2. get_research_progress_stream()拿到全局唯一SSE流单例；
    3. 调用stream_research_progress(request)返回异步生成器；
    4. EventSourceResponse包装生成器，输出标准SSE协议字节流。

    连接生命周期：
    - 浏览器发起GET请求 → 进入本接口；
    - 内部生成器会新建浏览器专属asyncio.Queue；
    - 浏览器关闭页面/网络断开 → request.is_disconnected()检测到，生成器finally块清理队列，释放资源。

    业务约束（来自底层ResearchProgressStream）：
    1. 后端**不做task_id隔离过滤**；所有任务的进度事件全部广播给全部在线浏览器；前端JS解析payload之后，必须根据data.task_id过滤无关任务消息；
    2. 没有历史快照；页面刷新重连，只能接收连接建立之后新产生的事件；历史已发生进度全部丢失；
    3. 多worker部署本SSE模块失效；只能单worker uvicorn启动。
    """
    # EventSourceResponse 把一个持续产生事件的异步生成器转换为浏览器能够接收的SSE长连接。
    return EventSourceResponse(
        get_research_progress_stream().stream_research_progress(request)
    )