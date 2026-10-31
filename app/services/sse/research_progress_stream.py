"""研究进度 SSE 事件流
模块归属：SSE进度反馈模块 · 消费转发核心
整体职责：
1. 【事件总线绑定入口】register_progress_update()：调用全局subscribe，把自身的_broadcast_progress_update回调函数注册绑定到事件总线的ROLE_PROGRESS / ROLE_RESULT / ROLE_ERROR三类事件；
    这里就是**生产者与消费者的绑定点**！不是赋值，是调用subscribe函数，把回调函数引用注册进总线内部注册表；
2. stop_progress_update()：执行解绑unsubscribe；清空所有浏览器客户端队列池；应用shutdown生命周期调用；
3. _broadcast_progress_update(event_type, data)：【事件总线回调函数】；
    当事件总线收到三类进度事件，会同步调用这个方法；做payload序列化，广播写入全部在线浏览器的asyncio队列；
4. stream_research_progress(request)：【浏览器HTTP SSE长连接生成器】；
    浏览器GET /api/events/stream进入本生成器；为每一个浏览器连接新建专属asyncio.Queue；加入_subscribers池；
    循环阻塞等待队列数据，yield给sse‑starlette库组装SSE协议报文；客户端断开finally清理队列，防止内存泄漏。

监听绑定的事件总线事件集合：
- EventType.ROLE_PROGRESS：角色增量进度更新
- EventType.ROLE_RESULT：角色执行成功终态
- EventType.ROLE_ERROR：角色执行异常失败终态
"""
import asyncio
import json
from loguru import logger

from engines.common.events import EventType, subscribe, unsubscribe


class ResearchProgressStream:
    """订阅角色进度、结果和错误事件，并推送给在线 SSE 客户端"""

    # 需要转发给前端的事件总线事件集合
    FORWARDED_EVENT_TYPES = (
        EventType.ROLE_PROGRESS,
        EventType.ROLE_RESULT,
        EventType.ROLE_ERROR
    )

    def __init__(self):
        """初始化 SSE 客户端订阅队列池
        self._subscribers：存储**每一条浏览器SSE长连接**专属asyncio.Queue实例；
        注意：这个list存放的是浏览器会话队列，**不是事件总线的回调绑定！！**
        __init__构造函数里面**不会做事件总线subscribe绑定**；绑定动作需要显式调用 register_progress_update()；
        如果只new实例，不调用register_progress_update，就算有浏览器连上SSE，也永远收不到任何进度事件！！
        """
        self._subscribers: list[asyncio.Queue] = []

    def register_progress_update(self):
        """向全局事件总线注册研究进度事件监听【事件总线绑定动作在这里！】
        调用时机：AppLifecycleManager.register() 应用启动阶段，**必须在Agent/Host业务任务开始之前调用！**

        内部逻辑：
        遍历三类目标事件EventType；调用全局subscribe(event_type, callback)；
        把本实例的回调方法 self._broadcast_progress_update，**注册绑定到事件总线的全局注册表 _subscribers字典**（注意：这里是events.py模块的全局_subscribers，和本类实例self._subscribers是完全两个变量！名字一样，所属作用域不一样，极易混淆！！）

        绑定完成效果：
        后续事件总线每当收到 ROLE_PROGRESS / ROLE_RESULT / ROLE_ERROR，就会同步调用 self._broadcast_progress_update(event_type, data)。

        时序强约束：
        >> 必须**先执行本函数完成总线回调绑定，再启动HostListener、再提交Agent后台任务**；
        >> 如果顺序颠倒：Agent任务先跑，第一批发出来的进度事件，此时回调还没有注册；事件总线没有匹配的订阅者，事件直接丢弃，前端丢失任务起始阶段的进度消息。
        """
        # 1. 遍历关注的事件类型，将转发方法绑定到事件中心
        for event_type in self.FORWARDED_EVENT_TYPES:
            subscribe(event_type, self._broadcast_progress_update)

    def stop_progress_update(self):
        """注销事件监听并清空 SSE 客户端订阅队列【解绑动作】
        调用时机：AppLifecycleManager.shutdown()应用关闭阶段；
        做两件独立事情：
        1. unsubscribe(self._broadcast_progress_update)：从**事件总线全局注册表**解绑回调；之后事件总线收到进度事件，不再调用_broadcast_progress_update；
        2. self._subscribers.clear()：清空**本实例的浏览器会话队列池**；所有现存SSE长连接会因为队列清空逐步断开，释放内存。

        两件事不要搞混：
        - 解绑总线回调：解决“不再接收新的业务事件”；
        - 清空浏览器队列：解决“释放已经建立的http长连接资源”；
        """
        # 1. 从事件中心注销当前转发函数
        unsubscribe(self._broadcast_progress_update)
        # 2. 清空所有客户端队列以释放连接
        self._subscribers.clear()

    def _broadcast_progress_update(
        self,
        event_type: EventType,
        data: dict
    ):
        """将事件总线中的研究进度事件转发给当前在线客户端。
        【事件总线回调入口函数】；当总线收到FORWARDED_EVENT_TYPES内事件，自动同步执行本函数。
        入参：
            event_type：事件枚举 ROLE_PROGRESS / ROLE_RESULT / ROLE_ERROR
            data：pydantic模型model_dump()之后的原始字典载荷（来自events.py publish）

        业务动作：
        1. 组装SSE外层payload：{"event":event_type, "data":原始业务dict}，序列化为json字符串；
        2. 遍历当前所有浏览器会话队列池 self._subscribers；list拷贝副本，防止遍历过程队列增删引发迭代异常；
        3. put_nowait(payload)：把同一份消息拷贝写入**每一条在线浏览器专属队列**；实现多浏览器同时收到同一条进度。

        现存风险：
        1. **没有task_id过滤！！不管是哪个task产生的事件，全部推送给全部在线浏览器连接；前端JS必须自己解析payload.data.task_id过滤不属于当前页面的消息；后端不做隔离。**
        2. put_nowait无try‑except捕获QueueFull；任意一个客户端队列满，直接抛出异常；本回调是事件总线同步回调，一旦异常，总线内部try‑except只会打error日志，**本回调后续循环会中断，剩下的客户端收不到这条消息；更严重，后续到来的全部进度事件，本回调不会再执行！**
        3. 同步执行，本函数内禁止耗时IO；会阻塞发布事件的Agent业务协程。
        """
        # 1. 将原生事件字典序列化为 JSON 字符串
        payload = json.dumps({"event": event_type, "data": data}, ensure_ascii=False)
        # 2. 将事件推送到所有活跃客户端的专属队列
        for queue in list(self._subscribers):
            queue.put_nowait(payload)



    """
        接口(request:Request -> 1.包含请求数据包的全部数据 2.检查前端的状态 is_disconnected())
    
        while True:
        
            1. 会判断前端有没有断开连接 sse长连接已经断开了  前端(es = EventSourceStream(uri) es.addEventListener("事件类型",函数) es.close() )
            if request.is_disconnected():
                logger.info("前端主动断开连接了!我们也断开!")
                break     
            2. 获取队列数据
            data =await queue.get() 
            
            3. 返回数据
            yield data
    
    
    
    
    
    
    
    
    """


    async def stream_research_progress(self, request):
        """管理 SSE 客户端连接并持续推送研究进度事件
        【浏览器HTTP长连接生成器；每一个浏览器页面访问GET /api/events/stream，就会进入这个生成器一次】
        :param request: starlette原始Request对象；用于检测浏览器客户端是否已经断开网络/关闭页面。
        :return: async生成器，产出SSE协议字典，交给sse‑starlette的EventSourceResponse封装成标准SSE字节流返回浏览器。

        单条浏览器连接完整生命周期：
        1. 浏览器发起GET /api/events/stream请求 → FastAPI路由调用本生成器；
        2. 为**当前这一个浏览器连接**新建一条独立asyncio.Queue；append加入self._subscribers浏览器会话队列池；
        3. 第一条yield：立刻向浏览器推送 connected 连接建立成功消息；
        4. while True循环：
            a. 检测request.is_disconnected()浏览器是否关闭；断开直接跳出循环，进入finally；
            b. await queue.get()阻塞等待**属于本浏览器自己队列**的新payload；
            c. yield payload字典，交给sse‑starlette输出SSE报文给浏览器；
        5. finally块：无论正常跳出、网络异常、页面关闭，都会执行；把当前这条连接的queue从self._subscribers移除，防止内存泄漏。

        重要：
        >> 本生成器**只管浏览器连接的队列；完全不做事件总线subscribe绑定！**
        >> 就算一百个浏览器连上这个SSE接口，如果之前没有调用register_progress_update()绑定事件总线回调；所有浏览器队列永远是空，浏览器只会收到connected，之后再也收不到任何业务进度消息！
        >> 【这就是很多人踩坑点：只开了SSE路由，忘记生命周期调用register_progress_update绑定总线回调，SSE“能连上但是没有任何数据”】
        """
        # 1. 为当前连接创建专属异步队列
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        logger.debug("SSE 客户端连接")
        try:
            # 2. 首先向客户端推送连接成功消息
            yield {"event": "connected", "data": json.dumps({"status": "connected"})}
            # 3. 等待并消费当前连接队列中的实时事件
            while True:
                if await request.is_disconnected():
                    break
                payload = await queue.get()
                yield {"data": payload}
        finally:
            # 4. 客户端断开时移除对应队列
            if queue in self._subscribers:
                self._subscribers.remove(queue)
            logger.debug("SSE 客户端关闭")